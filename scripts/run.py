#!/usr/bin/env python3
import argparse, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.config import VERSION, STARTING_GP, PROFILES
from src.market import snapshot
from src.strategy import common_features, wallet_candidates
from src.portfolio import fresh_wallet, normalize_wallet, close_positions, open_positions, wallet_value, marked_positions
from src.history import historical_context
from src.research import deterministic_research
from src.intelligence import analyze
from src.io_utils import DATA, read_json, write_json, append_jsonl

p=argparse.ArgumentParser();p.add_argument("--reset",action="store_true");args=p.parse_args();now=datetime.now(timezone.utc)
latest,five,hourly,mapping=snapshot();common=common_features(latest,five,hourly,mapping)
history=historical_context(common);research=deterministic_research(common)
wallets={}; wallet_candidates_map={}
for slug,profile in PROFILES.items():
    base=DATA/"wallets"/slug; path=base/"portfolio.json"
    state=fresh_wallet(profile) if args.reset else normalize_wallet(read_json(path,{}),profile)
    closed=close_positions(state,latest,profile); candidates=wallet_candidates(common,profile,history)
    opened=open_positions(state,candidates,latest,profile); trades=closed+opened
    value=wallet_value(state,latest,profile); marks=marked_positions(state,latest,profile)
    snap={"id":slug,"name":profile.name,"thesis":profile.thesis,"value_gp":value,"cash_gp":state["cash_gp"],
        "return_pct":round(value/STARTING_GP-1,6),"realized_pnl_gp":state["realized_pnl_gp"],
        "unrealized_pnl_gp":sum(x["unrealized_pnl_gp"] for x in marks),"positions":marks,"trades_this_run":trades,
        "eligible_candidates":len(candidates),"top_candidates":candidates[:16],
        "strategy":{"max_positions":profile.max_positions,"reserve_pct":profile.reserve_pct,"take_profit":profile.take_profit,
        "stop_loss":profile.stop_loss,"soft_rotate_hours":profile.soft_rotate_hours,"max_hold_hours":profile.max_hold_hours,
        "max_position_pct":profile.max_position_pct}}
    wallets[slug]=snap;wallet_candidates_map[slug]=candidates
    write_json(path,state);write_json(base/"latest.json",snap)
    append_jsonl(base/"equity_history.jsonl",{"at":now.isoformat(),"value_gp":value,"cash_gp":state["cash_gp"],"realized_pnl_gp":state["realized_pnl_gp"],"unrealized_pnl_gp":snap["unrealized_pnl_gp"]})
    for t in trades:append_jsonl(base/"journal.jsonl",t)
    (base/"journal.jsonl").touch(exist_ok=True)

context={"timestamp":now.isoformat(),"version":VERSION,"common_market":{"top_by_turnover":common[:12],"historical":history},
    "wallets":{k:{"name":v["name"],"thesis":v["thesis"],"return_pct":v["return_pct"],"cash_gp":v["cash_gp"],
    "positions":v["positions"][:10],"top_candidates":v["top_candidates"][:10]} for k,v in wallets.items()},
    "deterministic_research":research}
intel=analyze(context)
market_stats={"tracked_items":len(common),"total_turnover_gp_1h":sum(x["turnover_gp_1h"] for x in common),
    "median_top_momentum":round(sum(x["momentum_5m_vs_1h"] for x in common[:20])/max(1,len(common[:20])),6)}
doc={"version":VERSION,"updated_at":now.isoformat(),"starting_gp_per_wallet":STARTING_GP,"wallets":wallets,
    "market":{"stats":market_stats,"top_by_turnover":common[:25],"historical":history},"deterministic_research":research,"intelligence":intel}
write_json(DATA/"latest_snapshot.json",doc);write_json(DATA/"intelligence/latest.json",intel);append_jsonl(DATA/"intelligence/history.jsonl",intel)

day=now.date().isoformat(); day_path=DATA/"days"/f"{day}.json"; day_doc=read_json(day_path,{"date":day,"runs":[]})
day_doc["runs"].append({"version":VERSION,"at":now.isoformat(),"wallets":{k:{"value_gp":v["value_gp"],"cash_gp":v["cash_gp"],"return_pct":v["return_pct"],
    "realized_pnl_gp":v["realized_pnl_gp"],"unrealized_pnl_gp":v["unrealized_pnl_gp"],"positions":len(v["positions"]),
    "trades":v["trades_this_run"]} for k,v in wallets.items()},"market":market_stats,
    "intelligence":{"status":intel.get("status"),"market_mood":intel.get("market_mood"),"regime":intel.get("regime"),"summary":intel.get("summary")}})
day_doc["runs"]=day_doc["runs"][-30:];write_json(day_path,day_doc)
idxp=DATA/"days"/"index.json";idx=read_json(idxp,{"days":[]});idx["days"]=([day]+[x for x in idx.get("days",[]) if x!=day])[:120];write_json(idxp,idx)
print("v"+VERSION+" "+" ".join(f"{s}={w['value_gp']:,}gp/{len(w['positions'])}pos" for s,w in wallets.items())+f" market={len(common)} ai={intel.get('status')}")
