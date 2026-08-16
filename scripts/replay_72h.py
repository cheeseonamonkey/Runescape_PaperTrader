#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime, timezone
from math import log1p
from pathlib import Path
from statistics import mean
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import PROFILES, STARTING_GP, REPLAY_EVERY_HOURS, REPLAY_HOURS, REPLAY_ITEMS
from src.io_utils import DATA, read_json, write_json
from src.market import timeseries
from src.portfolio import fresh_wallet, close_positions, open_positions, wallet_value
from src.strategy import wallet_candidates

OUT = DATA / "simulations" / "latest_72h.json"


def _age_hours(value):
    try:
        return max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(value)).total_seconds() / 3600)
    except (TypeError, ValueError):
        return None


def _universe(snapshot):
    seen, rows = set(), []
    pools = [snapshot.get("market", {}).get("items", [])[:16]]
    for wallet in snapshot.get("wallets", {}).values():
        pools.append(wallet.get("top_candidates", [])[:12])
        pools.append(wallet.get("positions", [])[:8])
    for pool in pools:
        for row in pool:
            item_id = row.get("id") or row.get("item_id")
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            rows.append({"id": int(item_id), "name": row.get("name", f"Item {item_id}"), "limit": row.get("limit")})
            if len(rows) >= REPLAY_ITEMS:
                return rows
    return rows


def _mid(row):
    vals = [v for v in (row.get("avgHighPrice"), row.get("avgLowPrice")) if isinstance(v, (int, float)) and v > 0]
    return sum(vals) / len(vals) if vals else None


def _vol(row):
    return int(row.get("highPriceVolume", 0) or 0) + int(row.get("lowPriceVolume", 0) or 0)


def _common_at(timestamp, series_by_item, meta):
    out = []
    for item_id, rows in series_by_item.items():
        row = rows.get(timestamp)
        if not row:
            continue
        high, low = row.get("avgHighPrice"), row.get("avgLowPrice")
        mid = _mid(row)
        if not high or not low or high <= low or not mid:
            continue
        earlier = [r for ts, r in rows.items() if ts < timestamp]
        earlier = sorted(earlier, key=lambda r: r.get("timestamp", 0))[-6:]
        prev_mid = _mid(earlier[-1]) if earlier else mid
        trailing_vol = mean([_vol(r) for r in earlier]) if earlier else max(1, _vol(row))
        volume_1h = _vol(row)
        momentum = mid / prev_mid - 1 if prev_mid else 0
        accel = max(-1, min(5, volume_1h / max(1, trailing_vol) - 1))
        volume_5m = max(1, int(volume_1h / 12 * max(.2, min(3, 1 + accel))))
        turnover = volume_1h * mid
        liquidity = min(1, log1p(turnover) / 19)
        info = meta[item_id]
        out.append({
            "id": item_id, "name": info["name"], "limit": info.get("limit"), "members": False, "highalch": None,
            "high": int(high), "low": int(low), "spread_roi": (high - low) / low,
            "momentum_5m_vs_1h": momentum, "volume_5m": volume_5m, "volume_1h": volume_1h,
            "volume_acceleration": accel, "turnover_gp_1h": int(turnover),
            "liquidity_score": liquidity, "quote_age_minutes": 0,
        })
    return sorted(out, key=lambda r: r["turnover_gp_1h"], reverse=True)


def _max_drawdown(points):
    peak, dd = 0, 0
    for point in points:
        value = point["value_gp"]
        peak = max(peak, value)
        if peak:
            dd = min(dd, value / peak - 1)
    return dd


def run(force=False):
    cached = read_json(OUT, {})
    age = _age_hours(cached.get("generated_at"))
    if not force and age is not None and age < REPLAY_EVERY_HOURS and cached.get("wallets"):
        print(f"72h replay cached age={age:.2f}h")
        return cached

    snapshot = read_json(DATA / "latest_snapshot.json", {})
    universe = _universe(snapshot)
    if len(universe) < 4:
        raise RuntimeError("not enough items for replay universe")
    meta = {row["id"]: row for row in universe}
    series_by_item, errors = {}, []
    def fetch_one(row):
        series = timeseries(row["id"], "1h")
        selected = series[-(REPLAY_HOURS + 8):]
        return row, {int(x["timestamp"]): x for x in selected if x.get("timestamp")}
    with ThreadPoolExecutor(max_workers=min(6, len(universe))) as pool:
        futures = {pool.submit(fetch_one, row): row for row in universe}
        for future in as_completed(futures):
            row = futures[future]
            try:
                fetched_row, series = future.result()
                series_by_item[fetched_row["id"]] = series
            except Exception as exc:
                errors.append({"id": row["id"], "name": row["name"], "error": type(exc).__name__})

    timestamps = sorted({ts for rows in series_by_item.values() for ts in rows})[-REPLAY_HOURS:]
    if len(timestamps) < 12:
        raise RuntimeError("insufficient aligned replay history")

    results = {}
    for slug, profile in PROFILES.items():
        wallet = fresh_wallet(profile)
        points, trades = [], []
        for ts in timestamps:
            now = datetime.fromtimestamp(ts, timezone.utc)
            common = _common_at(ts, series_by_item, meta)
            latest = {
                str(r["id"]): {"high": r["high"], "low": r["low"], "highTime": ts, "lowTime": ts}
                for r in common
            }
            trades.extend(close_positions(wallet, latest, profile, now=now))
            candidates = wallet_candidates(common, profile, None)
            trades.extend(open_positions(wallet, candidates, latest, profile, now=now))
            points.append({"at": now.isoformat(), "value_gp": wallet_value(wallet, latest, profile)})
        end = points[-1]["value_gp"]
        results[slug] = {
            "name": profile.name,
            "start_gp": STARTING_GP,
            "end_gp": end,
            "return_pct": round(end / STARTING_GP - 1, 6),
            "max_drawdown": round(_max_drawdown(points), 6),
            "trades": len(trades),
            "buys": sum(1 for t in trades if t.get("side") == "BUY"),
            "sells": sum(1 for t in trades if t.get("side") == "SELL"),
            "ending_positions": len(wallet["positions"]),
            "points": points,
        }

    document = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": len(timestamps),
        "requested_hours": REPLAY_HOURS,
        "universe_items": len(series_by_item),
        "fetch_errors": errors,
        "assumptions": [
            "Read-only replay; never touches live wallet state.",
            "Uses 1-hour Wiki bars, so 5-minute flow is approximated from hourly volume and trailing activity.",
            "Passive fills remain the same deterministic expected-fill model used by the paper engine; this is diagnostic, not a claim about real GE queue fills.",
            "Universe is bounded to currently relevant/high-activity items, so results are a strategy diagnostic rather than an exhaustive historical backtest.",
        ],
        "wallets": results,
    }
    write_json(OUT, document)
    print("72h replay " + " ".join(f"{k}={v['return_pct']:+.2%}" for k, v in results.items()))
    return document


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run(force=args.force)
