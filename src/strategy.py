from datetime import datetime, timedelta, timezone
from math import ceil, floor, log1p
from statistics import median, pstdev
from time import time

from .config import (
    GE_TAX_RATE,
    GE_TAX_CAP,
    PATCH_WEEKDAY_UTC,
    PATCH_HOUR_UTC,
    PATCH_MINUTE_UTC,
)


def _clamp(value, low, high):
    return min(high, max(low, value))


def ge_tax(unit_sell: int) -> int:
    return min(floor(max(0, unit_sell) * GE_TAX_RATE), GE_TAX_CAP)


def _mid(row):
    values = [x for x in (row.get("avgHighPrice"), row.get("avgLowPrice")) if isinstance(x, (int, float)) and x > 0]
    return sum(values) / len(values) if values else None


def _volume(row):
    return int(row.get("highPriceVolume", 0) or 0) + int(row.get("lowPriceVolume", 0) or 0)


def _imbalance(row):
    high = int(row.get("highPriceVolume", 0) or 0)
    low = int(row.get("lowPriceVolume", 0) or 0)
    total = high + low
    return (high - low) / total if total else 0.0


def patch_context(now=None):
    """Deterministic awareness of the usual Wednesday update window.

    Jagex can move or cancel updates, so this is a schedule prior rather than a fact that
    a patch is actually shipping. Official RSS evidence is supplied separately to the LLM.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    days_ahead = (PATCH_WEEKDAY_UTC - now.weekday()) % 7
    next_patch = (now + timedelta(days=days_ahead)).replace(
        hour=PATCH_HOUR_UTC, minute=PATCH_MINUTE_UTC, second=0, microsecond=0
    )
    if next_patch <= now:
        next_patch += timedelta(days=7)
    previous_patch = next_patch - timedelta(days=7)
    hours_to = (next_patch - now).total_seconds() / 3600
    hours_since = (now - previous_patch).total_seconds() / 3600

    if hours_to <= 2:
        phase, risk = "pre_patch", 1.0
    elif hours_to <= 24:
        phase, risk = "pre_patch", _clamp(1 - (hours_to - 2) / 30, .25, .95)
    elif hours_since <= 3:
        phase, risk = "patch_window", 1.0
    elif hours_since <= 18:
        phase, risk = "post_patch", _clamp(1 - (hours_since - 3) / 22, .25, .95)
    else:
        phase, risk = "normal", 0.0

    return {
        "phase": phase,
        "risk": round(risk, 4),
        "hours_to_usual_update": round(hours_to, 2),
        "hours_since_usual_update": round(hours_since, 2),
        "usual_update_at_utc": next_patch.isoformat(),
    }


def common_features(latest, five, hourly, mapping):
    now = int(time())
    out = []
    for item_id, price in latest.items():
        hi, lo = price.get("high"), price.get("low")
        high_time, low_time = price.get("highTime"), price.get("lowTime")
        if not all((hi, lo, high_time, low_time)) or hi <= lo or lo <= 0:
            continue
        five_row, hour_row = five.get(item_id, {}), hourly.get(item_id, {})
        volume_5m, volume_1h = _volume(five_row), _volume(hour_row)
        mid_5m, mid_1h = _mid(five_row), _mid(hour_row)
        age = max(0.0, max(now - high_time, now - low_time) / 60)
        momentum = (mid_5m / mid_1h - 1) if mid_5m and mid_1h else 0
        accel = _clamp((volume_5m * 12 / max(volume_1h, 1)) - 1, -1, 5)
        turnover = volume_1h * max(mid_1h or lo, 1)
        liquidity = min(1, log1p(turnover) / 19)
        spread = (hi - lo) / lo
        impact = spread / max(1, volume_1h) ** .5
        meta = mapping.get(item_id, {})
        out.append({
            "id": int(item_id),
            "name": meta.get("name", f"Item {item_id}"),
            "members": bool(meta.get("members")),
            "limit": meta.get("limit"),
            "highalch": meta.get("highalch"),
            "high": hi,
            "low": lo,
            "mid_5m": round(mid_5m, 2) if mid_5m else None,
            "mid_1h": round(mid_1h, 2) if mid_1h else None,
            "spread_roi": round(spread, 6),
            "momentum_5m_vs_1h": round(momentum, 6),
            "volume_5m": volume_5m,
            "volume_1h": volume_1h,
            "volume_acceleration": round(accel, 3),
            "high_low_volume_imbalance": round(_imbalance(five_row), 4),
            "turnover_gp_1h": int(turnover),
            "liquidity_score": round(liquidity, 4),
            "market_impact_proxy": round(impact, 8),
            "quote_age_minutes": round(age, 1),
        })

    out.sort(key=lambda x: x["turnover_gp_1h"], reverse=True)
    total_turnover = sum(max(0, row["turnover_gp_1h"]) for row in out)
    for row in out:
        row["turnover_share"] = round(row["turnover_gp_1h"] / total_turnover, 8) if total_turnover else 0
    return out


def _gini(values):
    values = sorted(max(0.0, float(v)) for v in values)
    n = len(values)
    total = sum(values)
    if not n or not total:
        return 0.0
    return _clamp((2 * sum((i + 1) * value for i, value in enumerate(values)) / (n * total)) - (n + 1) / n, 0, 1)


def _percentile(values, q):
    values = sorted(values)
    if not values:
        return 0
    index = (len(values) - 1) * q
    low, high = floor(index), ceil(index)
    if low == high:
        return values[low]
    return values[low] * (high - index) + values[high] * (index - low)


def economy_metrics(rows, now=None):
    """Cross-sectional market diagnostics. Short-run condition proxies, not a CPI claim."""
    patch = patch_context(now)
    if not rows:
        return {
            "advancers": 0,
            "decliners": 0,
            "flat": 0,
            "breadth": 0,
            "turnover_weighted_breadth": 0,
            "turnover_weighted_price_pressure": 0,
            "median_momentum": 0,
            "median_abs_momentum": 0,
            "momentum_dispersion": 0,
            "median_spread": 0,
            "turnover_weighted_spread": 0,
            "spread_dispersion": 0,
            "median_liquidity": 0,
            "median_volume_acceleration": 0,
            "p90_volume_acceleration": 0,
            "turnover_weighted_volume_imbalance": 0,
            "top1_turnover_share": 0,
            "top5_turnover_share": 0,
            "top10_turnover_share": 0,
            "turnover_hhi": 0,
            "turnover_gini": 0,
            "active_share": 0,
            "shock_share": 0,
            "stale_share": 0,
            "extreme_spread_share": 0,
            "members_turnover_share": 0,
            "liquidity_stress": 0,
            "risk_appetite_proxy": .5,
            "market_temperature": 0,
            "patch": patch,
        }

    eps = .0001
    adv = sum(1 for r in rows if r["momentum_5m_vs_1h"] > eps)
    dec = sum(1 for r in rows if r["momentum_5m_vs_1h"] < -eps)
    flat = len(rows) - adv - dec
    breadth = (adv - dec) / max(1, adv + dec)
    turnover_total = sum(max(0, r["turnover_gp_1h"]) for r in rows)
    volumes_total = sum(max(0, r["volume_1h"]) for r in rows)
    shares = [max(0, r["turnover_gp_1h"]) / turnover_total for r in rows] if turnover_total else [0] * len(rows)
    ranked_shares = sorted(shares, reverse=True)
    momenta = [r["momentum_5m_vs_1h"] for r in rows]
    spreads = [r["spread_roi"] for r in rows]
    accelerations = [r["volume_acceleration"] for r in rows]
    liquidities = [r["liquidity_score"] for r in rows]

    weighted_pressure = sum(_clamp(r["momentum_5m_vs_1h"], -.08, .08) * s for r, s in zip(rows, shares))
    weighted_breadth = sum((1 if r["momentum_5m_vs_1h"] > eps else -1 if r["momentum_5m_vs_1h"] < -eps else 0) * s for r, s in zip(rows, shares))
    weighted_spread = sum(r["spread_roi"] * s for r, s in zip(rows, shares))
    weighted_imbalance = sum(r.get("high_low_volume_imbalance", 0) * s for r, s in zip(rows, shares))
    members_turnover = sum(r["turnover_gp_1h"] for r in rows if r.get("members"))

    active_share = sum(1 for r in rows if r["volume_acceleration"] > 0) / len(rows)
    shock_share = sum(1 for r in rows if abs(r["momentum_5m_vs_1h"]) >= .02) / len(rows)
    stale_share = sum(1 for r in rows if r["quote_age_minutes"] >= 15) / len(rows)
    extreme_spread_share = sum(1 for r in rows if r["spread_roi"] >= .05) / len(rows)

    median_spread = median(spreads)
    median_liquidity = median(liquidities)
    dispersion = pstdev(momenta) if len(momenta) > 1 else 0
    spread_dispersion = pstdev(spreads) if len(spreads) > 1 else 0
    median_abs_momentum = median(abs(x) for x in momenta)

    liquidity_stress = _clamp(
        .30 * min(1, median_spread / .03)
        + .22 * stale_share
        + .25 * (1 - median_liquidity)
        + .23 * shock_share,
        0,
        1,
    )
    risk_appetite = _clamp(.5 + weighted_pressure / .04 + .12 * (active_share - .5), 0, 1)
    temperature = 100 * _clamp(
        .28 * active_share
        + .24 * min(1, median_abs_momentum / .015)
        + .24 * min(1, dispersion / .03)
        + .24 * min(1, abs(weighted_pressure) / .02),
        0,
        1,
    )

    return {
        "advancers": adv,
        "decliners": dec,
        "flat": flat,
        "breadth": round(breadth, 4),
        "turnover_weighted_breadth": round(weighted_breadth, 4),
        "turnover_weighted_price_pressure": round(weighted_pressure, 6),
        "median_momentum": round(median(momenta), 6),
        "median_abs_momentum": round(median_abs_momentum, 6),
        "momentum_dispersion": round(dispersion, 6),
        "median_spread": round(median_spread, 6),
        "turnover_weighted_spread": round(weighted_spread, 6),
        "spread_dispersion": round(spread_dispersion, 6),
        "median_liquidity": round(median_liquidity, 4),
        "median_volume_acceleration": round(median(accelerations), 3),
        "p90_volume_acceleration": round(_percentile(accelerations, .90), 3),
        "turnover_weighted_volume_imbalance": round(weighted_imbalance, 4),
        "total_turnover_gp_1h": int(turnover_total),
        "total_volume_units_1h": int(volumes_total),
        "median_turnover_gp_1h": int(median(r["turnover_gp_1h"] for r in rows)),
        "top1_turnover_share": round(sum(ranked_shares[:1]), 4),
        "top5_turnover_share": round(sum(ranked_shares[:5]), 4),
        "top10_turnover_share": round(sum(ranked_shares[:10]), 4),
        "turnover_hhi": round(sum(s * s for s in shares), 6),
        "turnover_gini": round(_gini([r["turnover_gp_1h"] for r in rows]), 4),
        "active_share": round(active_share, 4),
        "shock_share": round(shock_share, 4),
        "stale_share": round(stale_share, 4),
        "extreme_spread_share": round(extreme_spread_share, 4),
        "members_turnover_share": round(members_turnover / turnover_total, 4) if turnover_total else 0,
        "liquidity_stress": round(liquidity_stress, 4),
        "risk_appetite_proxy": round(risk_appetite, 4),
        "market_temperature": round(temperature, 1),
        "patch": patch,
    }


def liquidation_unit(low, profile):
    gross = floor(max(0, low) * (1 - profile.liquidation_slippage))
    return max(0, gross - ge_tax(gross))


def entry_liquidation_baseline(entry_price, profile):
    inferred_low = max(1, floor(entry_price / (1 + profile.passive_entry_penalty)))
    return max(1, liquidation_unit(inferred_low, profile))


def _advisor_component(x, profile, advisory, signals):
    if not advisory or advisory.get("status") not in {"ok", "cached", "stale_cache"}:
        return 0.0, 1.0, 0.0
    biases = advisory.get("biases", {}) if isinstance(advisory.get("biases"), dict) else {}
    item_biases = advisory.get("item_biases", {}) if isinstance(advisory.get("item_biases"), dict) else {}
    macro = _clamp(float(biases.get("macro", 0) or 0), -1, 1)
    momentum = _clamp(float(biases.get("momentum", 0) or 0), -1, 1)
    reversion = _clamp(float(biases.get("mean_reversion", 0) or 0), -1, 1)
    liquidity = _clamp(float(biases.get("liquidity", 0) or 0), -1, 1)
    risk = _clamp(float(biases.get("risk", 0) or 0), -1, 1)
    item = _clamp(float(item_biases.get(str(x["id"]), 0) or 0), -1, 1)
    combined = (
        .18 * macro
        + .26 * momentum * signals["momentum"]
        + .22 * reversion * signals["mean_reversion"]
        + .18 * liquidity * (2 * x["liquidity_score"] - 1)
        + .16 * item
    )
    component = _clamp(profile.ai_score_cap * profile.ai_sensitivity * combined, -profile.ai_score_cap, profile.ai_score_cap)
    max_sizing = .14 if profile.slug == "frontier" else .08
    risk_multiplier = _clamp(1 + max_sizing * profile.ai_sensitivity * risk, 1 - max_sizing, 1 + max_sizing)
    return component, risk_multiplier, item


def wallet_candidates(common, profile, historical=None, advisory=None, patch=None):
    hist = (historical or {}).get("items", {})
    patch = patch or patch_context()
    rows = []
    for x in common:
        if (
            x["quote_age_minutes"] > profile.quote_max_age_minutes
            or x["volume_1h"] < profile.min_hourly_volume
            or x["volume_5m"] < profile.min_5m_volume
            or x["spread_roi"] > profile.max_spread_roi
        ):
            continue

        entry = max(1, ceil(x["low"] * (1 + profile.passive_entry_penalty)))
        gross = max(1, floor(x["high"] * (1 - profile.passive_exit_penalty)))
        exit_net = max(0, gross - ge_tax(gross))
        edge = exit_net - entry
        raw_roi = edge / entry
        freshness = max(0, 1 - x["quote_age_minutes"] / profile.quote_max_age_minutes)
        liquidity = x["liquidity_score"]
        momentum = x["momentum_5m_vs_1h"]
        accel = x["volume_acceleration"]
        imbalance = x.get("high_low_volume_imbalance", 0)

        entry_fill = _clamp(.28 + .38 * liquidity + .18 * freshness + .08 * min(1, x["volume_5m"] / 70), .15, .97)
        exit_fill = _clamp(.28 + .42 * liquidity + .15 * freshness + .06 * _clamp(momentum / .02, -1, 1), .16, .98)
        complete = entry_fill * exit_fill
        inventory = entry_fill * (1 - exit_fill)
        adverse = entry * (.0025 + .012 * max(0, -momentum) + .0025 * (1 - liquidity))
        gross_capture_ev = complete * edge
        inventory_risk_ev = inventory * adverse
        expected_value = gross_capture_ev - inventory_risk_ev
        expected_roi = expected_value / entry
        if expected_value < profile.min_expected_edge_gp or expected_roi < profile.min_expected_roi:
            continue

        history_row = hist.get(str(x["id"]), {})
        zscore = float(history_row.get("zscore", 0) or 0)
        history_trend = float(history_row.get("trend_6h", 0) or 0)
        hist_vol = abs(float(history_row.get("volatility_1h", 0) or 0))
        history_signal = _clamp((history_trend / .04 if history_trend else 0) - max(0, zscore - 2) * .25, -1, 1)
        momentum_signal = _clamp(momentum / .03, -1, 1)
        accel_signal = _clamp(accel / 2, -1, 1)
        mean_reversion_signal = -_clamp(zscore / 2.5, -1, 1) if history_row else 0
        volatility_signal = _clamp(hist_vol / .03, 0, 1)
        edge_signal = min(2, expected_roi / .01)
        crowding_signal = _clamp(x.get("turnover_share", 0) / .05, 0, 1)
        flow_confirmation = _clamp(.55 * momentum_signal + .30 * accel_signal + .15 * imbalance, -1, 1)
        cross_signal = _clamp(.60 * (momentum_signal * accel_signal) + .40 * min(1, edge_signal) * liquidity, -1, 1)

        patch_risk = float(patch.get("risk", 0) or 0)
        if profile.slug == "frontier" and patch.get("phase") in {"patch_window", "post_patch"}:
            patch_signal = _clamp(patch_risk * (.55 * abs(momentum_signal) + .45 * abs(accel_signal)) - .30 * patch_risk, -1, 1)
        else:
            patch_signal = -patch_risk

        signals = {
            "edge": min(1, edge_signal),
            "momentum": momentum_signal,
            "flow": accel_signal,
            "liquidity": liquidity,
            "history": history_signal,
            "mean_reversion": mean_reversion_signal,
            "cross_factor": cross_signal,
            "flow_confirmation": flow_confirmation,
            "volatility": volatility_signal,
            "crowding": crowding_signal,
            "patch": patch_signal,
        }
        ai_component, ai_risk_multiplier, item_ai_bias = _advisor_component(x, profile, advisory, signals)

        carry_lens = _clamp(.62 * min(1, edge_signal) + .38 * liquidity - .18 * volatility_signal, -1, 1)
        trend_lens = _clamp(.45 * momentum_signal + .35 * accel_signal + .20 * history_signal, -1, 1)
        reversion_lens = _clamp(.62 * mean_reversion_signal + .20 * liquidity - .18 * max(0, accel_signal * momentum_signal), -1, 1)
        shock_lens = _clamp(patch_risk * (.45 * abs(momentum_signal) + .35 * abs(accel_signal) + .20 * abs(imbalance)), 0, 1)

        raw_components = {
            "edge": 100 * profile.edge_weight * edge_signal,
            "momentum": 100 * profile.momentum_weight * momentum_signal,
            "flow": 100 * profile.volume_accel_weight * accel_signal,
            "liquidity": 100 * profile.liquidity_weight * liquidity,
            "history": 100 * profile.historical_weight * history_signal,
            "mean_reversion": 100 * profile.mean_reversion_weight * mean_reversion_signal,
            "cross_factor": 100 * profile.cross_factor_weight * cross_signal,
            "volatility": -100 * profile.volatility_penalty_weight * volatility_signal,
            "crowding": -100 * profile.crowding_penalty_weight * crowding_signal,
            "patch": 100 * profile.patch_weight * patch_signal,
            "ai_prior": ai_component,
            "freshness": 10 * freshness,
        }
        score_components = {key: round(value, 3) for key, value in raw_components.items()}
        score = round(sum(score_components.values()), 3)

        directional = [momentum_signal, accel_signal, flow_confirmation]
        agreement = abs(sum(directional) / len(directional))
        kelly_proxy = _clamp(expected_roi / max(expected_roi + x["spread_roi"] + 2 * hist_vol + .01, .001), 0, 1)
        conviction = _clamp(.55 * agreement + .25 * max(0, cross_signal) + .20 * kelly_proxy, 0, 1)
        risk = profile.base_position_pct * (
            .56
            + .72 * liquidity
            + .28 * max(0, momentum_signal)
            + .18 * max(0, accel_signal)
            + .12 * max(0, history_signal)
        )
        risk *= 1 + profile.conviction_sizing * conviction
        risk *= ai_risk_multiplier
        if profile.slug != "frontier":
            risk *= 1 - min(.22, patch_risk * profile.patch_weight)
        risk = _clamp(risk, .02, profile.max_position_pct)

        capacity_qty = max(1, floor(x["volume_1h"] * profile.max_participation_rate))
        if x.get("limit"):
            capacity_qty = min(capacity_qty, int(x["limit"]))

        rows.append({
            **x,
            "eligible": True,
            "passive_entry": entry,
            "passive_exit_net": exit_net,
            "edge_gp": round(edge, 2),
            "raw_roi": round(raw_roi, 6),
            "expected_edge_gp": round(expected_value, 2),
            "expected_roi": round(expected_roi, 6),
            "entry_fill_probability": round(entry_fill, 4),
            "exit_fill_probability": round(exit_fill, 4),
            "fill_probability": round(complete, 4),
            "inventory_probability": round(inventory, 4),
            "adverse_selection_unit_gp": round(adverse, 2),
            "spread_capture_ev_gp": round(gross_capture_ev, 2),
            "inventory_risk_ev_gp": round(inventory_risk_ev, 2),
            "risk_budget_pct": round(risk, 4),
            "historical_signal": round(history_signal, 4),
            "mean_reversion_signal": round(mean_reversion_signal, 4),
            "volatility_signal": round(volatility_signal, 4),
            "cross_factor_signal": round(cross_signal, 4),
            "flow_confirmation": round(flow_confirmation, 4),
            "crowding_signal": round(crowding_signal, 4),
            "patch_signal": round(patch_signal, 4),
            "ai_item_bias": round(item_ai_bias, 4),
            "ai_risk_multiplier": round(ai_risk_multiplier, 4),
            "conviction": round(conviction, 4),
            "kelly_fraction_proxy": round(kelly_proxy, 4),
            "capacity_qty": capacity_qty,
            "capacity_gp": capacity_qty * entry,
            "historical": history_row,
            "strategy_lenses": {
                "carry": round(carry_lens, 4),
                "trend": round(trend_lens, 4),
                "reversion": round(reversion_lens, 4),
                "shock": round(shock_lens, 4),
            },
            "score_components": score_components,
            "score": score,
        })
    return sorted(rows, key=lambda x: x["score"], reverse=True)


def mark_position(position, latest, profile):
    quote = latest.get(str(position["item_id"]), {})
    low = quote.get("low") or position["entry_price"]
    unit = liquidation_unit(low, profile)
    value = unit * position["qty"]
    cost = position["entry_price"] * position["qty"]
    baseline = max(1, int(position.get("entry_liquidation_unit") or entry_liquidation_baseline(position["entry_price"], profile)))
    return {
        "unit_liquidation": unit,
        "value_gp": value,
        "unrealized_pnl_gp": value - cost,
        "unrealized_roi": (value / cost - 1) if cost else 0,
        "market_move_roi": unit / baseline - 1,
    }
