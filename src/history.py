from datetime import datetime, timezone
from math import log
from statistics import mean, pstdev, median
from .config import HISTORY_EVERY_HOURS, HISTORY_ITEMS
from .market import timeseries

def _mid(x):
    v=[n for n in (x.get("avgHighPrice"),x.get("avgLowPrice")) if isinstance(n,(int,float)) and n>0]
    return sum(v)/len(v) if v else None

def _metrics(rows):
    pts=[(_mid(x),int(x.get("highPriceVolume",0) or 0)+int(x.get("lowPriceVolume",0) or 0)) for x in rows]
    pts=[x for x in pts if x[0]]
    if len(pts)<4:return {}
    prices=[x[0] for x in pts]; rets=[log(b/a) for a,b in zip(prices,prices[1:]) if a>0 and b>0]
    mu=mean(prices); sd=pstdev(prices) or 1; peak=prices[0]; mdd=0
    for p in prices:peak=max(peak,p);mdd=min(mdd,p/peak-1)
    recent=prices[-min(7,len(prices)):]; drift=(recent[-1]/recent[0]-1) if len(recent)>1 else 0
    noise=pstdev(rets) if len(rets)>1 else 0; projection=max(-.12,min(.12,drift));confidence=max(0,min(1,1-noise*12))
    return {"points":len(prices),"mean_price":round(mu,2),"zscore":round((prices[-1]-mu)/sd,3),"volatility_1h":round(noise,6),"max_drawdown":round(mdd,6),"median_hourly_volume":int(median(x[1] for x in pts)),"trend_6h":round(drift,6),"projected_6h_pct":round(projection,6),"projection_confidence":round(confidence,3)}

def historical_context(common_rows):
    now=datetime.now(timezone.utc)
    if now.hour % HISTORY_EVERY_HOURS:return {"status":"not_scheduled","items":{}}
    out={}
    for c in common_rows[:HISTORY_ITEMS]:
        try:out[str(c["id"])]={"name":c["name"],**_metrics(timeseries(c["id"],"1h"))}
        except Exception as e:out[str(c["id"])]={"name":c["name"],"error":type(e).__name__}
    return {"status":"ok","generated_at":now.isoformat(),"items":out}
