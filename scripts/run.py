#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import VERSION, STARTING_GP, PROFILES
from src.market import snapshot
from src.strategy import common_features, economy_metrics, wallet_candidates
from src.portfolio import (
    fresh_wallet,
    normalize_wallet,
    close_positions,
    open_positions,
    wallet_value,
    marked_positions,
    portfolio_diagnostics,
)
from src.history import historical_context
from src.research import deterministic_research
from src.intelligence import advisory, report
from src.observability import build_run_record, run_index_summary
from src.io_utils import DATA, read_json, write_json, append_jsonl, read_jsonl_tail


def compact_market(row):
    keys = (
        "id", "name", "high", "low", "mid_5m", "mid_1h", "spread_roi", "momentum_5m_vs_1h",
        "volume_5m", "volume_1h", "volume_acceleration", "high_low_volume_imbalance",
        "turnover_gp_1h", "turnover_share", "liquidity_score", "market_impact_proxy", "quote_age_minutes",
    )
    return {key: row.get(key) for key in keys}


def compact_position(row):
    keys = (
        "item_id", "name", "qty", "entry_price", "unit_liquidation", "value_gp", "unrealized_roi", "market_move_roi",
        "entry_expected_roi", "entry_momentum", "entry_conviction", "risk_budget_pct", "tranches", "opened_at",
    )
    return {key: row.get(key) for key in keys}


def compact_candidate(row):
    keys = (
        "id", "name", "expected_roi", "expected_edge_gp", "spread_capture_ev_gp", "inventory_risk_ev_gp",
        "fill_probability", "inventory_probability", "momentum_5m_vs_1h", "volume_acceleration", "liquidity_score",
        "high_low_volume_imbalance", "historical_signal", "mean_reversion_signal", "volatility_signal",
        "cross_factor_signal", "crowding_signal", "patch_signal", "risk_budget_pct", "capacity_qty", "capacity_gp",
        "conviction", "kelly_fraction_proxy", "ai_risk_multiplier", "score", "score_components", "strategy_lenses",
    )
    return {key: row.get(key) for key in keys}


def prior_wallet_packet():
    out = {}
    for slug, profile in PROFILES.items():
        previous = read_json(DATA / "wallets" / slug / "latest.json", {})
        if not previous:
            continue
        out[slug] = {
            "name": profile.name,
            "return_pct": previous.get("return_pct"),
            "net_worth_gp": previous.get("net_worth_gp", previous.get("value_gp")),
            "liquid_gp": previous.get("liquid_gp", previous.get("cash_gp")),
            "portfolio_metrics": previous.get("portfolio_metrics", {}),
            "recent_actions": previous.get("recent_actions", [])[-5:],
        }
    return out


def inference_packet(started_at, economy, common, history, research, prior_wallets):
    return {
        "timestamp": started_at.isoformat(),
        "version": VERSION,
        "economy": economy,
        "market_distribution": {
            "tracked_items": len(common),
            "top_by_turnover": [compact_market(row) for row in common[:12]],
            "largest_movers": [compact_market(row) for row in sorted(common, key=lambda row: abs(row["momentum_5m_vs_1h"]), reverse=True)[:10]],
            "highest_flow_acceleration": [compact_market(row) for row in sorted(common, key=lambda row: row["volume_acceleration"], reverse=True)[:8]],
        },
        "historical": {"status": history.get("status"), "items": history.get("items", {})},
        "deterministic_research": {
            "official": research.get("official", [])[:8],
            "search": research.get("search", [])[:6],
            "search_status": research.get("search_status"),
            "queries": research.get("queries", []),
        },
        "prior_wallets": prior_wallets,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    started_at = datetime.now(timezone.utc)

    latest, five, hourly, mapping = snapshot()
    common = common_features(latest, five, hourly, mapping)
    economy = economy_metrics(common, started_at)

    history_cache_path = DATA / "historical" / "latest.json"
    research_cache_path = DATA / "research" / "latest.json"
    history = historical_context(common, read_json(history_cache_path, {}))
    research = deterministic_research(common, read_json(research_cache_path, {}))

    base_packet = inference_packet(started_at, economy, common, history, research, prior_wallet_packet())
    advisory_path = DATA / "intelligence" / "advisory.json"
    semantic_prior = advisory(base_packet, read_json(advisory_path, {}), started_at)

    wallets = {}
    states = {}
    trades_by_wallet = {}
    for slug, profile in PROFILES.items():
        base = DATA / "wallets" / slug
        path = base / "portfolio.json"
        state = fresh_wallet(profile) if args.reset else normalize_wallet(read_json(path, {}), profile)
        candidates = wallet_candidates(common, profile, history, semantic_prior, economy.get("patch"))
        signal_lookup = {row["id"]: row for row in candidates}
        common_ids = {row["id"] for row in common}
        for position in state.get("positions", []):
            item_id = position.get("item_id")
            if item_id in common_ids and item_id not in signal_lookup:
                signal_lookup[item_id] = {"eligible": False, "score": 0, "expected_roi": -1}
        closed = close_positions(state, latest, profile, signals=signal_lookup)
        opened = open_positions(state, candidates, latest, profile)
        trades = closed + opened
        value = wallet_value(state, latest, profile)
        marks = marked_positions(state, latest, profile)
        diagnostics = portfolio_diagnostics(state, latest, profile, started_at)
        recent_actions = (read_jsonl_tail(base / "journal.jsonl", 28) + trades)[-32:]
        wallet_snapshot = {
            "id": slug,
            "name": profile.name,
            "thesis": profile.thesis,
            "modules": list(profile.modules),
            "value_gp": value,
            "net_worth_gp": value,
            "cash_gp": state["cash_gp"],
            "liquid_gp": state["cash_gp"],
            "return_pct": round(value / STARTING_GP - 1, 6),
            "realized_pnl_gp": state["realized_pnl_gp"],
            "unrealized_pnl_gp": sum(row["unrealized_pnl_gp"] for row in marks),
            "positions": marks,
            "trades_this_run": trades,
            "recent_actions": recent_actions,
            "portfolio_metrics": diagnostics,
            "eligible_candidates": len(candidates),
            "top_candidates": candidates[:24],
            "strategy": {
                "max_positions": profile.max_positions,
                "reserve_pct": profile.reserve_pct,
                "take_profit": profile.take_profit,
                "stop_loss": profile.stop_loss,
                "soft_rotate_hours": profile.soft_rotate_hours,
                "max_hold_hours": profile.max_hold_hours,
                "max_position_pct": profile.max_position_pct,
                "max_participation_rate": profile.max_participation_rate,
                "allow_scale_in": profile.allow_scale_in,
                "max_tranches": profile.max_tranches,
                "ai_sensitivity": profile.ai_sensitivity,
                "ai_score_cap": profile.ai_score_cap,
            },
        }
        wallets[slug] = wallet_snapshot
        states[slug] = state
        trades_by_wallet[slug] = trades

    report_packet = {
        **base_packet,
        "advisory_prior": {
            key: semantic_prior.get(key)
            for key in ("status", "freshness", "generated_at", "biases", "patch_risk", "confidence", "item_biases", "rationale")
        },
        "wallets": {
            slug: {
                "name": wallet["name"],
                "thesis": wallet["thesis"],
                "modules": wallet["modules"],
                "return_pct": wallet["return_pct"],
                "net_worth_gp": wallet["net_worth_gp"],
                "liquid_gp": wallet["liquid_gp"],
                "portfolio_metrics": wallet["portfolio_metrics"],
                "positions": [compact_position(row) for row in wallet["positions"][:10]],
                "top_candidates": [compact_candidate(row) for row in wallet["top_candidates"][:7]],
                "recent_actions": wallet["recent_actions"][-6:],
            }
            for slug, wallet in wallets.items()
        },
    }
    intelligence_path = DATA / "intelligence" / "latest.json"
    intelligence = report(report_packet, read_json(intelligence_path, {}), started_at)
    intelligence["advisory"] = {
        key: semantic_prior.get(key)
        for key in ("schema", "status", "freshness", "generated_at", "age_hours", "biases", "patch_risk", "confidence", "item_biases", "rationale", "ensemble", "usage")
    }

    market_stats = {
        "tracked_items": len(common),
        "total_turnover_gp_1h": economy.get("total_turnover_gp_1h", sum(row["turnover_gp_1h"] for row in common)),
        "median_top_momentum": round(sum(row["momentum_5m_vs_1h"] for row in common[:20]) / max(1, len(common[:20])), 6),
    }
    finished_at = datetime.now(timezone.utc)
    run_record = build_run_record(
        version=VERSION,
        started_at=started_at,
        finished_at=finished_at,
        wallets=wallets,
        market_stats=market_stats,
        intelligence=intelligence,
        research=research,
        history=history,
    )
    document = {
        "version": VERSION,
        "updated_at": finished_at.isoformat(),
        "starting_gp_per_wallet": STARTING_GP,
        "run": run_index_summary(run_record),
        "wallets": wallets,
        "market": {
            "stats": market_stats,
            "economy": economy,
            "top_by_turnover": common[:50],
            "items": common[:180],
            "historical": history,
        },
        "simulation": read_json(DATA / "simulations" / "latest_72h.json", {}),
        "deterministic_research": research,
        "advisory": semantic_prior,
        "intelligence": intelligence,
    }

    # Durable state only after the complete cycle has been computed successfully.
    for slug, profile in PROFILES.items():
        base = DATA / "wallets" / slug
        state = states[slug]
        wallet = wallets[slug]
        write_json(base / "portfolio.json", state)
        write_json(base / "latest.json", wallet)
        append_jsonl(base / "equity_history.jsonl", {
            "at": finished_at.isoformat(),
            "value_gp": wallet["value_gp"],
            "cash_gp": state["cash_gp"],
            "realized_pnl_gp": state["realized_pnl_gp"],
            "unrealized_pnl_gp": wallet["unrealized_pnl_gp"],
        })
        for trade in trades_by_wallet[slug]:
            append_jsonl(base / "journal.jsonl", trade)
        (base / "journal.jsonl").touch(exist_ok=True)

    write_json(history_cache_path, history)
    write_json(research_cache_path, research)
    write_json(DATA / "latest_snapshot.json", document)
    write_json(advisory_path, semantic_prior)
    write_json(intelligence_path, intelligence)
    if intelligence.get("freshness") == "refreshed":
        append_jsonl(DATA / "intelligence" / "history.jsonl", intelligence)
    if semantic_prior.get("freshness") == "refreshed":
        append_jsonl(DATA / "intelligence" / "advisory_history.jsonl", semantic_prior)

    day = finished_at.date().isoformat()
    day_path = DATA / "days" / f"{day}.json"
    day_doc = read_json(day_path, {"date": day, "runs": []})
    day_doc["runs"].append({
        "version": VERSION,
        "at": finished_at.isoformat(),
        "run_id": run_record["github"]["run_id"],
        "health": run_record["health"],
        "wallets": {
            slug: {
                "value_gp": wallet["value_gp"],
                "net_worth_gp": wallet["net_worth_gp"],
                "cash_gp": wallet["cash_gp"],
                "liquid_gp": wallet["liquid_gp"],
                "return_pct": wallet["return_pct"],
                "realized_pnl_gp": wallet["realized_pnl_gp"],
                "unrealized_pnl_gp": wallet["unrealized_pnl_gp"],
                "positions": len(wallet["positions"]),
                "trades": wallet["trades_this_run"],
                "portfolio_metrics": wallet["portfolio_metrics"],
            }
            for slug, wallet in wallets.items()
        },
        "market": {**market_stats, "economy": economy},
        "advisory": {
            "status": semantic_prior.get("status"),
            "freshness": semantic_prior.get("freshness"),
            "biases": semantic_prior.get("biases"),
            "confidence": semantic_prior.get("confidence"),
        },
        "intelligence": {
            "status": intelligence.get("status"),
            "freshness": intelligence.get("freshness"),
            "economy_brief": intelligence.get("economy_brief"),
            "market_mood": intelligence.get("market_mood"),
            "regime": intelligence.get("regime"),
            "summary": intelligence.get("summary"),
        },
    })
    day_doc["runs"] = day_doc["runs"][-96:]
    write_json(day_path, day_doc)

    days_index_path = DATA / "days" / "index.json"
    days_index = read_json(days_index_path, {"days": []})
    days_index["days"] = ([day] + [value for value in days_index.get("days", []) if value != day])[:180]
    write_json(days_index_path, days_index)

    run_id = str(run_record["github"]["run_id"])
    write_json(DATA / "runs" / day / f"{run_id}.json", run_record)
    run_index_path = DATA / "runs" / "index.json"
    run_index = read_json(run_index_path, {"runs": []})
    summary = run_index_summary(run_record)
    run_index["runs"] = [summary] + [row for row in run_index.get("runs", []) if row.get("run_id") != run_id]
    run_index["runs"] = run_index["runs"][:320]
    write_json(run_index_path, run_index)

    warning_text = ",".join(run_record["health"]["warnings"]) or "none"
    print(
        "v" + VERSION + " "
        + " ".join(f"{slug}={wallet['net_worth_gp']:,}gp/{len(wallet['positions'])}pos" for slug, wallet in wallets.items())
        + f" market={len(common)} advisory={semantic_prior.get('status')}/{semantic_prior.get('freshness')} report={intelligence.get('status')}/{intelligence.get('freshness')} health={run_record['health']['status']} warnings={warning_text} run={run_id}"
    )


if __name__ == "__main__":
    main()
