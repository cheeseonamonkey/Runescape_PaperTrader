from math import ceil, floor, log1p
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


def liquidation_unit(low, profile):
    gross = floor(max(0, low) * (1 - profile.liquidation_slippage))
    return max(0, gross - ge_tax(gross))


def entry_liquidation_baseline(entry_price, profile):
    """Approximate the immediate liquidation mark that existed when a passive entry was booked.

    This separates market movement from the simulator's own tax/slippage haircut. It is used
    for stop-loss decisions; accounting still uses the true mark-to-liquidation value.
    """
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
        expected_value = complete * edge - inventory * adverse
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
        score = 100 * (
            profile.edge_weight * edge_signal
            + profile.momentum_weight * momentum_signal
            + profile.volume_accel_weight * accel_signal
            + profile.liquidity_weight * liquidity
            + profile.historical_weight * history_signal
        ) + 10 * freshness
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
            "risk_budget_pct": round(risk, 4), "historical_signal": round(history_signal, 4),
            "historical": history_row, "score": round(score, 3),
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
