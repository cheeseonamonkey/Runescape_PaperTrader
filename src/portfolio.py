from datetime import datetime, timezone
from statistics import mean

from .config import STARTING_GP
from .strategy import entry_liquidation_baseline, liquidation_unit, mark_position

STATE_SCHEMA = 3


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
        position.setdefault("entry_conviction", 0)
        position.setdefault("tranches", 1)
        position.setdefault("last_scaled_at", None)
        clean.append(position)
    state["positions"] = clean
    return state


def marked_positions(wallet, latest, profile):
    return [{**position, **mark_position(position, latest, profile)} for position in wallet["positions"]]


def wallet_value(wallet, latest, profile):
    return wallet["cash_gp"] + sum(row["value_gp"] for row in marked_positions(wallet, latest, profile))


def portfolio_diagnostics(wallet, latest, profile, now=None):
    now = now or utcnow()
    marks = marked_positions(wallet, latest, profile)
    net_worth = wallet["cash_gp"] + sum(row["value_gp"] for row in marks)
    exposure = sum(row["value_gp"] for row in marks)
    cost_basis = sum(row["entry_price"] * row["qty"] for row in marks)
    weights = [row["value_gp"] / exposure for row in marks if exposure > 0]
    holding_hours = []
    for row in marks:
        try:
            holding_hours.append(max(0, (now - datetime.fromisoformat(row["opened_at"])).total_seconds() / 3600))
        except (TypeError, ValueError):
            pass
    return {
        "net_worth_gp": net_worth,
        "liquid_gp": wallet["cash_gp"],
        "cash_share": round(wallet["cash_gp"] / net_worth, 4) if net_worth else 0,
        "gross_exposure_gp": exposure,
        "exposure_share": round(exposure / net_worth, 4) if net_worth else 0,
        "cost_basis_gp": cost_basis,
        "inventory_pnl_gp": exposure - cost_basis,
        "position_hhi": round(sum(w * w for w in weights), 4) if weights else 0,
        "largest_position_share": round(max(weights), 4) if weights else 0,
        "winning_position_share": round(sum(1 for row in marks if row["unrealized_pnl_gp"] > 0) / len(marks), 4) if marks else 0,
        "mean_unrealized_roi": round(mean(row["unrealized_roi"] for row in marks), 6) if marks else 0,
        "mean_holding_hours": round(mean(holding_hours), 2) if holding_hours else 0,
        "position_slot_utilization": round(len(marks) / profile.max_positions, 4) if profile.max_positions else 0,
    }


def _quote_age_minutes(quote, now):
    ts = quote.get("lowTime")
    return max(0, (now.timestamp() - ts) / 60) if ts else None


def _top_components(candidate, limit=3):
    parts = candidate.get("score_components", {}) if isinstance(candidate, dict) else {}
    rows = sorted(parts.items(), key=lambda item: abs(float(item[1])), reverse=True)[:limit]
    return [{"factor": key, "points": round(float(value), 3)} for key, value in rows]


def _sell_reason(reason, held, net_roi, market_move, current=None):
    if reason == "take_profit":
        return f"Net liquidation ROI {net_roi:+.2%} cleared the take-profit hurdle after {held:.1f}h."
    if reason == "stop_loss":
        return f"Market-move ROI {market_move:+.2%} breached the adverse-move stop after {held:.1f}h."
    if reason == "capital_rotation":
        score = current.get("score") if isinstance(current, dict) else None
        if isinstance(current, dict) and current.get("eligible") is False:
            return f"Opportunity fell out of the current eligibility set after {held:.1f}h; capital recycled."
        return f"Opportunity decayed after {held:.1f}h; capital recycled" + (f" at current score {score:.1f}." if isinstance(score, (int, float)) else ".")
    return f"Maximum holding horizon reached after {held:.1f}h; inventory liquidated."


def close_positions(wallet, latest, profile, now=None, signals=None):
    now = now or utcnow()
    signals = signals or {}
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
        current = signals.get(position["item_id"])
        reason = None

        if net_roi >= profile.take_profit:
            reason = "take_profit"
        elif market_move_roi <= profile.stop_loss:
            reason = "stop_loss"
        elif held >= profile.soft_rotate_hours:
            if current:
                score_decay = current.get("score", 0) < position.get("entry_score", 0) * .62
                edge_decay = current.get("expected_roi", 0) < max(.001, thesis * .30)
                if score_decay or edge_decay:
                    reason = "capital_rotation"
            elif net_roi < max(.001, thesis * .20) and momentum <= 0:
                reason = "capital_rotation"
        if not reason and held >= profile.max_hold_hours:
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
            "wallet": profile.slug,
            "side": "SELL",
            "item_id": position["item_id"],
            "name": position["name"],
            "qty": position["qty"],
            "unit_price": unit,
            "pnl_gp": pnl,
            "roi": round(net_roi, 6),
            "market_move_roi": round(market_move_roi, 6),
            "held_hours": round(held, 2),
            "reason": reason,
            "reasoning": _sell_reason(reason, held, net_roi, market_move_roi, current),
            "math": {
                "take_profit": profile.take_profit,
                "stop_loss": profile.stop_loss,
                "entry_expected_roi": thesis,
                "entry_score": position.get("entry_score"),
                "current_score": current.get("score") if current else None,
                "entry_liquidation_unit": baseline,
                "exit_liquidation_unit": unit,
            },
            "quote_age_minutes": round(quote_age, 1) if quote_age is not None else None,
            "at": now.isoformat(),
        })
    wallet["positions"] = kept
    return trades


def _buy_reason(candidate, scaled=False):
    factors = _top_components(candidate)
    names = ", ".join(f"{x['factor']} {x['points']:+.1f}" for x in factors)
    prefix = "Pyramided into an existing thesis" if scaled else "Opened from the ranked opportunity book"
    return f"{prefix}: EV {candidate.get('expected_roi', 0):+.2%}, conviction {candidate.get('conviction', 0):.0%}; strongest score terms: {names}."


def _position_from_candidate(candidate, qty, profile, now):
    return {
        "item_id": candidate["id"],
        "name": candidate["name"],
        "qty": qty,
        "entry_price": candidate["passive_entry"],
        "entry_liquidation_unit": liquidation_unit(candidate.get("low") or candidate["passive_entry"], profile),
        "opened_at": now.isoformat(),
        "entry_score": candidate["score"],
        "entry_expected_roi": candidate["expected_roi"],
        "entry_momentum": candidate["momentum_5m_vs_1h"],
        "entry_fill_probability": float(candidate.get("entry_fill_probability", 1)),
        "entry_completion_probability": candidate.get("fill_probability", 1),
        "entry_conviction": candidate.get("conviction", 0),
        "risk_budget_pct": candidate["risk_budget_pct"],
        "tranches": 1,
        "last_scaled_at": None,
    }


def _scale_position(position, candidate, qty, profile, now):
    old_qty = position["qty"]
    total = old_qty + qty
    old_cost = position["entry_price"] * old_qty
    new_cost = candidate["passive_entry"] * qty
    old_baseline = position.get("entry_liquidation_unit") or entry_liquidation_baseline(position["entry_price"], profile)
    new_baseline = liquidation_unit(candidate.get("low") or candidate["passive_entry"], profile)
    position["entry_price"] = max(1, round((old_cost + new_cost) / total))
    position["entry_liquidation_unit"] = max(1, round((old_baseline * old_qty + new_baseline * qty) / total))
    position["qty"] = total
    position["entry_score"] = round((position.get("entry_score", 0) * old_qty + candidate["score"] * qty) / total, 3)
    position["entry_expected_roi"] = round((position.get("entry_expected_roi", 0) * old_qty + candidate["expected_roi"] * qty) / total, 6)
    position["entry_momentum"] = round((position.get("entry_momentum", 0) * old_qty + candidate["momentum_5m_vs_1h"] * qty) / total, 6)
    position["entry_conviction"] = round((position.get("entry_conviction", 0) * old_qty + candidate.get("conviction", 0) * qty) / total, 4)
    position["risk_budget_pct"] = candidate["risk_budget_pct"]
    position["tranches"] = int(position.get("tranches", 1)) + 1
    position["last_scaled_at"] = now.isoformat()


def open_positions(wallet, candidates, latest, profile, now=None):
    now = now or utcnow()
    trades = []
    by_id = {position["item_id"]: position for position in wallet["positions"]}
    slots = profile.max_positions - len(wallet["positions"])
    equity = wallet_value(wallet, latest, profile)
    reserve = max(int(STARTING_GP * profile.reserve_pct), int(equity * profile.reserve_pct))

    for candidate in candidates:
        existing = by_id.get(candidate["id"])
        scaling = bool(existing and profile.allow_scale_in and int(existing.get("tranches", 1)) < profile.max_tranches)
        if existing and not scaling:
            continue
        if not existing and slots <= 0:
            continue

        spendable = max(0, wallet["cash_gp"] - reserve)
        target_budget = min(int(equity * candidate["risk_budget_pct"]), spendable)
        if scaling:
            existing_cost = existing["qty"] * existing["entry_price"]
            strength_ok = candidate.get("conviction", 0) >= max(.55, existing.get("entry_conviction", 0) * .9)
            score_ok = candidate.get("score", 0) >= existing.get("entry_score", 0) * .98
            if not (strength_ok and score_ok):
                continue
            budget = min(max(0, target_budget - existing_cost), int(equity * candidate["risk_budget_pct"] * .45), spendable)
        else:
            budget = target_budget

        if budget < candidate["passive_entry"]:
            continue
        order_qty = budget // candidate["passive_entry"]
        if candidate.get("limit"):
            order_qty = min(order_qty, int(candidate["limit"]))
        if candidate.get("capacity_qty"):
            order_qty = min(order_qty, int(candidate["capacity_qty"]))
        entry_fill = float(candidate.get("entry_fill_probability", 1))
        qty = int(order_qty * entry_fill)
        if qty <= 0:
            continue
        cost = qty * candidate["passive_entry"]
        if cost > spendable:
            continue

        wallet["cash_gp"] -= cost
        if scaling:
            _scale_position(existing, candidate, qty, profile, now)
        else:
            position = _position_from_candidate(candidate, qty, profile, now)
            wallet["positions"].append(position)
            by_id[candidate["id"]] = position
            slots -= 1

        trades.append({
            "wallet": profile.slug,
            "side": "BUY",
            "item_id": candidate["id"],
            "name": candidate["name"],
            "qty": qty,
            "order_qty": order_qty,
            "fill_model": "expected_quantity",
            "unit_price": candidate["passive_entry"],
            "cost_gp": cost,
            "entry_fill_probability": round(entry_fill, 4),
            "completion_probability": candidate.get("fill_probability"),
            "expected_roi": candidate["expected_roi"],
            "score": candidate["score"],
            "conviction": candidate.get("conviction"),
            "risk_budget_pct": candidate.get("risk_budget_pct"),
            "capacity_qty": candidate.get("capacity_qty"),
            "ai_prior_points": (candidate.get("score_components") or {}).get("ai_prior"),
            "strategy_lenses": candidate.get("strategy_lenses", {}),
            "top_components": _top_components(candidate),
            "reason": f"{profile.slug}_{'scale_in' if scaling else 'rank'}",
            "reasoning": _buy_reason(candidate, scaling),
            "math": {
                "spread_capture_ev_gp": candidate.get("spread_capture_ev_gp"),
                "inventory_risk_ev_gp": candidate.get("inventory_risk_ev_gp"),
                "kelly_fraction_proxy": candidate.get("kelly_fraction_proxy"),
                "ai_risk_multiplier": candidate.get("ai_risk_multiplier"),
                "patch_signal": candidate.get("patch_signal"),
            },
            "at": now.isoformat(),
        })
    return trades
