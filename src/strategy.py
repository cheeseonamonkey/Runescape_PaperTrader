from math import ceil, floor, log1p
from time import time
from .config import CFG

def ge_tax(unit_sell: int) -> int:
    return min(floor(unit_sell * CFG.ge_tax_rate), CFG.ge_tax_cap)

def liquidation_unit(low: int) -> int:
    gross = floor(low * (1 - CFG.liquidation_slippage))
    return max(0, gross - ge_tax(gross))

def passive_entry(low: int) -> int:
    return max(1, ceil(low * (1 + CFG.passive_entry_penalty)))

def passive_exit(high: int) -> int:
    gross = max(1, floor(high * (1 - CFG.passive_exit_penalty)))
    return max(0, gross - ge_tax(gross))

def _mid(row):
    hi, lo = row.get("avgHighPrice"), row.get("avgLowPrice")
    vals = [x for x in (hi, lo) if isinstance(x, (int, float)) and x > 0]
    return sum(vals) / len(vals) if vals else None

def _volume(row):
    return int(row.get("highPriceVolume", 0) or 0) + int(row.get("lowPriceVolume", 0) or 0)

def candidate_rows(latest, five, hourly, mapping):
    now = int(time()); rows = []
    for item_id, p in latest.items():
        hi, lo = p.get("high"), p.get("low"); hi_t, lo_t = p.get("highTime"), p.get("lowTime")
        f = five.get(item_id, {}); h = hourly.get(item_id, {}); meta = mapping.get(item_id, {})
        if not all((hi, lo, hi_t, lo_t)) or hi <= lo or lo <= 0: continue
        age = max(now - hi_t, now - lo_t) / 60
        vol5, vol1 = _volume(f), _volume(h)
        if age > CFG.quote_max_age_minutes or vol1 < CFG.min_hourly_volume or vol5 < CFG.min_5m_volume: continue
        entry, exit_net = passive_entry(lo), passive_exit(hi)
        edge = exit_net - entry; raw_roi = edge / entry
        spread_roi = (hi - lo) / lo
        if spread_roi > CFG.max_spread_roi: continue
        mid5, mid1 = _mid(f), _mid(h)
        momentum = (mid5 / mid1 - 1) if mid5 and mid1 else 0.0
        vol_accel = min(4.0, max(-1.0, (vol5 * 12 / max(vol1, 1)) - 1))
        turnover = vol1 * max(mid1 or lo, 1)
        liquidity = min(1.0, log1p(turnover) / 19.0)
        freshness = max(0.0, 1 - age / CFG.quote_max_age_minutes)
        entry_fill = min(0.96, max(0.20, 0.30 + 0.35 * liquidity + 0.18 * freshness + 0.10 * min(1, vol5 / 80)))
        exit_fill = min(0.97, max(0.20, 0.28 + 0.40 * liquidity + 0.16 * freshness + 0.05 * max(-1, min(1, momentum / 0.02))))
        completion_prob = entry_fill * exit_fill
        inventory_prob = entry_fill * (1 - exit_fill)
        adverse = entry * (0.003 + 0.010 * max(0, -momentum) + 0.002 * (1 - liquidity))
        expected_edge = completion_prob * edge - inventory_prob * adverse
        expected_roi = expected_edge / entry
        if expected_edge < CFG.min_expected_edge_gp or expected_roi < CFG.min_expected_roi: continue
        momentum_signal = max(-0.03, min(0.03, momentum)) / 0.03
        accel_signal = max(-1.0, min(1.0, vol_accel / 2))
        edge_signal = min(2.0, expected_roi / 0.01)
        score = 100 * (CFG.edge_weight * edge_signal + CFG.momentum_weight * momentum_signal + CFG.volume_accel_weight * accel_signal + CFG.liquidity_weight * liquidity) + 12 * freshness
        risk_budget = CFG.base_position_pct * (0.65 + 0.75 * liquidity + 0.35 * max(0, momentum_signal) + 0.25 * max(0, accel_signal))
        risk_budget = min(CFG.max_position_pct, max(0.035, risk_budget))
        rows.append({"id": int(item_id), "name": meta.get("name", f"Item {item_id}"), "members": bool(meta.get("members")), "high": hi, "low": lo, "passive_entry": entry, "passive_exit_net": exit_net, "edge_gp": round(edge, 2), "raw_roi": round(raw_roi, 6), "expected_edge_gp": round(expected_edge, 2), "expected_roi": round(expected_roi, 6), "spread_roi": round(spread_roi, 6), "momentum_5m_vs_1h": round(momentum, 6), "volume_5m": vol5, "volume_1h": vol1, "volume_acceleration": round(vol_accel, 3), "turnover_gp_1h": int(turnover), "liquidity_score": round(liquidity, 4), "entry_fill_probability": round(entry_fill, 4), "exit_fill_probability": round(exit_fill, 4), "fill_probability": round(completion_prob, 4), "quote_age_minutes": round(age, 1), "limit": meta.get("limit"), "highalch": meta.get("highalch"), "risk_budget_pct": round(risk_budget, 4), "score": round(score, 3)})
    return sorted(rows, key=lambda x: x["score"], reverse=True)

def mark_position(position, latest):
    p = latest.get(str(position["item_id"]), {})
    low = p.get("low") or position["entry_price"]
    unit = liquidation_unit(low)
    value = unit * position["qty"]
    cost = position["entry_price"] * position["qty"]
    return {"unit_liquidation": unit, "value_gp": value, "unrealized_pnl_gp": value - cost, "unrealized_roi": (value / cost - 1) if cost else 0}
