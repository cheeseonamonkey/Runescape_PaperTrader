import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .config import USER_AGENT

BASE = "https://prices.runescape.wiki/api/v1/osrs"

def _get(path, params=None):
    url=BASE+path+(("?" + urlencode(params)) if params else "")
    req=Request(url, headers={"User-Agent":USER_AGENT,"Accept":"application/json"})
    with urlopen(req, timeout=30) as r:return json.load(r)

def snapshot():
    latest=_get("/latest")["data"]
    five=_get("/5m")["data"]
    hourly=_get("/1h")["data"]
    mapping={str(x["id"]):x for x in _get("/mapping")}
    return latest,five,hourly,mapping

def timeseries(item_id, timestep="1h"):
    return _get("/timeseries", {"id":int(item_id),"timestep":timestep}).get("data",[])
