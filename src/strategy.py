from math import ceil, floor, log1p
from time import time
from .config import GE_TAX_RATE, GE_TAX_CAP

def ge_tax(unit_sell:int)->int:return min(floor(unit_sell*GE_TAX_RATE),GE_TAX_CAP)
def _mid(row):
    v=[x for x in (row.get("avgHighPrice"),row.get("avgLowPrice")) if isinstance(x,(int,float)) and x>0]
    return sum(v)/len(v) if v else None
def _volume(row):return int(row.get("highPriceVolume",0) or 0)+int(row.get("lowPriceVolume",0) or 0)

def common_features(latest,five,hourly,mapping):
    now=int(time()); out=[]
    for item_id,p in latest.items():
        hi,lo=p.get("high"),p.get("low"); ht,lt=p.get("highTime"),p.get("lowTime")
        if not all((hi,lo,ht,lt)) or hi<=lo or lo<=0:continue
        f,h=five.get(item_id,{}),hourly.get(item_id,{})
        v5,v1=_volume(f),_volume(h); m5,m1=_mid(f),_mid(h)
        age=max(now-ht,now-lt)/60; mom=(m5/m1-1) if m5 and m1 else 0
        accel=min(5,max(-1,(v5*12/max(v1,1))-1)); turnover=v1*max(m1 or lo,1); liq=min(1,log1p(turnover)/19)
        meta=mapping.get(item_id,{})
        out.append({"id":int(item_id),"name":meta.get("name",f"Item {item_id}"),"members":bool(meta.get("members")),"limit":meta.get("limit"),"highalch":meta.get("highalch"),"high":hi,"low":lo,"spread_roi":round((hi-lo)/lo,6),"momentum_5m_vs_1h":round(mom,6),"volume_5m":v5,"volume_1h":v1,"volume_acceleration":round(accel,3),"turnover_gp_1h":int(turnover),"liquidity_score":round(liq,4),"quote_age_minutes":round(age,1)})
    return sorted(out,key=lambda x:x["turnover_gp_1h"],reverse=True)

def liquidation_unit(low,profile):
    gross=floor(low*(1-profile.liquidation_slippage));return max(0,gross-ge_tax(gross))

def wallet_candidates(common,profile,historical=None):
    hist=(historical or {}).get("items",{}); rows=[]
    for x in common:
        if x["quote_age_minutes"]>profile.quote_max_age_minutes or x["volume_1h"]<profile.min_hourly_volume or x["volume_5m"]<profile.min_5m_volume or x["spread_roi"]>profile.max_spread_roi:continue
        entry=max(1,ceil(x["low"]*(1+profile.passive_entry_penalty)));gross=max(1,floor(x["high"]*(1-profile.passive_exit_penalty)));exit_net=max(0,gross-ge_tax(gross))
        edge=exit_net-entry; raw_roi=edge/entry; freshness=max(0,1-x["quote_age_minutes"]/profile.quote_max_age_minutes);liq=x["liquidity_score"];mom=x["momentum_5m_vs_1h"];accel=x["volume_acceleration"]
        entry_fill=min(.97,max(.15,.28+.38*liq+.18*freshness+.08*min(1,x["volume_5m"]/70)));exit_fill=min(.98,max(.16,.28+.42*liq+.15*freshness+.06*max(-1,min(1,mom/.02))))
        complete=entry_fill*exit_fill;inventory=entry_fill*(1-exit_fill);adverse=entry*(.0025+.012*max(0,-mom)+.0025*(1-liq));ev=complete*edge-inventory*adverse;ev_roi=ev/entry
        if ev<profile.min_expected_edge_gp or ev_roi<profile.min_expected_roi:continue
        hs=hist.get(str(x["id"]),{});z=float(hs.get("zscore",0) or 0);htrend=float(hs.get("trend_6h",0) or 0);hist_signal=max(-1,min(1,(htrend/.04 if htrend else 0)-max(0,z-2)*.25))
        momsig=max(-1,min(1,mom/.03));accsig=max(-1,min(1,accel/2));edgesig=min(2,ev_roi/.01)
        score=100*(profile.edge_weight*edgesig+profile.momentum_weight*momsig+profile.volume_accel_weight*accsig+profile.liquidity_weight*liq+profile.historical_weight*hist_signal)+10*freshness
        risk=profile.base_position_pct*(.58+.80*liq+.32*max(0,momsig)+.20*max(0,accsig)+.15*max(0,hist_signal));risk=min(profile.max_position_pct,max(.025,risk))
        rows.append({**x,"passive_entry":entry,"passive_exit_net":exit_net,"edge_gp":round(edge,2),"raw_roi":round(raw_roi,6),"expected_edge_gp":round(ev,2),"expected_roi":round(ev_roi,6),"entry_fill_probability":round(entry_fill,4),"exit_fill_probability":round(exit_fill,4),"fill_probability":round(complete,4),"risk_budget_pct":round(risk,4),"historical_signal":round(hist_signal,4),"historical":hs,"score":round(score,3)})
    return sorted(rows,key=lambda x:x["score"],reverse=True)

def mark_position(position,latest,profile):
    q=latest.get(str(position["item_id"]),{});low=q.get("low") or position["entry_price"];unit=liquidation_unit(low,profile);value=unit*position["qty"];cost=position["entry_price"]*position["qty"]
    return {"unit_liquidation":unit,"value_gp":value,"unrealized_pnl_gp":value-cost,"unrealized_roi":(value/cost-1) if cost else 0}
