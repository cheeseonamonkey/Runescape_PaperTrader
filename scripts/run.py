#!/usr/bin/env python3
import argparse, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.config import CFG, VERSION
from src.market import snapshot
from src.strategy import candidate_rows
from src.portfolio import fresh_portfolio, close_positions, open_positions, portfolio_value, marked_positions
from src.research import deterministic_research
from src.intelligence import analyze
from src.io_utils import DATA, read_json, write_json, append_jsonl

p=argparse.ArgumentParser();p.add_argument("--reset",action="store_true");args=p.parse_args(); now=datetime.now(timezone.utc)
latest,five,hourly,mapping=snapshot(); portfolio_path=DATA/"portfolio.json"; portfolio=fresh_portfolio() if args.reset else read_json(portfolio_path,fresh_portfolio())
closed=close_positions(portfolio,latest); candidates=candidate_rows(latest,five,hourly,mapping); deterministic=deterministic_research(candidates)
context={"timestamp":now.isoformat(),"version":VERSION,"strategy":{"max_positions":CFG.max_positions,"reserve_pct":CFG.reserve_pct,"take_profit":CFG.take_profit,"stop_loss":CFG.stop_loss,"soft_rotate_hours":CFG.soft_rotate_hours,"max_hold_hours":CFG.max_hold_hours},"portfolio":{"cash_gp":portfolio["cash_gp"],"positions":marked_positions(portfolio,latest)},"top_candidates":candidates[:18],"deterministic_research":deterministic}
intel=analyze(context); opened=open_positions(portfolio,candidates,latest); trades=closed+opened; value=portfolio_value(portfolio,latest); marks=marked_positions(portfolio,latest)
market_stats={"eligible_candidates":len(candidates),"top_expected_roi":candidates[0]["expected_roi"] if candidates else 0,"top_momentum":candidates[0]["momentum_5m_vs_1h"] if candidates else 0,"top_volume_acceleration":candidates[0]["volume_acceleration"] if candidates else 0}
doc={"version":VERSION,"updated_at":datetime.now(timezone.utc).isoformat(),"portfolio_value_gp":value,"cash_gp":portfolio["cash_gp"],"realized_pnl_gp":portfolio["realized_pnl_gp"],"unrealized_pnl_gp":sum(x["unrealized_pnl_gp"] for x in marks),"return_pct":round(value/CFG.starting_gp-1,6),"positions":marks,"trades_this_run":trades,"top_candidates":candidates[:20],"market_stats":market_stats,"deterministic_research":deterministic,"intelligence":intel,"strategy":{"starting_gp":CFG.starting_gp,"max_positions":CFG.max_positions,"reserve_pct":CFG.reserve_pct,"take_profit":CFG.take_profit,"stop_loss":CFG.stop_loss,"soft_rotate_hours":CFG.soft_rotate_hours,"max_hold_hours":CFG.max_hold_hours,"ge_tax_rate":CFG.ge_tax_rate,"ge_tax_cap":CFG.ge_tax_cap}}
write_json(portfolio_path,portfolio);write_json(DATA/"latest_snapshot.json",doc);write_json(DATA/"intelligence/latest.json",intel);append_jsonl(DATA/"equity_history.jsonl",{"at":doc["updated_at"],"value_gp":value,"cash_gp":portfolio["cash_gp"],"realized_pnl_gp":portfolio["realized_pnl_gp"],"unrealized_pnl_gp":doc["unrealized_pnl_gp"]});append_jsonl(DATA/"intelligence/history.jsonl",intel)
for t in trades:append_jsonl(DATA/"journal.jsonl",t)
(DATA/"journal.jsonl").touch(exist_ok=True)
day=now.date().isoformat(); day_path=DATA/"days"/f"{day}.json"; day_doc=read_json(day_path,{"date":day,"runs":[]}); day_doc["runs"].append({"at":doc["updated_at"],"value_gp":value,"cash_gp":doc["cash_gp"],"realized_pnl_gp":doc["realized_pnl_gp"],"unrealized_pnl_gp":doc["unrealized_pnl_gp"],"positions":len(marks),"trades":trades,"market_stats":market_stats,"intelligence":{"status":intel.get("status"),"market_mood":intel.get("market_mood"),"regime":intel.get("regime"),"summary":intel.get("summary"),"notable_events":intel.get("notable_events",[])[:4]}}); day_doc["runs"]=day_doc["runs"][-30:]; write_json(day_path,day_doc)
idx_path=DATA/"days"/"index.json"; idx=read_json(idx_path,{"days":[]}); idx["days"]=([day]+[x for x in idx.get("days",[]) if x!=day])[:90];write_json(idx_path,idx)
print(f"v{VERSION} value={value:,} cash={portfolio['cash_gp']:,} positions={len(marks)} trades={len(trades)} candidates={len(candidates)} ai={intel.get('status')}")
