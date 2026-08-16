from datetime import datetime, timezone
from .config import CFG
from .strategy import liquidation_unit, mark_position

def utcnow(): return datetime.now(timezone.utc)
def fresh_portfolio(): return {"cash_gp": CFG.starting_gp, "positions": [], "realized_pnl_gp": 0, "created_at": utcnow().isoformat()}

def marked_positions(portfolio, latest):
    out=[]
    for p in portfolio["positions"]:
        m=mark_position(p, latest); out.append({**p, **m})
    return out

def portfolio_value(portfolio, latest):
    return portfolio["cash_gp"] + sum(x["value_gp"] for x in marked_positions(portfolio, latest))

def close_positions(portfolio, latest):
    now=utcnow(); kept=[]; trades=[]
    for pos in portfolio["positions"]:
        q=latest.get(str(pos["item_id"]),{}); low=q.get("low")
        if not low: kept.append(pos); continue
        unit_exit=liquidation_unit(low); roi=unit_exit/pos["entry_price"]-1
        held_h=(now-datetime.fromisoformat(pos["opened_at"])).total_seconds()/3600; reason=None
        thesis=pos.get("entry_expected_roi",0); momentum=pos.get("entry_momentum",0)
        if roi>=CFG.take_profit: reason="take_profit"
        elif roi<=CFG.stop_loss: reason="stop_loss"
        elif held_h>=CFG.soft_rotate_hours and roi < max(0.0015, thesis * 0.20) and momentum <= 0: reason="capital_rotation"
        elif held_h>=CFG.max_hold_hours: reason="max_hold"
        if not reason: kept.append(pos); continue
        proceeds=unit_exit*pos["qty"]; cost=pos["entry_price"]*pos["qty"]; pnl=proceeds-cost
        portfolio["cash_gp"]+=proceeds; portfolio["realized_pnl_gp"]+=pnl
        trades.append({"side":"SELL","item_id":pos["item_id"],"name":pos["name"],"qty":pos["qty"],"unit_price":unit_exit,"pnl_gp":pnl,"roi":round(roi,6),"held_hours":round(held_h,2),"reason":reason,"at":now.isoformat()})
    portfolio["positions"]=kept; return trades

def open_positions(portfolio, candidates, latest):
    trades=[]; occupied={p["item_id"] for p in portfolio["positions"]}; slots=CFG.max_positions-len(portfolio["positions"])
    equity=portfolio_value(portfolio, latest); reserve=max(int(CFG.starting_gp*CFG.reserve_pct), int(equity*CFG.reserve_pct))
    for c in candidates:
        if slots<=0 or c["id"] in occupied: continue
        spendable=max(0,portfolio["cash_gp"]-reserve)
        budget=min(int(equity*c["risk_budget_pct"]), spendable)
        if budget<c["passive_entry"]: continue
        qty=budget//c["passive_entry"]
        if c.get("limit"): qty=min(qty,int(c["limit"]))
        if qty<=0: continue
        cost=qty*c["passive_entry"]; portfolio["cash_gp"]-=cost; opened=utcnow().isoformat()
        pos={"item_id":c["id"],"name":c["name"],"qty":qty,"entry_price":c["passive_entry"],"opened_at":opened,"entry_score":c["score"],"entry_expected_roi":c["expected_roi"],"entry_momentum":c["momentum_5m_vs_1h"],"entry_fill_probability":c["fill_probability"],"risk_budget_pct":c["risk_budget_pct"]}
        portfolio["positions"].append(pos)
        trades.append({"side":"BUY","item_id":c["id"],"name":c["name"],"qty":qty,"unit_price":c["passive_entry"],"cost_gp":cost,"expected_roi":c["expected_roi"],"score":c["score"],"reason":"aggressive_ev_rank","at":opened})
        occupied.add(c["id"]); slots-=1
    return trades
