import json, os, re
from urllib.request import Request, urlopen
from datetime import datetime, timezone
from .config import OPENROUTER_MODEL, OPENROUTER_FREE_MODEL, OPENROUTER_SUBAGENT_MODEL, ENABLE_WEB_RESEARCH, ENABLE_SUBAGENT, ENABLE_FREE_SANITY_PASS

ENDPOINT="https://openrouter.ai/api/v1/chat/completions"
SYSTEM="""You are the qualitative macro/microstructure research sidecar for an OSRS paper-trading and economy-reference project. Never calculate P&L, ROI, tax, position sizing, or prices: deterministic code supplies those. Interpret market microstructure, liquidity, momentum, volume acceleration, catalyst risk, adverse selection, regime shifts, community narratives, and opportunity cost. Distinguish OFFICIAL, CONFIRMED_COMMUNITY, COMMUNITY, RUMOR, and MODEL_INFERENCE. Prefer Jagex/Wiki evidence. Reddit/community is sentiment evidence, not fact. Use supplied deterministic research before searching; use server-side web research only when it adds material context. Be terse but information-dense and mobile-readable. Return JSON only with keys market_mood, regime, summary, notable_events, candidate_notes, position_notes, research_summary, watchlist. Do not invent sources."""

def _extract_json(text):
    text=(text or "").strip()
    try:return json.loads(text)
    except json.JSONDecodeError:pass
    m=re.search(r"\{.*\}",text,re.S)
    if not m: raise ValueError("No JSON object in model response")
    return json.loads(m.group(0))

def _call(key, model, messages, tools=None, max_tokens=1800):
    body={"model":model,"messages":messages,"temperature":0.18,"max_tokens":max_tokens}
    if tools: body["tools"]=tools
    req=Request(ENDPOINT,data=json.dumps(body).encode(),headers={"Authorization":f"Bearer {key}","Content-Type":"application/json","HTTP-Referer":"https://github.com/cheeseonamonkey/Runescape_PaperTrader","X-Title":"OSRS PaperTrader"})
    with urlopen(req,timeout=120) as r:return json.load(r)

def analyze(context):
    key=os.getenv("OPENROUTER_API_KEY")
    if not key:return {"status":"disabled","market_mood":"unknown","regime":"unknown","summary":"AI research disabled: OPENROUTER_API_KEY is not configured.","notable_events":[],"candidate_notes":[],"position_notes":[],"watchlist":[],"research_summary":"Deterministic research remains available."}
    tools=[]
    if ENABLE_WEB_RESEARCH: tools += [{"type":"openrouter:web_search","parameters":{"max_results":4,"max_total_results":8}},{"type":"openrouter:web_fetch"}]
    if ENABLE_SUBAGENT: tools.append({"type":"openrouter:subagent","parameters":{"model":OPENROUTER_SUBAGENT_MODEL,"max_completion_tokens":900,"tools":[{"type":"openrouter:web_search","parameters":{"max_total_results":5}}]}})
    messages=[{"role":"system","content":SYSTEM},{"role":"user","content":json.dumps(context,separators=(",",":"))}]
    try:
        raw=_call(key,OPENROUTER_MODEL,messages,tools); out=_extract_json(raw["choices"][0]["message"]["content"])
        out.update(status="ok",model=raw.get("model",OPENROUTER_MODEL),generated_at=datetime.now(timezone.utc).isoformat(),usage=raw.get("usage",{}))
        if ENABLE_FREE_SANITY_PASS:
            try:
                sanity=_call(key,OPENROUTER_FREE_MODEL,[{"role":"system","content":"Check the supplied OSRS market commentary for unsupported certainty, contradiction, or obvious semantic mistakes. Do no arithmetic. Return one short JSON object: {ok:boolean, caution:string}."},{"role":"user","content":json.dumps(out,separators=(",",":"))}],max_tokens=220)
                out["free_sanity"]={"model":sanity.get("model",OPENROUTER_FREE_MODEL),**_extract_json(sanity["choices"][0]["message"]["content"])}
            except Exception as e: out["free_sanity"]={"ok":None,"caution":f"Free sanity pass unavailable ({type(e).__name__})."}
        return out
    except Exception as e:
        return {"status":"error","market_mood":"unknown","regime":"unknown","summary":f"AI research failed safely: {type(e).__name__}","notable_events":[],"candidate_notes":[],"position_notes":[],"watchlist":[],"research_summary":"Deterministic trading and research continued."}
