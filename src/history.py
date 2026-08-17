from datetime import datetime, timezone
from math import log
from statistics import mean, median, pstdev

from .config import HISTORY_EVERY_HOURS, HISTORY_ITEMS
from .market import timeseries


def _mid(row):
    values = [n for n in (row.get("avgHighPrice"), row.get("avgLowPrice")) if isinstance(n, (int, float)) and n > 0]
    return sum(values) / len(values) if values else None


def _metrics(rows):
    points = [(_mid(row), int(row.get("highPriceVolume", 0) or 0) + int(row.get("lowPriceVolume", 0) or 0)) for row in rows]
    points = [point for point in points if point[0]]
    if len(points) < 4:
        return {}
    prices = [point[0] for point in points]
    returns = [log(b / a) for a, b in zip(prices, prices[1:]) if a > 0 and b > 0]
    avg = mean(prices)
    sd = pstdev(prices) or 1
    peak, max_drawdown = prices[0], 0
    for price in prices:
        peak = max(peak, price)
        max_drawdown = min(max_drawdown, price / peak - 1)
    recent = prices[-min(7, len(prices)):]
    drift = recent[-1] / recent[0] - 1 if len(recent) > 1 else 0
    noise = pstdev(returns) if len(returns) > 1 else 0
    projection = max(-.12, min(.12, drift))
    confidence = max(0, min(1, 1 - noise * 12))
    return {
        "points": len(prices),
        "mean_price": round(avg, 2),
        "zscore": round((prices[-1] - avg) / sd, 3),
        "volatility_1h": round(noise, 6),
        "max_drawdown": round(max_drawdown, 6),
        "median_hourly_volume": int(median(point[1] for point in points)),
        "trend_6h": round(drift, 6),
        "projected_6h_pct": round(projection, 6),
        "projection_confidence": round(confidence, 3),
    }


def _age_hours(value, now):
    try:
        return max(0, (now - datetime.fromisoformat(value)).total_seconds() / 3600)
    except (TypeError, ValueError):
        return None


def _select_rows(common_rows):
    """Diversify expensive timeseries calls across turnover, movement and flow."""
    if not common_rows:
        return []
    buckets = [
        common_rows,
        sorted(common_rows, key=lambda row: abs(float(row.get("momentum_5m_vs_1h", 0) or 0)), reverse=True),
        sorted(common_rows, key=lambda row: float(row.get("volume_acceleration", 0) or 0), reverse=True),
    ]
    selected, seen = [], set()
    cursor = 0
    while len(selected) < HISTORY_ITEMS and any(cursor < len(bucket) for bucket in buckets):
        for bucket in buckets:
            if cursor >= len(bucket):
                continue
            row = bucket[cursor]
            item_id = row.get("id")
            if item_id not in seen:
                seen.add(item_id)
                selected.append(row)
                if len(selected) >= HISTORY_ITEMS:
                    break
        cursor += 1
    return selected


def historical_context(common_rows, cached=None):
    now = datetime.now(timezone.utc)
    cached = cached if isinstance(cached, dict) else {}
    age = _age_hours(cached.get("generated_at"), now)
    if age is not None and age < HISTORY_EVERY_HOURS and cached.get("items"):
        return {**cached, "status": "cached", "age_hours": round(age, 2)}

    items = {}
    errors = 0
    selected = _select_rows(common_rows)
    for candidate in selected:
        try:
            items[str(candidate["id"])] = {"name": candidate["name"], **_metrics(timeseries(candidate["id"], "1h"))}
        except Exception as exc:
            errors += 1
            items[str(candidate["id"])] = {"name": candidate["name"], "error": type(exc).__name__}

    if selected and errors == len(items) and cached.get("items"):
        stale_age = _age_hours(cached.get("generated_at"), now)
        return {**cached, "status": "stale_cache", "age_hours": round(stale_age or 0, 2), "refresh_errors": errors}

    return {
        "status": "ok" if not errors else "partial",
        "generated_at": now.isoformat(),
        "age_hours": 0,
        "refresh_errors": errors,
        "selection": "round_robin_turnover_momentum_flow",
        "items": items,
    }
