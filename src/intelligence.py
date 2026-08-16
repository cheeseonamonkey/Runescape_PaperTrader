import json, os, re
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from datetime import datetime, timezone
from .config import OPENROUTER_MODEL, OPENROUTER_FREE_MODEL, OPENROUTER_SUBAGENT_MODEL, ENABLE_WEB_RESEARCH, ENABLE_SUBAGENT, ENABLE_FREE_AUX, FREE_AUX_PASSES

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
SYSTEM = """You are the qualitative research sidecar for an OSRS economy terminal running two independent paper-trading wallets. Never calculate P&L, ROI, tax, sizing, or prices. Deterministic code supplies those. Interpret microstructure, liquidity, momentum, volume acceleration, catalyst risk, adverse selection, regime shifts, community narratives, historical context, and opportunity cost. Compare Velocity (flow/momentum/high turnover) with Market Maker (spread/liquidity/completion quality). Distinguish OFFICIAL, CONFIRMED_COMMUNITY, COMMUNITY, RUMOR, MODEL_INFERENCE. Prefer Jagex/Wiki evidence. Reddit/community is sentiment evidence, not fact. Return one JSON object only with keys market_mood, regime, summary, notable_events, wallet_notes, research_summary, watchlist. Do not invent sources."""

JSON_OBJECT = {"type": "json_object"}


def _extract(text):
    if isinstance(text, list):
        text = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in text)
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("No JSON object")
    return json.loads(m.group(0))


def _call(key, model, messages, tools=None, max_tokens=1600, timeout=120, json_mode=False):
    body = {"model": model, "messages": messages, "temperature": .18, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    if json_mode:
        body["response_format"] = JSON_OBJECT
        body["plugins"] = [{"id": "response-healing"}]
    req = Request(ENDPOINT, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/cheeseonamonkey/Runescape_PaperTrader",
        "X-Title": "OSRS PaperTrader"
    })
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except HTTPError as e:
        # Do not persist response bodies: they may contain provider details not meant for the public dataset.
        err = RuntimeError(f"OpenRouter HTTP {e.code}")
        err.http_status = e.code
        raise err from e


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
            raw = _call(key, OPENROUTER_FREE_MODEL, [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, separators=(",", ":"))}
            ], max_tokens=420, timeout=60, json_mode=True)
            out.append({
                "kind": kind,
                "status": "ok",
                "model": raw.get("model", OPENROUTER_FREE_MODEL),
                "result": _extract(raw["choices"][0]["message"]["content"])
            })
        except Exception as e:
            out.append({"kind": kind, "status": "unavailable", "error": type(e).__name__})
    return out


def analyze(context):
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return {
            "status": "disabled",
            "market_mood": "unknown",
            "regime": "unknown",
            "summary": "AI disabled; deterministic research and wallet engines continue.",
            "notable_events": [],
            "wallet_notes": [],
            "watchlist": [],
            "research_summary": "",
            "auxiliary": []
        }

    tools = []
    if ENABLE_WEB_RESEARCH:
        tools += [
            {"type": "openrouter:web_search", "parameters": {"max_results": 4, "max_total_results": 8}},
            {"type": "openrouter:web_fetch"}
        ]
    if ENABLE_SUBAGENT:
        tools.append({
            "type": "openrouter:subagent",
            "parameters": {
                "model": OPENROUTER_SUBAGENT_MODEL,
                "max_completion_tokens": 800,
                "tools": [{"type": "openrouter:web_search", "parameters": {"max_total_results": 5}}]
            }
        })

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(context, separators=(",", ":"))}
    ]
    try:
        raw = _call(key, OPENROUTER_MODEL, messages, tools, json_mode=True)
        out = _extract(raw["choices"][0]["message"]["content"])
        out.update(
            status="ok",
            model=raw.get("model", OPENROUTER_MODEL),
            generated_at=datetime.now(timezone.utc).isoformat(),
            usage=raw.get("usage", {})
        )
        out["auxiliary"] = _free_aux(key, context, out)
        return out
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "http_status": getattr(e, "http_status", None),
            "market_mood": "unknown",
            "regime": "unknown",
            "summary": f"Primary AI failed safely: {type(e).__name__}",
            "notable_events": [],
            "wallet_notes": [],
            "watchlist": [],
            "research_summary": "",
            "auxiliary": []
        }
