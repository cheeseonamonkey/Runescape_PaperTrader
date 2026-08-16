from datetime import datetime, timezone
from .config import CFG
from .strategy import expected_unit_exit, mark_value

def utcnow(): return datetime.now(timezone.utc)
def fresh_portfolio(): return {"cash_gp":CFG.starting_gp,"positions":[],"realized_pnl_gp":0,"created_at":utcnow().isoformat()}
def portfolio_value(portfolio, latest): return portfolio["cash_gp"] + sum(mark_value(p, latest) for p in portfolio["positions"])

def close_positions(portfolio, latest):
    now=utcnow(); kept=[]; trades=[]
    for pos in portfolio["positions"]:
        low=latest.get(str(pos["item_id"]),{}).get("low")
        if not low: kept.append(pos); continue
        unit_exit=expected_unit_exit(low); roi=unit_exit/pos["entry_price"]-1; held_h=(now-datetime.fromisoformat(pos["opened_at"])).total_seconds()/3600; reason=None
        if roi>=CFG.take_profit: reason="take_profit"
        elif roi<=CFG.stop_loss: reason="stop_loss"
        elif held_h>=CFG.max_hold_hours: reason="max_hold"
        if not reason: kept.append(pos); continue
        proceeds=unit_exit*pos["qty"]; cost=pos["entry_price"]*pos["qty"]; pnl=proceeds-cost
        portfolio["cash_gp"]+=proceeds; portfolio["realized_pnl_gp"]+=pnl
        trades.append({"side":"SELL","item_id":pos["item_id"],"name":pos["name"],"qty":pos["qty"],"unit_price":unit_exit,"pnl_gp":pnl,"reason":reason,"at":now.isoformat()})
    portfolio["positions"]=kept; return trades

def open_positions(portfolio, candidates):
    trades=[]; occupied={p["item_id"] for p in portfolio["positions"]}; slots=CFG.max_positions-len(portfolio["positions"]); reserve=int(CFG.starting_gp*CFG.reserve_pct)
    for c in candidates:
        if slots<=0 or c["id"] in occupied: continue
        spendable=max(0,portfolio["cash_gp"]-reserve); budget=min(int(portfolio["cash_gp"]*CFG.max_position_pct),spendable)
        if budget<c["buy"]: continue
        qty=budget//c["buy"]
        if c.get("limit"): qty=min(qty,int(c["limit"]))
        if qty<=0: continue
        cost=qty*c["buy"]; portfolio["cash_gp"]-=cost
        pos={"item_id":c["id"],"name":c["name"],"qty":qty,"entry_price":c["buy"],"opened_at":utcnow().isoformat(),"entry_score":c["score"]}; portfolio["positions"].append(pos)
        trades.append({"side":"BUY","item_id":c["id"],"name":c["name"],"qty":qty,"unit_price":c["buy"],"cost_gp":cost,"reason":"ranked_candidate","at":pos["opened_at"]}); occupied.add(c["id"]); slots-=1
    return trades
