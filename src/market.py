import json
from urllib.request import Request, urlopen
from .config import USER_AGENT

BASE = "https://prices.runescape.wiki/api/v1/osrs"

def _get(path):
    req = Request(BASE + path, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=30) as r: return json.load(r)

def snapshot():
    latest = _get("/latest")["data"]
    hourly = _get("/1h")["data"]
    mapping = {str(x["id"]): x for x in _get("/mapping")}
    return latest, hourly, mapping
