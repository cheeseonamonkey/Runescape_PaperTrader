from math import floor, log10
from time import time
from .config import CFG

def ge_tax(unit_sell: int) -> int:
    return min(floor(unit_sell * CFG.ge_tax_rate), CFG.ge_tax_cap)

def expected_unit_exit(low: int) -> int:
    return max(0, floor(low * (1 - CFG.slippage_pct)) - ge_tax(low))

def candidate_rows(latest, hourly, mapping):
    now = int(time()); rows = []
    for item_id, p in latest.items():
        hi, lo = p.get("high"), p.get("low"); hi_t, lo_t = p.get("highTime"), p.get("lowTime")
        h = hourly.get(item_id, {}); meta = mapping.get(item_id, {})
        if not all((hi, lo, hi_t, lo_t)) or hi <= 0 or lo <= 0 or hi <= lo: continue
        age = max(now - hi_t, now - lo_t) / 60
        volume = int(h.get("highPriceVolume", 0) or 0) + int(h.get("lowPriceVolume", 0) or 0)
        if age > CFG.quote_max_age_minutes or volume < CFG.min_hourly_volume: continue
        buy = hi; exit_value = expected_unit_exit(lo); edge = exit_value - buy; edge_roi = edge / buy; spread_roi = (hi - lo) / lo
        if edge < CFG.min_edge_gp or edge_roi < CFG.min_edge_roi or spread_roi > CFG.max_spread_roi: continue
        score = edge_roi * 100 + min(3.0, log10(max(volume, 1)) / 2) + max(0, 1 - age / CFG.quote_max_age_minutes)
        rows.append({"id":int(item_id),"name":meta.get("name",f"Item {item_id}"),"buy":buy,"sell":lo,"edge_gp":edge,"edge_roi":round(edge_roi,6),"spread_roi":round(spread_roi,6),"hourly_volume":volume,"quote_age_minutes":round(age,1),"limit":meta.get("limit"),"score":round(score,4)})
    return sorted(rows, key=lambda x:x["score"], reverse=True)

def mark_value(position, latest):
    p = latest.get(str(position["item_id"]), {}); low = p.get("low") or position["entry_price"]
    return expected_unit_exit(low) * position["qty"]
