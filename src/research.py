from datetime import datetime, timezone
from urllib.parse import urlparse
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
                "title": item.findtext("title", "").strip(),
                "url": item.findtext("link", "").strip(),
                "published": item.findtext("pubDate", "").strip(),
                "source": "Jagex RSS",
                "evidence_class": "OFFICIAL",
            })
        return out
    except Exception as exc:
        return [{"error": type(exc).__name__, "source": "Jagex RSS"}]


def _evidence_for_url(url):
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        host = ""
    host = host.lower()
    if host == "oldschool.runescape.com" or host.endswith(".runescape.com"):
        return "OFFICIAL", "Jagex"
    if host == "oldschool.runescape.wiki" or host.endswith(".oldschool.runescape.wiki"):
        return "CONFIRMED_COMMUNITY", "OSRS Wiki"
    if host == "reddit.com" or host.endswith(".reddit.com"):
        return "COMMUNITY", "Reddit"
    return "COMMUNITY", host or "Web"


def _ddgs_search(queries):
    if not ENABLE_DDGS:
        return []
    try:
        from ddgs import DDGS
        rows, seen = [], set()
        for query in queries[:3]:
            for result in DDGS().text(query, max_results=5):
                url = result.get("href", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                evidence, source = _evidence_for_url(url)
                rows.append({
                    "title": result.get("title", ""),
                    "url": url,
                    "snippet": result.get("body", ""),
                    "query": query,
                    "source": source,
                    "evidence_class": evidence,
                })
        return rows[:12]
    except Exception as exc:
        return [{"error": type(exc).__name__, "source": "DDGS"}]


def _age_hours(value, now):
    try:
        return max(0, (now - datetime.fromisoformat(value)).total_seconds() / 3600)
    except (TypeError, ValueError):
        return None


def _queries(rows):
    if not rows:
        return ["Old School RuneScape economy update Jagex"]
    movers = sorted(rows, key=lambda row: abs(float(row.get("momentum_5m_vs_1h", 0) or 0)), reverse=True)
    flow = sorted(rows, key=lambda row: float(row.get("volume_acceleration", 0) or 0), reverse=True)
    names = []
    for row in movers[:2] + flow[:2]:
        name = row.get("name")
        if name and name not in names:
            names.append(name)
    queries = [f'OSRS "{name}" update' for name in names[:2]]
    queries.append("Old School RuneScape update economy Jagex")
    return queries[:3]


def deterministic_research(candidates, cached=None):
    now = datetime.now(timezone.utc)
    cached = cached if isinstance(cached, dict) else {}
    queries = _queries(candidates)
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
        "generated_at": now.isoformat(),
        "official": official,
        "search": search,
        "queries": queries,
        "search_status": search_status,
        "search_generated_at": search_generated_at,
        "search_error": search_error,
    }
