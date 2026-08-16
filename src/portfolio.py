from datetime import datetime, timezone
from .config import STARTING_GP
from .strategy import entry_liquidation_baseline, liquidation_unit, mark_position

STATE_SCHEMA = 2


def utcnow():
    return datetime.now(timezone.utc)


def fresh_wallet(profile):
    return {
        "schema": STATE_SCHEMA,
        "strategy_id": profile.slug,
        "cash_gp": STARTING_GP,
        "positions": [],
        "realized_pnl_gp": 0,
        "created_at": utcnow().isoformat(),
    }


def normalize_wallet(state, profile):
    if not isinstance(state, dict) or state.get("strategy_id") != profile.slug:
        return fresh_wallet(profile)
    state["schema"] = STATE_SCHEMA
    state.setdefault("cash_gp", STARTING_GP)
    state.setdefault("positions", [])
    state.setdefault("realized_pnl_gp", 0)
    clean = []
    for position in state["positions"]:
        if not isinstance(position, dict) or not position.get("item_id") or not position.get("qty"):
            continue
        position.setdefault("entry_liquidation_unit", entry_liquidation_baseline(position.get("entry_price", 1), profile))
        position.setdefault("entry_completion_probability", position.get("entry_fill_probability", 1))
        clean.append(position)
    state["positions"] = clean
    return state


def marked_positions(wallet, latest, profile):
    return [{**position, **mark_position(position, latest, profile)} for position in wallet["positions"]]


def wallet_value(wallet, latest, profile):
    return wallet["cash_gp"] + sum(row["value_gp"] for row in marked_positions(wallet, latest, profile))


def _quote_age_minutes(quote, now):
    ts = quote.get("lowTime")
    return max(0, (now.timestamp() - ts) / 60) if ts else None


def close_positions(wallet, latest, profile, now=None):
    now = now or utcnow()
    kept, trades = [], []
    for position in wallet["positions"]:
        quote = latest.get(str(position["item_id"]), {})
        low = quote.get("low")
        if not low:
            kept.append(position)
            continue
        quote_age = _quote_age_minutes(quote, now)
        if quote_age is not None and quote_age > max(60, profile.quote_max_age_minutes * 3):
            kept.append(position)
            continue

        unit = liquidation_unit(low, profile)
        net_roi = unit / position["entry_price"] - 1
        baseline = max(1, int(position.get("entry_liquidation_unit") or entry_liquidation_baseline(position["entry_price"], profile)))
        market_move_roi = unit / baseline - 1
        held = (now - datetime.fromisoformat(position["opened_at"])).total_seconds() / 3600
        thesis = position.get("entry_expected_roi", 0)
        momentum = position.get("entry_momentum", 0)
        reason = None

        if net_roi >= profile.take_profit:
            reason = "take_profit"
        elif market_move_roi <= profile.stop_loss:
            reason = "stop_loss"
        elif held >= profile.soft_rotate_hours and net_roi < max(.001, thesis * .20) and momentum <= 0:
            reason = "capital_rotation"
        elif held >= profile.max_hold_hours:
            reason = "max_hold"

        if not reason:
            kept.append(position)
            continue

        proceeds = unit * position["qty"]
        cost = position["entry_price"] * position["qty"]
        pnl = proceeds - cost
        wallet["cash_gp"] += proceeds
        wallet["realized_pnl_gp"] += pnl
        trades.append({
            "wallet": profile.slug, "side": "SELL", "item_id": position["item_id"], "name": position["name"],
            "qty": position["qty"], "unit_price": unit, "pnl_gp": pnl, "roi": round(net_roi, 6),
            "market_move_roi": round(market_move_roi, 6), "held_hours": round(held, 2), "reason": reason,
            "quote_age_minutes": round(quote_age, 1) if quote_age is not None else None, "at": now.isoformat(),
        })
    wallet["positions"] = kept
    return trades


def open_positions(wallet, candidates, latest, profile, now=None):
    now = now or utcnow()
    trades = []
    occupied = {position["item_id"] for position in wallet["positions"]}
    slots = profile.max_positions - len(wallet["positions"])
    equity = wallet_value(wallet, latest, profile)
    reserve = max(int(STARTING_GP * profile.reserve_pct), int(equity * profile.reserve_pct))

    for candidate in candidates:
        if slots <= 0 or candidate["id"] in occupied:
            continue
        spendable = max(0, wallet["cash_gp"] - reserve)
        budget = min(int(equity * candidate["risk_budget_pct"]), spendable)
        if budget < candidate["passive_entry"]:
            continue
        order_qty = budget // candidate["passive_entry"]
        if candidate.get("limit"):
            order_qty = min(order_qty, int(candidate["limit"]))
        entry_fill = float(candidate.get("entry_fill_probability", 1))
        qty = int(order_qty * entry_fill)
        if qty <= 0:
            continue
        cost = qty * candidate["passive_entry"]
        if cost > spendable:
            continue
        wallet["cash_gp"] -= cost
        opened = now.isoformat()
        entry_liquidation = liquidation_unit(candidate.get("low") or candidate["passive_entry"], profile)
        position = {
            "item_id": candidate["id"], "name": candidate["name"], "qty": qty,
            "entry_price": candidate["passive_entry"], "entry_liquidation_unit": entry_liquidation,
            "opened_at": opened, "entry_score": candidate["score"], "entry_expected_roi": candidate["expected_roi"],
            "entry_momentum": candidate["momentum_5m_vs_1h"], "entry_fill_probability": entry_fill,
            "entry_completion_probability": candidate.get("fill_probability", entry_fill),
            "risk_budget_pct": candidate["risk_budget_pct"],
        }
        wallet["positions"].append(position)
        occupied.add(candidate["id"])
        slots -= 1
        trades.append({
            "wallet": profile.slug, "side": "BUY", "item_id": candidate["id"], "name": candidate["name"],
            "qty": qty, "order_qty": order_qty, "fill_model": "expected_quantity", "unit_price": candidate["passive_entry"],
            "cost_gp": cost, "entry_fill_probability": round(entry_fill, 4),
            "completion_probability": candidate.get("fill_probability"), "expected_roi": candidate["expected_roi"],
            "score": candidate["score"], "reason": f"{profile.slug}_rank", "at": opened,
        })
    return trades
