#!/usr/bin/env python3
import argparse, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.config import CFG
from src.market import snapshot
from src.strategy import candidate_rows
from src.portfolio import fresh_portfolio, close_positions, open_positions, portfolio_value
from src.intelligence import analyze
from src.io_utils import DATA, read_json, write_json, append_jsonl
p=argparse.ArgumentParser(); p.add_argument("--reset",action="store_true"); args=p.parse_args()
latest,hourly,mapping=snapshot(); portfolio_path=DATA/"portfolio.json"; portfolio=fresh_portfolio() if args.reset else read_json(portfolio_path,fresh_portfolio())
closed=close_positions(portfolio,latest); candidates=candidate_rows(latest,hourly,mapping)
context={"timestamp":datetime.now(timezone.utc).isoformat(),"strategy":{"max_positions":CFG.max_positions,"take_profit":CFG.take_profit,"stop_loss":CFG.stop_loss},"portfolio":{"cash_gp":portfolio["cash_gp"],"positions":portfolio["positions"]},"top_candidates":candidates[:15]}
intel=analyze(context); opened=open_positions(portfolio,candidates); trades=closed+opened; value=portfolio_value(portfolio,latest)
doc={"updated_at":datetime.now(timezone.utc).isoformat(),"portfolio_value_gp":value,"cash_gp":portfolio["cash_gp"],"realized_pnl_gp":portfolio["realized_pnl_gp"],"return_pct":round(value/CFG.starting_gp-1,6),"positions":portfolio["positions"],"trades_this_run":trades,"top_candidates":candidates[:12],"intelligence":intel}
write_json(portfolio_path,portfolio); write_json(DATA/"latest_snapshot.json",doc); write_json(DATA/"intelligence/latest.json",intel); append_jsonl(DATA/"equity_history.jsonl",{"at":doc["updated_at"],"value_gp":value}); append_jsonl(DATA/"intelligence/history.jsonl",intel)
for t in trades: append_jsonl(DATA/"journal.jsonl",t)
(DATA/"journal.jsonl").touch(exist_ok=True)
print(f"value={value:,} cash={portfolio['cash_gp']:,} positions={len(portfolio['positions'])} trades={len(trades)} ai={intel.get('status')}")
