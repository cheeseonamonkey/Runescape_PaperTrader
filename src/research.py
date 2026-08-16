from datetime import datetime, timezone
from urllib.request import Request, urlopen
from .config import USER_AGENT, ENABLE_DDGS, DDGS_EVERY_HOURS

JAGEX_RSS = "https://services.runescape.com/m=news/latest_news.rss?oldschool=true"


def _rss_headlines(limit=8):
    try:
        import xml.etree.ElementTree as ET
        req = Request(JAGEX_RSS, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=20) as response:
            root = ET.fromstring(response.read())
        out = []
        for item in root.findall(".//item")[:limit]:
            out.append({
                "title": item.findtext("title", "").strip(), "url": item.findtext("link", "").strip(),
                "published": item.findtext("pubDate", "").strip(), "source": "Jagex RSS", "evidence_class": "OFFICIAL",
            })
        return out
    except Exception as exc:
        return [{"error": type(exc).__name__, "source": "Jagex RSS"}]


def _ddgs_search(queries):
    if not ENABLE_DDGS:
        return []
    try:
        from ddgs import DDGS
        rows = []
        for query in queries[:3]:
            for result in DDGS().text(query, max_results=4):
                rows.append({
                    "title": result.get("title", ""), "url": result.get("href", ""), "snippet": result.get("body", ""),
                    "query": query, "source": "DDGS", "evidence_class": "COMMUNITY",
                })
        return rows[:10]
    except Exception as exc:
        return [{"error": type(exc).__name__, "source": "DDGS"}]


def _age_hours(value, now):
    try:
        return max(0, (now - datetime.fromisoformat(value)).total_seconds() / 3600)
    except (TypeError, ValueError):
        return None


def deterministic_research(candidates, cached=None):
    now = datetime.now(timezone.utc)
    cached = cached if isinstance(cached, dict) else {}
    names = [candidate["name"] for candidate in candidates[:4]]
    queries = [f'OSRS "{name}" update reddit' for name in names[:2]] + (["Old School RuneScape economy update Jagex"] if names else [])
    official = _rss_headlines()

    search = cached.get("search", []) if isinstance(cached.get("search"), list) else []
    search_generated_at = cached.get("search_generated_at")
    search_age = _age_hours(search_generated_at, now)
    refresh_due = ENABLE_DDGS and (search_age is None or search_age >= DDGS_EVERY_HOURS)
    search_status = "disabled" if not ENABLE_DDGS else "cached"
    search_error = None

    if refresh_due:
        fresh = _ddgs_search(queries)
        only_error = bool(fresh) and all(row.get("error") for row in fresh)
        if only_error and search:
            search_status = "stale_cache"
            search_error = fresh[0].get("error")
        else:
            search = fresh
            search_generated_at = now.isoformat()
            search_status = "refreshed" if not only_error else "error"
            if only_error:
                search_error = fresh[0].get("error")

    return {
        "generated_at": now.isoformat(), "official": official, "search": search, "queries": queries,
        "search_status": search_status, "search_generated_at": search_generated_at, "search_error": search_error,
    }
