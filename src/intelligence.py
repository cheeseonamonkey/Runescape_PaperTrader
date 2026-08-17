import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .config import (
    OPENROUTER_MODEL,
    OPENROUTER_FREE_MODEL,
    OPENROUTER_SUBAGENT_MODEL,
    ENABLE_WEB_RESEARCH,
    ENABLE_SUBAGENT,
    ENABLE_FREE_AUX,
    FREE_AUX_PASSES,
    ADVISORY_EVERY_HOURS,
    INTELLIGENCE_EVERY_HOURS,
    AI_PRIOR_MAX_AGE_HOURS,
)

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
JSON_OBJECT = {"type": "json_object"}
EVIDENCE = {"OFFICIAL", "CONFIRMED_COMMUNITY", "COMMUNITY", "RUMOR", "MODEL_INFERENCE"}
SCHEMA = 3
ADVISORY_SCHEMA = 1

REPORT_SYSTEM = """You are the qualitative economics sidecar for an OSRS economy terminal with three paper-trading funds: Velocity, Market Maker and Frontier Lab. Deterministic code owns all prices, tax, P&L, fills, sizing and execution. Read the supplied shared inference packet, including derived macro/microstructure metrics, patch-window context, deterministic news and wallet diagnostics. Explain the state of the OSRS economy using economics language but do not pretend short-run price pressure is CPI/inflation. Distinguish OFFICIAL, CONFIRMED_COMMUNITY, COMMUNITY, RUMOR and MODEL_INFERENCE. Return compact JSON with keys economy_brief, market_mood, regime, summary, notable_events, wallet_notes, research_summary, watchlist. economy_brief should be 2-4 useful sentences. Mention the usual weekly update window only as a schedule prior unless official evidence confirms an update. Do not invent sources or recalculate the supplied arithmetic."""

ADVISOR_SYSTEM = """You are one member of a bounded OSRS market-prior ensemble. Deterministic code owns arithmetic and execution. You receive the same compact inference packet as other ensemble members. Return directional semantic priors only; do not calculate prices, P&L or position sizes. Use derived metrics, deterministic research and patch-window context. Keep uncertainty explicit. JSON keys: biases={macro,momentum,mean_reversion,liquidity,risk}, patch_risk, confidence, item_biases, rationale. Every bias must be between -1 and 1. patch_risk/confidence must be 0..1. item_biases is an object keyed only by item IDs present in the packet with values -1..1; omit items without a meaningful qualitative reason. risk=-1 means de-risk, +1 means modestly permit more risk. These are tiny priors, not decisions."""


def _clamp(value, low=-1.0, high=1.0):
    try:
        return min(high, max(low, float(value)))
    except (TypeError, ValueError):
        return 0.0


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
        return _list_of_text(value, 10, 700)
    if isinstance(value, dict):
        notes = []
        for wallet, detail in list(value.items())[:6]:
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
        "economy_brief": _text(raw.get("economy_brief") or raw.get("summary") or "", 1400),
        "market_mood": _text(raw.get("market_mood") or "unknown", 500),
        "regime": _text(raw.get("regime") or "unknown", 700),
        "summary": _text(raw.get("summary") or "", 1400),
        "notable_events": events[:8],
        "wallet_notes": _wallet_notes(raw.get("wallet_notes")),
        "research_summary": _text(raw.get("research_summary") or "", 1000),
        "watchlist": _list_of_text(raw.get("watchlist"), 12, 180),
    }


def normalize_advisory(raw):
    raw = raw if isinstance(raw, dict) else {}
    biases = raw.get("biases", {}) if isinstance(raw.get("biases"), dict) else {}
    item_biases = raw.get("item_biases", {}) if isinstance(raw.get("item_biases"), dict) else {}
    clean_items = {}
    for key, value in list(item_biases.items())[:20]:
        try:
            item_id = str(int(key))
        except (TypeError, ValueError):
            continue
        clean_items[item_id] = round(_clamp(value), 4)
    return {
        "biases": {
            "macro": round(_clamp(biases.get("macro")), 4),
            "momentum": round(_clamp(biases.get("momentum")), 4),
            "mean_reversion": round(_clamp(biases.get("mean_reversion")), 4),
            "liquidity": round(_clamp(biases.get("liquidity")), 4),
            "risk": round(_clamp(biases.get("risk")), 4),
        },
        "patch_risk": round(_clamp(raw.get("patch_risk"), 0, 1), 4),
        "confidence": round(_clamp(raw.get("confidence"), 0, 1), 4),
        "item_biases": clean_items,
        "rationale": _list_of_text(raw.get("rationale"), 6, 320),
    }


def _call(key, model, messages, tools=None, max_tokens=900, timeout=90, json_mode=True):
    body = {"model": model, "messages": messages, "temperature": .12, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    if json_mode:
        body["response_format"] = JSON_OBJECT
        body["plugins"] = [{"id": "response-healing"}]
    req = Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/cheeseonamonkey/Runescape_PaperTrader",
            "X-Title": "OSRS PaperTrader",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        error = RuntimeError(f"OpenRouter HTTP {exc.code}")
        error.http_status = exc.code
        raise error from exc


def _age_hours(value, now):
    try:
        return max(0, (now - datetime.fromisoformat(value)).total_seconds() / 3600)
    except (TypeError, ValueError):
        return None


def _usage(response):
    return response.get("usage", {}) if isinstance(response, dict) else {}


def _packet_item_ids(packet):
    market = packet.get("market_distribution", {}) if isinstance(packet, dict) else {}
    allowed = set()
    for key in ("top_by_turnover", "largest_movers", "highest_flow_acceleration"):
        rows = market.get(key, []) if isinstance(market.get(key), list) else []
        for row in rows:
            if isinstance(row, dict) and row.get("id") is not None:
                try:
                    allowed.add(str(int(row["id"])))
                except (TypeError, ValueError):
                    pass
    return allowed


def _one_advisor(key, model, packet, label):
    response = _call(
        key,
        model,
        [{"role": "system", "content": ADVISOR_SYSTEM}, {"role": "user", "content": json.dumps(packet, separators=(",", ":"))}],
        max_tokens=520,
        timeout=70,
        json_mode=True,
    )
    result = normalize_advisory(_extract(response["choices"][0]["message"]["content"]))
    allowed_ids = _packet_item_ids(packet)
    result["item_biases"] = {key: value for key, value in result["item_biases"].items() if key in allowed_ids}
    return {
        "label": label,
        "status": "ok",
        "model": response.get("model", model),
        "result": result,
        "usage": _usage(response),
    }


def _aggregate_advisors(rows):
    valid = [row for row in rows if row.get("status") == "ok" and isinstance(row.get("result"), dict)]
    if not valid:
        return normalize_advisory({})
    base_weights = []
    for row in valid:
        primary = row.get("label") == "paid_anchor"
        base = .5 if primary else .5 / max(1, sum(1 for x in valid if x.get("label") != "paid_anchor"))
        confidence = row["result"].get("confidence", 0)
        base_weights.append(base * (.55 + .45 * confidence))
    total = sum(base_weights) or 1
    weights = [w / total for w in base_weights]

    fields = ("macro", "momentum", "mean_reversion", "liquidity", "risk")
    biases = {
        field: round(_clamp(sum(row["result"]["biases"].get(field, 0) * weight for row, weight in zip(valid, weights))), 4)
        for field in fields
    }
    keys = set()
    for row in valid:
        keys.update(row["result"].get("item_biases", {}).keys())
    item_biases = {}
    for key in keys:
        value = sum(row["result"].get("item_biases", {}).get(key, 0) * weight for row, weight in zip(valid, weights))
        if abs(value) >= .08:
            item_biases[key] = round(_clamp(value), 4)
    patch_risk = sum(row["result"].get("patch_risk", 0) * weight for row, weight in zip(valid, weights))
    confidence = sum(row["result"].get("confidence", 0) * weight for row, weight in zip(valid, weights))
    rationale = []
    for row in valid:
        for text in row["result"].get("rationale", [])[:2]:
            if text not in rationale:
                rationale.append(text)
    return {
        "biases": biases,
        "patch_risk": round(_clamp(patch_risk, 0, 1), 4),
        "confidence": round(_clamp(confidence, 0, 1), 4),
        "item_biases": item_biases,
        "rationale": rationale[:6],
    }


def advisory(packet, cached=None, now=None):
    now = now or datetime.now(timezone.utc)
    cached = cached if isinstance(cached, dict) else {}
    age = _age_hours(cached.get("generated_at"), now)
    if (
        cached.get("schema") == ADVISORY_SCHEMA
        and cached.get("status") in {"ok", "cached"}
        and age is not None
        and age < ADVISORY_EVERY_HOURS
        and age < AI_PRIOR_MAX_AGE_HOURS
    ):
        out = {**cached, "status": "cached", "freshness": "cached", "age_hours": round(age, 2), "usage": {}}
        return out

    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return {
            "schema": ADVISORY_SCHEMA,
            "status": "disabled",
            "freshness": "disabled",
            "generated_at": now.isoformat(),
            "age_hours": 0,
            **normalize_advisory({}),
            "ensemble": [],
            "usage": {},
        }

    ensemble = []
    try:
        ensemble.append(_one_advisor(key, OPENROUTER_MODEL, packet, "paid_anchor"))
    except Exception as exc:
        ensemble.append({"label": "paid_anchor", "status": "unavailable", "error": type(exc).__name__})

    if ENABLE_FREE_AUX:
        for index in range(FREE_AUX_PASSES):
            try:
                ensemble.append(_one_advisor(key, OPENROUTER_FREE_MODEL, packet, f"free_peer_{index + 1}"))
            except Exception as exc:
                ensemble.append({"label": f"free_peer_{index + 1}", "status": "unavailable", "error": type(exc).__name__})

    aggregate = _aggregate_advisors(ensemble)
    status = "ok" if any(row.get("status") == "ok" for row in ensemble) else "error"
    paid_usage = next((row.get("usage", {}) for row in ensemble if row.get("label") == "paid_anchor" and row.get("status") == "ok"), {})
    if status == "error" and cached.get("schema") == ADVISORY_SCHEMA and cached.get("status") in {"ok", "cached", "stale_cache"} and age is not None and age < AI_PRIOR_MAX_AGE_HOURS:
        return {
            **cached,
            "status": "stale_cache",
            "freshness": "stale_cache",
            "age_hours": round(age, 2),
            "refresh_error": "all_advisors_unavailable",
            "last_attempt": ensemble,
            "usage": {},
        }
    return {
        "schema": ADVISORY_SCHEMA,
        "status": status,
        "freshness": "refreshed",
        "generated_at": now.isoformat(),
        "age_hours": 0,
        **aggregate,
        "ensemble": ensemble,
        "usage": paid_usage,
    }


def report(packet, cached=None, now=None):
    now = now or datetime.now(timezone.utc)
    cached = cached if isinstance(cached, dict) else {}
    age = _age_hours(cached.get("generated_at"), now)
    if cached.get("schema") == SCHEMA and cached.get("status") in {"ok", "disabled"} and age is not None and age < INTELLIGENCE_EVERY_HOURS:
        clean = normalize_intelligence(cached)
        for key in ("schema", "status", "model", "generated_at", "advisory"):
            if key in cached:
                clean[key] = cached[key]
        clean["freshness"] = "cached"
        clean["age_hours"] = round(age, 2)
        clean["usage"] = {}
        clean["auxiliary"] = []
        return clean

    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return {
            "schema": SCHEMA,
            "status": "disabled",
            "freshness": "disabled",
            "generated_at": now.isoformat(),
            "age_hours": 0,
            **normalize_intelligence({"economy_brief": "AI disabled; deterministic economics and trading continue."}),
            "usage": {},
            "auxiliary": [],
        }

    tools = []
    if ENABLE_WEB_RESEARCH:
        tools += [
            {"type": "openrouter:web_search", "parameters": {"max_results": 3, "max_total_results": 5}},
            {"type": "openrouter:web_fetch"},
        ]
    if ENABLE_SUBAGENT:
        tools.append({
            "type": "openrouter:subagent",
            "parameters": {
                "model": OPENROUTER_SUBAGENT_MODEL,
                "max_completion_tokens": 500,
                "tools": [{"type": "openrouter:web_search", "parameters": {"max_total_results": 3}}],
            },
        })

    try:
        response = _call(
            key,
            OPENROUTER_MODEL,
            [{"role": "system", "content": REPORT_SYSTEM}, {"role": "user", "content": json.dumps(packet, separators=(",", ":"))}],
            tools=tools,
            max_tokens=1000,
            timeout=95,
            json_mode=True,
        )
        out = normalize_intelligence(_extract(response["choices"][0]["message"]["content"]))
        out.update(
            schema=SCHEMA,
            status="ok",
            freshness="refreshed",
            age_hours=0,
            model=response.get("model", OPENROUTER_MODEL),
            generated_at=now.isoformat(),
            usage=_usage(response),
            auxiliary=[],
        )
        return out
    except Exception as exc:
        if cached.get("schema") == SCHEMA and cached.get("status") in {"ok", "disabled"} and age is not None:
            clean = normalize_intelligence(cached)
            for key in ("schema", "status", "model", "generated_at", "advisory"):
                if key in cached:
                    clean[key] = cached[key]
            clean.update(
                status="ok" if cached.get("status") == "ok" else cached.get("status"),
                freshness="stale_cache",
                age_hours=round(age, 2),
                refresh_error=type(exc).__name__,
                usage={},
                auxiliary=[],
            )
            return clean
        return {
            "schema": SCHEMA,
            "status": "error",
            "freshness": "refreshed",
            "age_hours": 0,
            "error_type": type(exc).__name__,
            "http_status": getattr(exc, "http_status", None),
            "generated_at": now.isoformat(),
            **normalize_intelligence({"economy_brief": f"Economy report failed safely: {type(exc).__name__}"}),
            "usage": {},
            "auxiliary": [],
        }


def free_quality_critique(report_payload):
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return {"status": "disabled"}
    prompt = "You are a software reliability reviewer. Critique this OSRS paper-trader test report. Identify likely hidden bugs, brittle assumptions, missing tests, suspicious metrics, and one or two highest-value follow-up experiments. Be concise. Do not suggest changing production state. Return JSON {summary:string, risks:[string], missing_tests:[string], experiments:[string]}."
    try:
        response = _call(
            key,
            OPENROUTER_FREE_MODEL,
            [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(report_payload, separators=(",", ":"))}],
            max_tokens=700,
            timeout=75,
            json_mode=True,
        )
        result = _extract(response["choices"][0]["message"]["content"])
        return {"status": "ok", "model": response.get("model", OPENROUTER_FREE_MODEL), "result": result}
    except Exception as exc:
        return {"status": "unavailable", "error": type(exc).__name__}
