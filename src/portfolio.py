from datetime import datetime, timezone
from .config import STARTING_GP
from .strategy import liquidation_unit, mark_position

def utcnow():return datetime.now(timezone.utc)
def fresh_wallet(profile):return {"schema":1,"strategy_id":profile.slug,"cash_gp":STARTING_GP,"positions":[],"realized_pnl_gp":0,"created_at":utcnow().isoformat()}
def normalize_wallet(state,profile):
    if not isinstance(state,dict) or state.get("strategy_id")!=profile.slug:return fresh_wallet(profile)
    state.setdefault("schema",1);state.setdefault("cash_gp",STARTING_GP);state.setdefault("positions",[]);state.setdefault("realized_pnl_gp",0);return state
def marked_positions(wallet,latest,profile):return [{**p,**mark_position(p,latest,profile)} for p in wallet["positions"]]
def wallet_value(wallet,latest,profile):return wallet["cash_gp"]+sum(x["value_gp"] for x in marked_positions(wallet,latest,profile))

def close_positions(wallet,latest,profile):
    now=utcnow();kept=[];trades=[]
    for pos in wallet["positions"]:
        low=latest.get(str(pos["item_id"]),{}).get("low")
        if not low:kept.append(pos);continue
        unit=liquidation_unit(low,profile);roi=unit/pos["entry_price"]-1;held=(now-datetime.fromisoformat(pos["opened_at"])).total_seconds()/3600;reason=None
        thesis=pos.get("entry_expected_roi",0);momentum=pos.get("entry_momentum",0)
        if roi>=profile.take_profit:reason="take_profit"
        elif roi<=profile.stop_loss:reason="stop_loss"
        elif held>=profile.soft_rotate_hours and roi<max(.001,thesis*.20) and momentum<=0:reason="capital_rotation"
        elif held>=profile.max_hold_hours:reason="max_hold"
        if not reason:kept.append(pos);continue
        proceeds=unit*pos["qty"];cost=pos["entry_price"]*pos["qty"];pnl=proceeds-cost;wallet["cash_gp"]+=proceeds;wallet["realized_pnl_gp"]+=pnl
        trades.append({"wallet":profile.slug,"side":"SELL","item_id":pos["item_id"],"name":pos["name"],"qty":pos["qty"],"unit_price":unit,"pnl_gp":pnl,"roi":round(roi,6),"held_hours":round(held,2),"reason":reason,"at":now.isoformat()})
    wallet["positions"]=kept;return trades

def open_positions(wallet,candidates,latest,profile):
    trades=[];occupied={p["item_id"] for p in wallet["positions"]};slots=profile.max_positions-len(wallet["positions"]);equity=wallet_value(wallet,latest,profile);reserve=max(int(STARTING_GP*profile.reserve_pct),int(equity*profile.reserve_pct))
    for c in candidates:
        if slots<=0 or c["id"] in occupied:continue
        spendable=max(0,wallet["cash_gp"]-reserve);budget=min(int(equity*c["risk_budget_pct"]),spendable)
        if budget<c["passive_entry"]:continue
        order_qty=budget//c["passive_entry"]
        if c.get("limit"):order_qty=min(order_qty,int(c["limit"]))
        qty=int(order_qty*c.get("entry_fill_probability",1))
        if qty<=0:continue
        cost=qty*c["passive_entry"];wallet["cash_gp"]-=cost;opened=utcnow().isoformat();pos={"item_id":c["id"],"name":c["name"],"qty":qty,"entry_price":c["passive_entry"],"opened_at":opened,"entry_score":c["score"],"entry_expected_roi":c["expected_roi"],"entry_momentum":c["momentum_5m_vs_1h"],"entry_fill_probability":c["fill_probability"],"risk_budget_pct":c["risk_budget_pct"]};wallet["positions"].append(pos);occupied.add(c["id"]);slots-=1
        trades.append({"wallet":profile.slug,"side":"BUY","item_id":c["id"],"name":c["name"],"qty":qty,"order_qty":order_qty,"fill_model":"expected_quantity","unit_price":c["passive_entry"],"cost_gp":cost,"expected_roi":c["expected_roi"],"score":c["score"],"reason":f"{profile.slug}_rank","at":opened})
    return trades
