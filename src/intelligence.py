import json, os, re
from urllib.request import Request, urlopen
from datetime import datetime, timezone
from .config import OPENROUTER_MODEL, OPENROUTER_SUBAGENT_MODEL, ENABLE_WEB_RESEARCH, ENABLE_SUBAGENT

ENDPOINT="https://openrouter.ai/api/v1/chat/completions"
SYSTEM="""You are the qualitative research sidecar for an OSRS paper trader. Never calculate P&L, ROI, tax, sizing, prices, or portfolio arithmetic. Those values are supplied by deterministic code. Explain notable moves, identify possible catalysts, distinguish official facts/community chatter/rumor/model inference, flag uncertainty/manipulation risk, and write concise mobile-friendly prose. Use web research selectively. Prefer official Jagex and OSRS Wiki evidence; Reddit/community chatter is sentiment evidence, never confirmed fact. Return JSON only with keys: market_mood, summary, notable_events, candidate_notes, position_notes, research_summary. Every event must have: title, evidence_class (OFFICIAL|CONFIRMED_COMMUNITY|COMMUNITY|RUMOR|MODEL_INFERENCE), confidence (0..1), market_relevance (0..1), affected_items, explanation, sources. Do not invent sources."""

def _extract_json(text):
    text=text.strip()
    try: return json.loads(text)
    except json.JSONDecodeError: pass
    m=re.search(r"\{.*\}",text,re.S)
    if not m: raise ValueError("No JSON object in model response")
    return json.loads(m.group(0))

def analyze(context):
    key=os.getenv("OPENROUTER_API_KEY")
    if not key: return {"status":"disabled","market_mood":"unknown","summary":"AI research disabled: OPENROUTER_API_KEY is not configured.","notable_events":[],"candidate_notes":[],"position_notes":[],"research_summary":"No AI request made."}
    tools=[]
    if ENABLE_WEB_RESEARCH: tools += [{"type":"openrouter:web_search","parameters":{"max_results":4,"max_total_results":10}},{"type":"openrouter:web_fetch"}]
    if ENABLE_SUBAGENT: tools.append({"type":"openrouter:subagent","parameters":{"model":OPENROUTER_SUBAGENT_MODEL,"max_completion_tokens":1000,"tools":[{"type":"openrouter:web_search","parameters":{"max_total_results":6}}]}})
    body={"model":OPENROUTER_MODEL,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":json.dumps(context,separators=(",",":"))}],"temperature":0.2,"max_tokens":1800}
    if tools: body["tools"]=tools
    req=Request(ENDPOINT,data=json.dumps(body).encode(),headers={"Authorization":f"Bearer {key}","Content-Type":"application/json","HTTP-Referer":"https://github.com/cheeseonamonkey/Runescape_PaperTrader","X-Title":"OSRS PaperTrader"})
    try:
        with urlopen(req,timeout=120) as r: raw=json.load(r)
        out=_extract_json(raw["choices"][0]["message"]["content"]); out["status"]="ok"; out["model"]=raw.get("model",OPENROUTER_MODEL); out["generated_at"]=datetime.now(timezone.utc).isoformat(); out["usage"]=raw.get("usage",{}); return out
    except Exception as e:
        return {"status":"error","market_mood":"unknown","summary":f"AI research failed safely: {type(e).__name__}","notable_events":[],"candidate_notes":[],"position_notes":[],"research_summary":"Deterministic trading continued without AI input."}
