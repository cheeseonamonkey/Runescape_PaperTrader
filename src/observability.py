import os
from datetime import datetime, timezone


def github_run_meta(now=None):
    now = now or datetime.now(timezone.utc)
    run_id = os.getenv("GITHUB_RUN_ID")
    repository = os.getenv("GITHUB_REPOSITORY")
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    event = os.getenv("GITHUB_EVENT_NAME", "local")
    meta = {
        "run_id": run_id or f"local-{now.strftime('%Y%m%dT%H%M%SZ')}",
        "run_number": os.getenv("GITHUB_RUN_NUMBER"),
        "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
        "event": event,
        "workflow": os.getenv("GITHUB_WORKFLOW", "local"),
        "sha": os.getenv("GITHUB_SHA"),
        "repository": repository,
    }
    meta["url"] = f"{server}/{repository}/actions/runs/{run_id}" if run_id and repository else None
    if event == "schedule":
        # The workflow is scheduled for minute 07. GitHub may start scheduled work late.
        meta["schedule_delay_minutes"] = (now.minute - 7) % 60
    else:
        meta["schedule_delay_minutes"] = None
    return meta


def _aux_counts(intelligence):
    rows = intelligence.get("auxiliary", []) if isinstance(intelligence, dict) else []
    return {
        "ok": sum(1 for row in rows if row.get("status") == "ok"),
        "unavailable": sum(1 for row in rows if row.get("status") != "ok"),
    }


def health_warnings(wallets, market_stats, intelligence, research, history):
    warnings = []
    if market_stats.get("tracked_items", 0) < 2500:
        warnings.append("market_coverage_low")
    if intelligence.get("status") not in {"ok", "disabled"}:
        warnings.append(f"intelligence_{intelligence.get('status', 'unknown')}")
    if history.get("status") in {"stale_cache", "partial"}:
        warnings.append(f"history_{history.get('status')}")
    if research.get("search_status") in {"stale_cache", "error"}:
        warnings.append(f"research_{research.get('search_status')}")
    for slug, wallet in wallets.items():
        immediate_stops = [trade for trade in wallet.get("trades_this_run", []) if trade.get("side") == "SELL" and trade.get("reason") == "stop_loss" and float(trade.get("held_hours", 99)) < .25]
        if immediate_stops:
            warnings.append(f"{slug}_immediate_stop_churn")
        if wallet.get("cash_gp", 0) < 0 or wallet.get("value_gp", 0) < 0:
            warnings.append(f"{slug}_negative_balance")
    return warnings


def build_run_record(*, version, started_at, finished_at, wallets, market_stats, intelligence, research, history):
    meta = github_run_meta(finished_at)
    warnings = health_warnings(wallets, market_stats, intelligence, research, history)
    usage = intelligence.get("usage", {}) if isinstance(intelligence, dict) else {}
    tools = usage.get("server_tool_use_details", {}) if isinstance(usage, dict) else {}
    wallet_summary = {}
    for slug, wallet in wallets.items():
        trades = wallet.get("trades_this_run", [])
        wallet_summary[slug] = {
            "value_gp": wallet.get("value_gp"), "cash_gp": wallet.get("cash_gp"), "return_pct": wallet.get("return_pct"),
            "realized_pnl_gp": wallet.get("realized_pnl_gp"), "unrealized_pnl_gp": wallet.get("unrealized_pnl_gp"),
            "positions": len(wallet.get("positions", [])), "trades": len(trades),
            "buys": sum(1 for trade in trades if trade.get("side") == "BUY"),
            "sells": sum(1 for trade in trades if trade.get("side") == "SELL"),
        }
    return {
        "schema": 1, "version": version, "started_at": started_at.isoformat(), "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3), "github": meta,
        "health": {"status": "degraded" if warnings else "ok", "warnings": warnings},
        "market": market_stats,
        "history": {"status": history.get("status"), "age_hours": history.get("age_hours"), "items": len(history.get("items", {}))},
        "research": {"official": len([x for x in research.get("official", []) if not x.get("error")]), "search": len([x for x in research.get("search", []) if not x.get("error")]), "search_status": research.get("search_status")},
        "intelligence": {
            "status": intelligence.get("status"), "model": intelligence.get("model"), "cost": usage.get("cost"),
            "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
            "web_search_requests": tools.get("web_search_requests"), "tool_calls": tools.get("tool_calls_executed"),
            "auxiliary": _aux_counts(intelligence),
        },
        "wallets": wallet_summary,
    }


def run_index_summary(record):
    return {
        "run_id": record["github"]["run_id"], "at": record["finished_at"], "version": record["version"],
        "event": record["github"].get("event"), "url": record["github"].get("url"),
        "schedule_delay_minutes": record["github"].get("schedule_delay_minutes"),
        "duration_seconds": record.get("duration_seconds"), "health": record.get("health"),
        "intelligence": record.get("intelligence"), "wallets": record.get("wallets"),
    }
