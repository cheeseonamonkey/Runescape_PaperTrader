import json, os, re
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from datetime import datetime, timezone
from .config import OPENROUTER_MODEL, OPENROUTER_FREE_MODEL, OPENROUTER_SUBAGENT_MODEL, ENABLE_WEB_RESEARCH, ENABLE_SUBAGENT, ENABLE_FREE_AUX, FREE_AUX_PASSES

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
SYSTEM = """You are the qualitative research sidecar for an OSRS economy terminal running two independent paper-trading wallets. Never calculate P&L, ROI, tax, sizing, or prices. Deterministic code supplies those. Interpret microstructure, liquidity, momentum, volume acceleration, catalyst risk, adverse selection, regime shifts, community narratives, historical context, and opportunity cost. Compare Velocity (flow/momentum/high turnover) with Market Maker (spread/liquidity/completion quality). Distinguish OFFICIAL, CONFIRMED_COMMUNITY, COMMUNITY, RUMOR, MODEL_INFERENCE. Prefer Jagex/Wiki evidence. Reddit/community is sentiment evidence, not fact. Return one compact JSON object only with keys market_mood, regime, summary, notable_events, wallet_notes, research_summary, watchlist. Do not copy the input back. Do not invent sources."""
JSON_OBJECT = {"type": "json_object"}
EVIDENCE = {"OFFICIAL", "CONFIRMED_COMMUNITY", "COMMUNITY", "RUMOR", "MODEL_INFERENCE"}


def _text(value, limit=1200):
    value = "" if value is None else str(value)
    return value[:limit]


def _list_of_text(value, limit=8, item_limit=500):
    if not isinstance(value, list):
        return []
    return [_text(item, item_limit) for item in value[:limit] if item not in (None, "")]


def _extract(text):
    if isinstance(text, list):
        text = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in text)
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ValueError("No JSON object")
        return json.loads(match.group(0))


def _normalize_event(event):
    if not isinstance(event, dict):
        return None
    evidence = str(event.get("evidence_class") or event.get("type") or "MODEL_INFERENCE").upper()
    if evidence not in EVIDENCE:
        evidence = "MODEL_INFERENCE"
    out = {
        "title": _text(event.get("title") or "Untitled event", 240),
        "evidence_class": evidence,
        "explanation": _text(event.get("explanation") or event.get("reason") or "", 700),
        "source": _text(event.get("source") or "", 180),
        "url": _text(event.get("url") or "", 600),
        "published": _text(event.get("published") or "", 100),
        "affected_items": _list_of_text(event.get("affected_items"), 8, 120),
    }
    for key in ("confidence", "market_relevance"):
        try:
            out[key] = max(0.0, min(1.0, float(event.get(key))))
        except (TypeError, ValueError):
            out[key] = None
    return out


def _wallet_notes(value):
    if isinstance(value, list):
        return _list_of_text(value, 8, 700)
    if isinstance(value, dict):
        notes = []
        for wallet, detail in list(value.items())[:4]:
            if isinstance(detail, str):
                notes.append(f"{wallet}: {_text(detail, 600)}")
            elif isinstance(detail, dict):
                summary = detail.get("summary") or detail.get("thesis") or detail.get("note")
                if summary:
                    notes.append(f"{wallet}: {_text(summary, 600)}")
        return notes
    return []


def normalize_intelligence(raw):
    raw = raw if isinstance(raw, dict) else {}
    events = []
    for event in raw.get("notable_events", []) if isinstance(raw.get("notable_events"), list) else []:
        normalized = _normalize_event(event)
        if normalized:
            events.append(normalized)
    return {
        "market_mood": _text(raw.get("market_mood") or "unknown", 700),
        "regime": _text(raw.get("regime") or "unknown", 900),
        "summary": _text(raw.get("summary") or "", 1600),
        "notable_events": events[:8],
        "wallet_notes": _wallet_notes(raw.get("wallet_notes")),
        "research_summary": _text(raw.get("research_summary") or "", 1200),
        "watchlist": _list_of_text(raw.get("watchlist"), 12, 180),
    }


def _call(key, model, messages, tools=None, max_tokens=1600, timeout=120, json_mode=False):
    body = {"model": model, "messages": messages, "temperature": .18, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    if json_mode:
        body["response_format"] = JSON_OBJECT
        body["plugins"] = [{"id": "response-healing"}]
    req = Request(ENDPOINT, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/cheeseonamonkey/Runescape_PaperTrader", "X-Title": "OSRS PaperTrader",
    })
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        error = RuntimeError(f"OpenRouter HTTP {exc.code}")
        error.http_status = exc.code
        raise error from exc


def _normalize_aux(kind, value):
    value = value if isinstance(value, dict) else {}
    if kind == "analyst_critique":
        return {"summary": _text(value.get("summary"), 700), "concerns": _list_of_text(value.get("concerns"), 6, 400), "confidence": _text(value.get("confidence"), 80)}
    if kind == "wallet_red_team":
        return {"velocity": _list_of_text(value.get("velocity"), 5, 420), "market_maker": _list_of_text(value.get("market_maker"), 5, 420)}
    if kind == "news_triage":
        return {"important": _list_of_text(value.get("important"), 8, 300), "probably_noise": _list_of_text(value.get("probably_noise"), 8, 300)}
    return value


def _free_aux(key, context, primary):
    if not ENABLE_FREE_AUX or FREE_AUX_PASSES < 1:
        return []
    jobs = [
        ("analyst_critique", "Critique the primary OSRS market analysis. Find unsupported certainty, stale catalysts, narrative-following, missing counterarguments or semantic mistakes. No arithmetic. Return JSON {summary:string, concerns:[string], confidence:string}.", primary),
        ("wallet_red_team", "Red-team both supplied wallet theses. Explain why Velocity and Market Maker could each be wrong in current conditions, focusing on liquidity, adverse selection, regime mismatch and opportunity cost. No arithmetic. Return JSON {velocity:[string], market_maker:[string]}.", context.get("wallets", {})),
        ("news_triage", "Review supplied deterministic research only. Classify what deserves attention versus noise/repetition. Do not browse and do no arithmetic. Return JSON {important:[string], probably_noise:[string]}.", context.get("deterministic_research", {})),
    ][:FREE_AUX_PASSES]
    out = []
    for kind, prompt, payload in jobs:
        try:
            response = _call(key, OPENROUTER_FREE_MODEL, [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(payload, separators=(",", ":"))}], max_tokens=420, timeout=60, json_mode=True)
            result = _normalize_aux(kind, _extract(response["choices"][0]["message"]["content"]))
            out.append({"kind": kind, "status": "ok", "model": response.get("model", OPENROUTER_FREE_MODEL), "result": result})
        except Exception as exc:
            out.append({"kind": kind, "status": "unavailable", "error": type(exc).__name__})
    return out


def free_quality_critique(report):
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return {"status": "disabled"}
    prompt = "You are a software reliability reviewer. Critique this OSRS paper-trader test report. Identify likely hidden bugs, brittle assumptions, missing tests, suspicious metrics, and one or two highest-value follow-up experiments. Be concise. Do not suggest changing production state. Return JSON {summary:string, risks:[string], missing_tests:[string], experiments:[string]}."
    try:
        response = _call(key, OPENROUTER_FREE_MODEL, [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(report, separators=(",", ":"))}], max_tokens=700, timeout=75, json_mode=True)
        result = _extract(response["choices"][0]["message"]["content"])
        return {"status": "ok", "model": response.get("model", OPENROUTER_FREE_MODEL), "result": result}
    except Exception as exc:
        return {"status": "unavailable", "error": type(exc).__name__}


def analyze(context):
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return {"status": "disabled", **normalize_intelligence({"summary": "AI disabled; deterministic research and wallet engines continue."}), "auxiliary": []}

    tools = []
    if ENABLE_WEB_RESEARCH:
        tools += [{"type": "openrouter:web_search", "parameters": {"max_results": 4, "max_total_results": 8}}, {"type": "openrouter:web_fetch"}]
    if ENABLE_SUBAGENT:
        tools.append({"type": "openrouter:subagent", "parameters": {"model": OPENROUTER_SUBAGENT_MODEL, "max_completion_tokens": 800, "tools": [{"type": "openrouter:web_search", "parameters": {"max_total_results": 5}}]}})

    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(context, separators=(",", ":"))}]
    try:
        response = _call(key, OPENROUTER_MODEL, messages, tools, json_mode=True)
        out = normalize_intelligence(_extract(response["choices"][0]["message"]["content"]))
        out.update(status="ok", model=response.get("model", OPENROUTER_MODEL), generated_at=datetime.now(timezone.utc).isoformat(), usage=response.get("usage", {}))
        out["auxiliary"] = _free_aux(key, context, out)
        return out
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__, "http_status": getattr(exc, "http_status", None), **normalize_intelligence({"summary": f"Primary AI failed safely: {type(exc).__name__}"}), "auxiliary": []}
