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
    meta["schedule_delay_minutes"] = (now.minute - 7) % 60 if event == "schedule" else None
    return meta


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _usage_summary(payload, refreshed=True):
    usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
    tools = usage.get("server_tool_use_details", {}) if isinstance(usage, dict) else {}
    if not refreshed:
        return {"cost": 0, "prompt_tokens": 0, "completion_tokens": 0, "web_search_requests": 0, "tool_calls": 0}
    return {
        "cost": _num(usage.get("cost")),
        "prompt_tokens": int(_num(usage.get("prompt_tokens"))),
        "completion_tokens": int(_num(usage.get("completion_tokens"))),
        "web_search_requests": int(_num(tools.get("web_search_requests"))),
        "tool_calls": int(_num(tools.get("tool_calls_executed"))),
    }


def health_warnings(wallets, market_stats, intelligence, research, history):
    warnings = []
    if market_stats.get("tracked_items", 0) < 2500:
        warnings.append("market_coverage_low")
    if intelligence.get("status") not in {"ok", "disabled"}:
        warnings.append(f"intelligence_{intelligence.get('status', 'unknown')}")
    advisory = intelligence.get("advisory", {}) if isinstance(intelligence, dict) else {}
    if advisory and advisory.get("status") not in {"ok", "cached", "disabled"}:
        warnings.append(f"advisory_{advisory.get('status', 'unknown')}")
    if history.get("status") in {"stale_cache", "partial"}:
        warnings.append(f"history_{history.get('status')}")
    if research.get("search_status") in {"stale_cache", "error"}:
        warnings.append(f"research_{research.get('search_status')}")
    for slug, wallet in wallets.items():
        immediate = [
            trade
            for trade in wallet.get("trades_this_run", [])
            if trade.get("side") == "SELL"
            and trade.get("reason") == "stop_loss"
            and float(trade.get("held_hours", 99)) < .25
        ]
        if immediate:
            warnings.append(f"{slug}_immediate_stop_churn")
        if wallet.get("cash_gp", 0) < 0 or wallet.get("value_gp", 0) < 0:
            warnings.append(f"{slug}_negative_balance")
    return warnings


def build_run_record(*, version, started_at, finished_at, wallets, market_stats, intelligence, research, history):
    meta = github_run_meta(finished_at)
    warnings = health_warnings(wallets, market_stats, intelligence, research, history)
    wallet_summary = {}
    for slug, wallet in wallets.items():
        trades = wallet.get("trades_this_run", [])
        wallet_summary[slug] = {
            "value_gp": wallet.get("value_gp"),
            "net_worth_gp": wallet.get("net_worth_gp", wallet.get("value_gp")),
            "cash_gp": wallet.get("cash_gp"),
            "return_pct": wallet.get("return_pct"),
            "realized_pnl_gp": wallet.get("realized_pnl_gp"),
            "unrealized_pnl_gp": wallet.get("unrealized_pnl_gp"),
            "positions": len(wallet.get("positions", [])),
            "trades": len(trades),
            "buys": sum(1 for trade in trades if trade.get("side") == "BUY"),
            "sells": sum(1 for trade in trades if trade.get("side") == "SELL"),
        }

    report_fresh = intelligence.get("freshness") == "refreshed"
    advisory = intelligence.get("advisory", {}) if isinstance(intelligence, dict) else {}
    advisory_fresh = advisory.get("freshness") == "refreshed"
    report_usage = _usage_summary(intelligence, report_fresh)
    advisory_usage = _usage_summary(advisory, advisory_fresh)

    return {
        "schema": 2,
        "version": version,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "github": meta,
        "health": {"status": "degraded" if warnings else "ok", "warnings": warnings},
        "market": market_stats,
        "history": {
            "status": history.get("status"),
            "age_hours": history.get("age_hours"),
            "items": len(history.get("items", {})),
        },
        "research": {
            "official": len([x for x in research.get("official", []) if not x.get("error")]),
            "search": len([x for x in research.get("search", []) if not x.get("error")]),
            "search_status": research.get("search_status"),
        },
        "intelligence": {
            "status": intelligence.get("status"),
            "freshness": intelligence.get("freshness"),
            "model": intelligence.get("model"),
            "report": report_usage,
            "advisory": {
                "status": advisory.get("status"),
                "freshness": advisory.get("freshness"),
                "confidence": advisory.get("confidence"),
                **advisory_usage,
            },
            "total_cost": round(report_usage["cost"] + advisory_usage["cost"], 8),
            "total_prompt_tokens": report_usage["prompt_tokens"] + advisory_usage["prompt_tokens"],
            "total_completion_tokens": report_usage["completion_tokens"] + advisory_usage["completion_tokens"],
        },
        "wallets": wallet_summary,
    }


def run_index_summary(record):
    return {
        "run_id": record["github"]["run_id"],
        "at": record["finished_at"],
        "version": record["version"],
        "event": record["github"].get("event"),
        "url": record["github"].get("url"),
        "schedule_delay_minutes": record["github"].get("schedule_delay_minutes"),
        "duration_seconds": record.get("duration_seconds"),
        "health": record.get("health"),
        "intelligence": record.get("intelligence"),
        "wallets": record.get("wallets"),
    }
