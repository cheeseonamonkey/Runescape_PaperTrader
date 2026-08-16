from math import ceil, floor, log1p
from statistics import median, pstdev
from time import time
from .config import GE_TAX_RATE, GE_TAX_CAP


def ge_tax(unit_sell: int) -> int:
    return min(floor(max(0, unit_sell) * GE_TAX_RATE), GE_TAX_CAP)


def _mid(row):
    values = [x for x in (row.get("avgHighPrice"), row.get("avgLowPrice")) if isinstance(x, (int, float)) and x > 0]
    return sum(values) / len(values) if values else None


def _volume(row):
    return int(row.get("highPriceVolume", 0) or 0) + int(row.get("lowPriceVolume", 0) or 0)


def common_features(latest, five, hourly, mapping):
    now = int(time())
    out = []
    for item_id, price in latest.items():
        hi, lo = price.get("high"), price.get("low")
        high_time, low_time = price.get("highTime"), price.get("lowTime")
        if not all((hi, lo, high_time, low_time)) or hi <= lo or lo <= 0:
            continue
        five_row, hour_row = five.get(item_id, {}), hourly.get(item_id, {})
        volume_5m, volume_1h = _volume(five_row), _volume(hour_row)
        mid_5m, mid_1h = _mid(five_row), _mid(hour_row)
        age = max(0.0, max(now - high_time, now - low_time) / 60)
        momentum = (mid_5m / mid_1h - 1) if mid_5m and mid_1h else 0
        accel = min(5, max(-1, (volume_5m * 12 / max(volume_1h, 1)) - 1))
        turnover = volume_1h * max(mid_1h or lo, 1)
        liquidity = min(1, log1p(turnover) / 19)
        meta = mapping.get(item_id, {})
        out.append({
            "id": int(item_id), "name": meta.get("name", f"Item {item_id}"),
            "members": bool(meta.get("members")), "limit": meta.get("limit"), "highalch": meta.get("highalch"),
            "high": hi, "low": lo, "spread_roi": round((hi - lo) / lo, 6),
            "momentum_5m_vs_1h": round(momentum, 6), "volume_5m": volume_5m, "volume_1h": volume_1h,
            "volume_acceleration": round(accel, 3), "turnover_gp_1h": int(turnover),
            "liquidity_score": round(liquidity, 4), "quote_age_minutes": round(age, 1),
        })
    return sorted(out, key=lambda x: x["turnover_gp_1h"], reverse=True)


def economy_metrics(rows):
    """Cross-sectional market diagnostics. These are short-run conditions, not a CPI/inflation claim."""
    if not rows:
        return {
            "advancers": 0, "decliners": 0, "flat": 0, "breadth": 0,
            "turnover_weighted_price_pressure": 0, "momentum_dispersion": 0,
            "median_spread": 0, "median_liquidity": 0, "median_volume_acceleration": 0,
            "top10_turnover_share": 0, "turnover_hhi": 0, "active_share": 0,
        }
    eps = .0001
    adv = sum(1 for r in rows if r["momentum_5m_vs_1h"] > eps)
    dec = sum(1 for r in rows if r["momentum_5m_vs_1h"] < -eps)
    flat = len(rows) - adv - dec
    breadth = (adv - dec) / max(1, adv + dec)
    turnover_total = sum(max(0, r["turnover_gp_1h"]) for r in rows)
    weighted_pressure = sum(
        max(-.08, min(.08, r["momentum_5m_vs_1h"])) * max(0, r["turnover_gp_1h"])
        for r in rows
    ) / max(1, turnover_total)
    shares = [max(0, r["turnover_gp_1h"]) / turnover_total for r in rows] if turnover_total else []
    top10 = sum(shares[:10]) if shares else 0
    hhi = sum(s * s for s in shares) if shares else 0
    momenta = [r["momentum_5m_vs_1h"] for r in rows]
    active_share = sum(1 for r in rows if r["volume_acceleration"] > 0) / len(rows)
    return {
        "advancers": adv, "decliners": dec, "flat": flat,
        "breadth": round(breadth, 4),
        "turnover_weighted_price_pressure": round(weighted_pressure, 6),
        "momentum_dispersion": round(pstdev(momenta) if len(momenta) > 1 else 0, 6),
        "median_spread": round(median(r["spread_roi"] for r in rows), 6),
        "median_liquidity": round(median(r["liquidity_score"] for r in rows), 4),
        "median_volume_acceleration": round(median(r["volume_acceleration"] for r in rows), 3),
        "top10_turnover_share": round(top10, 4),
        "turnover_hhi": round(hhi, 6),
        "active_share": round(active_share, 4),
    }


def liquidation_unit(low, profile):
    gross = floor(max(0, low) * (1 - profile.liquidation_slippage))
    return max(0, gross - ge_tax(gross))


def entry_liquidation_baseline(entry_price, profile):
    inferred_low = max(1, floor(entry_price / (1 + profile.passive_entry_penalty)))
    return max(1, liquidation_unit(inferred_low, profile))


def wallet_candidates(common, profile, historical=None):
    hist = (historical or {}).get("items", {})
    rows = []
    for x in common:
        if (
            x["quote_age_minutes"] > profile.quote_max_age_minutes
            or x["volume_1h"] < profile.min_hourly_volume
            or x["volume_5m"] < profile.min_5m_volume
            or x["spread_roi"] > profile.max_spread_roi
        ):
            continue
        entry = max(1, ceil(x["low"] * (1 + profile.passive_entry_penalty)))
        gross = max(1, floor(x["high"] * (1 - profile.passive_exit_penalty)))
        exit_net = max(0, gross - ge_tax(gross))
        edge = exit_net - entry
        raw_roi = edge / entry
        freshness = max(0, 1 - x["quote_age_minutes"] / profile.quote_max_age_minutes)
        liquidity = x["liquidity_score"]
        momentum = x["momentum_5m_vs_1h"]
        accel = x["volume_acceleration"]
        entry_fill = min(.97, max(.15, .28 + .38 * liquidity + .18 * freshness + .08 * min(1, x["volume_5m"] / 70)))
        exit_fill = min(.98, max(.16, .28 + .42 * liquidity + .15 * freshness + .06 * max(-1, min(1, momentum / .02))))
        complete = entry_fill * exit_fill
        inventory = entry_fill * (1 - exit_fill)
        adverse = entry * (.0025 + .012 * max(0, -momentum) + .0025 * (1 - liquidity))
        gross_capture_ev = complete * edge
        inventory_risk_ev = inventory * adverse
        expected_value = gross_capture_ev - inventory_risk_ev
        expected_roi = expected_value / entry
        if expected_value < profile.min_expected_edge_gp or expected_roi < profile.min_expected_roi:
            continue
        history_row = hist.get(str(x["id"]), {})
        zscore = float(history_row.get("zscore", 0) or 0)
        history_trend = float(history_row.get("trend_6h", 0) or 0)
        history_signal = max(-1, min(1, (history_trend / .04 if history_trend else 0) - max(0, zscore - 2) * .25))
        momentum_signal = max(-1, min(1, momentum / .03))
        accel_signal = max(-1, min(1, accel / 2))
        edge_signal = min(2, expected_roi / .01)
        score_components = {
            "edge": 100 * profile.edge_weight * edge_signal,
            "momentum": 100 * profile.momentum_weight * momentum_signal,
            "flow": 100 * profile.volume_accel_weight * accel_signal,
            "liquidity": 100 * profile.liquidity_weight * liquidity,
            "history": 100 * profile.historical_weight * history_signal,
            "freshness": 10 * freshness,
        }
        score = sum(score_components.values())
        risk = profile.base_position_pct * (
            .58 + .80 * liquidity + .32 * max(0, momentum_signal) + .20 * max(0, accel_signal) + .15 * max(0, history_signal)
        )
        risk = min(profile.max_position_pct, max(.025, risk))
        rows.append({
            **x,
            "passive_entry": entry, "passive_exit_net": exit_net, "edge_gp": round(edge, 2),
            "raw_roi": round(raw_roi, 6), "expected_edge_gp": round(expected_value, 2),
            "expected_roi": round(expected_roi, 6), "entry_fill_probability": round(entry_fill, 4),
            "exit_fill_probability": round(exit_fill, 4), "fill_probability": round(complete, 4),
            "inventory_probability": round(inventory, 4), "adverse_selection_unit_gp": round(adverse, 2),
            "spread_capture_ev_gp": round(gross_capture_ev, 2), "inventory_risk_ev_gp": round(inventory_risk_ev, 2),
            "risk_budget_pct": round(risk, 4), "historical_signal": round(history_signal, 4),
            "historical": history_row,
            "score_components": {k: round(v, 3) for k, v in score_components.items()},
            "score": round(score, 3),
        })
    return sorted(rows, key=lambda x: x["score"], reverse=True)


def mark_position(position, latest, profile):
    quote = latest.get(str(position["item_id"]), {})
    low = quote.get("low") or position["entry_price"]
    unit = liquidation_unit(low, profile)
    value = unit * position["qty"]
    cost = position["entry_price"] * position["qty"]
    baseline = max(1, int(position.get("entry_liquidation_unit") or entry_liquidation_baseline(position["entry_price"], profile)))
    return {
        "unit_liquidation": unit,
        "value_gp": value,
        "unrealized_pnl_gp": value - cost,
        "unrealized_roi": (value / cost - 1) if cost else 0,
        "market_move_roi": unit / baseline - 1,
    }
