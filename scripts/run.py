#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import VERSION, STARTING_GP, PROFILES, INTELLIGENCE_EVERY_HOURS
from src.market import snapshot
from src.strategy import common_features, economy_metrics, wallet_candidates
from src.portfolio import fresh_wallet, normalize_wallet, close_positions, open_positions, wallet_value, marked_positions
from src.history import historical_context
from src.research import deterministic_research
from src.intelligence import analyze, normalize_intelligence, SCHEMA as INTELLIGENCE_SCHEMA
from src.observability import build_run_record, run_index_summary
from src.io_utils import DATA, read_json, write_json, append_jsonl


def compact_market(row):
    keys = ("id", "name", "high", "low", "spread_roi", "momentum_5m_vs_1h", "volume_5m", "volume_1h", "volume_acceleration", "turnover_gp_1h", "liquidity_score", "quote_age_minutes")
    return {key: row.get(key) for key in keys}


def compact_position(row):
    keys = ("item_id", "name", "qty", "unrealized_roi", "market_move_roi", "entry_expected_roi", "entry_momentum", "risk_budget_pct")
    return {key: row.get(key) for key in keys}


def compact_candidate(row):
    keys = (
        "id", "name", "expected_roi", "expected_edge_gp", "spread_capture_ev_gp", "inventory_risk_ev_gp",
        "fill_probability", "inventory_probability", "momentum_5m_vs_1h", "volume_acceleration", "liquidity_score",
        "historical_signal", "risk_budget_pct", "score", "score_components",
    )
    return {key: row.get(key) for key in keys}


def _age_hours(value, now):
    try:
        return max(0, (now - datetime.fromisoformat(value)).total_seconds() / 3600)
    except (TypeError, ValueError):
        return None


def cached_or_fresh_intelligence(context, now):
    path = DATA / "intelligence" / "latest.json"
    cached = read_json(path, {})
    age = _age_hours(cached.get("generated_at"), now)
    reusable = (
        cached.get("schema") == INTELLIGENCE_SCHEMA
        and cached.get("status") in {"ok", "disabled"}
        and age is not None
        and age < INTELLIGENCE_EVERY_HOURS
    )
    if reusable:
        clean = normalize_intelligence(cached)
        for key in ("schema", "status", "model", "generated_at", "usage", "auxiliary"):
            if key in cached:
                clean[key] = cached[key]
        clean["freshness"] = "cached"
        clean["age_hours"] = round(age, 2)
        return clean
    fresh = analyze(context)
    fresh["freshness"] = "refreshed"
    fresh["age_hours"] = 0
    return fresh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    started_at = datetime.now(timezone.utc)

    latest, five, hourly, mapping = snapshot()
    common = common_features(latest, five, hourly, mapping)
    economy = economy_metrics(common)

    history_cache_path = DATA / "historical" / "latest.json"
    research_cache_path = DATA / "research" / "latest.json"
    history = historical_context(common, read_json(history_cache_path, {}))
    research = deterministic_research(common, read_json(research_cache_path, {}))

    wallets = {}
    states = {}
    trades_by_wallet = {}
    for slug, profile in PROFILES.items():
        base = DATA / "wallets" / slug
        path = base / "portfolio.json"
        state = fresh_wallet(profile) if args.reset else normalize_wallet(read_json(path, {}), profile)
        closed = close_positions(state, latest, profile)
        candidates = wallet_candidates(common, profile, history)
        opened = open_positions(state, candidates, latest, profile)
        trades = closed + opened
        value = wallet_value(state, latest, profile)
        marks = marked_positions(state, latest, profile)
        wallet_snapshot = {
            "id": slug, "name": profile.name, "thesis": profile.thesis,
            "value_gp": value, "cash_gp": state["cash_gp"], "return_pct": round(value / STARTING_GP - 1, 6),
            "realized_pnl_gp": state["realized_pnl_gp"], "unrealized_pnl_gp": sum(row["unrealized_pnl_gp"] for row in marks),
            "positions": marks, "trades_this_run": trades, "eligible_candidates": len(candidates), "top_candidates": candidates[:20],
            "strategy": {
                "max_positions": profile.max_positions, "reserve_pct": profile.reserve_pct,
                "take_profit": profile.take_profit, "stop_loss": profile.stop_loss,
                "soft_rotate_hours": profile.soft_rotate_hours, "max_hold_hours": profile.max_hold_hours,
                "max_position_pct": profile.max_position_pct,
            },
        }
        wallets[slug] = wallet_snapshot
        states[slug] = state
        trades_by_wallet[slug] = trades

    context = {
        "timestamp": started_at.isoformat(), "version": VERSION,
        "economy": economy,
        "common_market": {
            "top_by_turnover": [compact_market(row) for row in common[:10]],
            "historical": {"status": history.get("status"), "items": history.get("items", {})},
        },
        "wallets": {
            slug: {
                "name": wallet["name"], "thesis": wallet["thesis"], "return_pct": wallet["return_pct"],
                "cash_gp": wallet["cash_gp"],
                "positions": [compact_position(row) for row in wallet["positions"][:8]],
                "top_candidates": [compact_candidate(row) for row in wallet["top_candidates"][:6]],
            }
            for slug, wallet in wallets.items()
        },
        "deterministic_research": {
            "official": research.get("official", [])[:8], "search": research.get("search", [])[:6],
            "search_status": research.get("search_status"), "queries": research.get("queries", []),
        },
    }
    intelligence = cached_or_fresh_intelligence(context, started_at)

    market_stats = {
        "tracked_items": len(common),
        "total_turnover_gp_1h": sum(row["turnover_gp_1h"] for row in common),
        "median_top_momentum": round(sum(row["momentum_5m_vs_1h"] for row in common[:20]) / max(1, len(common[:20])), 6),
    }
    finished_at = datetime.now(timezone.utc)
    run_record = build_run_record(
        version=VERSION, started_at=started_at, finished_at=finished_at, wallets=wallets,
        market_stats=market_stats, intelligence=intelligence, research=research, history=history,
    )
    document = {
        "version": VERSION, "updated_at": finished_at.isoformat(), "starting_gp_per_wallet": STARTING_GP,
        "run": run_index_summary(run_record), "wallets": wallets,
        "market": {"stats": market_stats, "economy": economy, "top_by_turnover": common[:40], "items": common[:120], "historical": history},
        "simulation": read_json(DATA / "simulations" / "latest_72h.json", {}),
        "deterministic_research": research, "intelligence": intelligence,
    }

    # Durable state only after the complete cycle has been computed successfully.
    for slug, profile in PROFILES.items():
        base = DATA / "wallets" / slug
        state = states[slug]
        wallet = wallets[slug]
        write_json(base / "portfolio.json", state)
        write_json(base / "latest.json", wallet)
        append_jsonl(base / "equity_history.jsonl", {
            "at": finished_at.isoformat(), "value_gp": wallet["value_gp"], "cash_gp": state["cash_gp"],
            "realized_pnl_gp": state["realized_pnl_gp"], "unrealized_pnl_gp": wallet["unrealized_pnl_gp"],
        })
        for trade in trades_by_wallet[slug]:
            append_jsonl(base / "journal.jsonl", trade)
        (base / "journal.jsonl").touch(exist_ok=True)

    write_json(history_cache_path, history)
    write_json(research_cache_path, research)
    write_json(DATA / "latest_snapshot.json", document)
    write_json(DATA / "intelligence" / "latest.json", intelligence)
    if intelligence.get("freshness") == "refreshed":
        append_jsonl(DATA / "intelligence" / "history.jsonl", intelligence)

    day = finished_at.date().isoformat()
    day_path = DATA / "days" / f"{day}.json"
    day_doc = read_json(day_path, {"date": day, "runs": []})
    day_doc["runs"].append({
        "version": VERSION, "at": finished_at.isoformat(), "run_id": run_record["github"]["run_id"],
        "health": run_record["health"],
        "wallets": {
            slug: {
                "value_gp": wallet["value_gp"], "cash_gp": wallet["cash_gp"], "return_pct": wallet["return_pct"],
                "realized_pnl_gp": wallet["realized_pnl_gp"], "unrealized_pnl_gp": wallet["unrealized_pnl_gp"],
                "positions": len(wallet["positions"]), "trades": wallet["trades_this_run"],
            }
            for slug, wallet in wallets.items()
        },
        "market": {**market_stats, "economy": economy},
        "intelligence": {
            "status": intelligence.get("status"), "freshness": intelligence.get("freshness"),
            "economy_brief": intelligence.get("economy_brief"), "market_mood": intelligence.get("market_mood"),
            "regime": intelligence.get("regime"), "summary": intelligence.get("summary"),
        },
    })
    day_doc["runs"] = day_doc["runs"][-72:]
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
    run_index["runs"] = run_index["runs"][:240]
    write_json(run_index_path, run_index)

    warning_text = ",".join(run_record["health"]["warnings"]) or "none"
    print(
        "v" + VERSION + " "
        + " ".join(f"{slug}={wallet['value_gp']:,}gp/{len(wallet['positions'])}pos" for slug, wallet in wallets.items())
        + f" market={len(common)} ai={intelligence.get('status')}/{intelligence.get('freshness')} health={run_record['health']['status']} warnings={warning_text} run={run_id}"
    )


if __name__ == "__main__":
    main()
