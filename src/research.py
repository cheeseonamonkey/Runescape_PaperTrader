from datetime import datetime, timezone
from urllib.request import Request, urlopen
from .config import USER_AGENT, ENABLE_DDGS, DDGS_EVERY_HOURS

JAGEX_RSS = "https://services.runescape.com/m=news/latest_news.rss?oldschool=true"

def _rss_headlines(limit=8):
    try:
        import xml.etree.ElementTree as ET
        req=Request(JAGEX_RSS, headers={"User-Agent":USER_AGENT})
        with urlopen(req, timeout=20) as r: root=ET.fromstring(r.read())
        out=[]
        for item in root.findall(".//item")[:limit]:
            out.append({"title":item.findtext("title","").strip(),"url":item.findtext("link","").strip(),"published":item.findtext("pubDate","").strip(),"source":"Jagex RSS","evidence_class":"OFFICIAL"})
        return out
    except Exception as e:
        return [{"error":type(e).__name__,"source":"Jagex RSS"}]

def _ddgs_search(queries):
    if not ENABLE_DDGS or datetime.now(timezone.utc).hour % DDGS_EVERY_HOURS: return []
    try:
        from ddgs import DDGS
        rows=[]
        for q in queries[:3]:
            for r in DDGS().text(q, max_results=4):
                rows.append({"title":r.get("title",""),"url":r.get("href",""),"snippet":r.get("body",""),"query":q,"source":"DDGS","evidence_class":"COMMUNITY"})
        return rows[:10]
    except Exception as e:
        return [{"error":type(e).__name__,"source":"DDGS"}]

def deterministic_research(candidates):
    names=[c["name"] for c in candidates[:4]]
    queries=[f'OSRS "{n}" update reddit' for n in names[:2]] + (["Old School RuneScape economy update Jagex"] if names else [])
    return {"generated_at":datetime.now(timezone.utc).isoformat(),"official":_rss_headlines(),"search":_ddgs_search(queries),"queries":queries}
