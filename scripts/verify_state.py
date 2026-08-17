#!/usr/bin/env python3
import argparse
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import VERSION, PROFILES
from src.io_utils import DATA, read_json

parser = argparse.ArgumentParser()
parser.add_argument("--allow-stale-version", action="store_true")
args = parser.parse_args()
doc = read_json(DATA / "latest_snapshot.json", {})
errors = []
strict = not args.allow_stale_version

if not doc:
    errors.append("missing latest_snapshot.json")
if strict and doc.get("version") != VERSION:
    errors.append(f"snapshot version {doc.get('version')} != {VERSION}")

wallets = doc.get("wallets", {}) if isinstance(doc, dict) else {}
for slug, profile in PROFILES.items():
    w = wallets.get(slug)
    if not isinstance(w, dict):
        if strict:
            errors.append(f"missing wallet {slug}")
        continue
    for key in ("value_gp", "cash_gp", "return_pct", "positions", "top_candidates"):
        if key not in w:
            errors.append(f"{slug} missing {key}")
    if w.get("cash_gp", 0) < 0 or w.get("value_gp", 0) < 0:
        errors.append(f"{slug} negative balance")
    positions = w.get("positions", [])
    ids = [p.get("item_id") for p in positions]
    if len(ids) != len(set(ids)):
        errors.append(f"{slug} duplicate holdings ids")
    if len(positions) > w.get("strategy", {}).get("max_positions", 10**9):
        errors.append(f"{slug} over max positions")
    if strict:
        if w.get("net_worth_gp") != w.get("value_gp"):
            errors.append(f"{slug} net worth/value alias mismatch")
        metrics = w.get("portfolio_metrics")
        if not isinstance(metrics, dict):
            errors.append(f"{slug} missing portfolio metrics")
        for c in w.get("top_candidates", []):
            parts = c.get("score_components")
            if not isinstance(parts, dict):
                errors.append(f"{slug} candidate missing score_components")
                break
            if abs(sum(float(x) for x in parts.values()) - float(c.get("score", 0))) > .08:
                errors.append(f"{slug} candidate score attribution mismatch")
                break
            if abs(float(c.get("spread_capture_ev_gp", 0)) - float(c.get("inventory_risk_ev_gp", 0)) - float(c.get("expected_edge_gp", 0))) > .05:
                errors.append(f"{slug} candidate EV decomposition mismatch")
                break
            if not 0 <= float(c.get("conviction", 0)) <= 1:
                errors.append(f"{slug} conviction out of bounds")
                break
            if abs(float((parts or {}).get("ai_prior", 0))) > profile.ai_score_cap + .05:
                errors.append(f"{slug} AI prior escaped cap")
                break

market_doc = doc.get("market", {}) if isinstance(doc, dict) else {}
market = market_doc.get("stats", {})
if market and market.get("tracked_items", 0) < 1000:
    errors.append("market coverage implausibly low")
if strict:
    econ = market_doc.get("economy")
    if not isinstance(econ, dict):
        errors.append("missing economy diagnostics")
    else:
        bounded = {
            "breadth": (-1, 1),
            "turnover_weighted_breadth": (-1, 1),
            "active_share": (0, 1),
            "top10_turnover_share": (0, 1),
            "turnover_hhi": (0, 1),
            "turnover_gini": (0, 1),
            "liquidity_stress": (0, 1),
            "risk_appetite_proxy": (0, 1),
            "shock_share": (0, 1),
            "stale_share": (0, 1),
        }
        for key, (low, high) in bounded.items():
            value = econ.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(f"economy {key} invalid")
            elif not low <= value <= high:
                errors.append(f"economy {key} out of bounds")
        temperature = econ.get("market_temperature")
        if not isinstance(temperature, (int, float)) or not 0 <= temperature <= 100:
            errors.append("economy market_temperature invalid")
        patch = econ.get("patch")
        if not isinstance(patch, dict) or not 0 <= float(patch.get("risk", -1)) <= 1:
            errors.append("patch context invalid")

    advisory = doc.get("advisory")
    if not isinstance(advisory, dict):
        errors.append("missing advisory prior")
    else:
        for key, value in (advisory.get("biases") or {}).items():
            if not -1 <= float(value) <= 1:
                errors.append(f"advisory bias {key} out of bounds")

if errors:
    print("\n".join("ERROR " + e for e in errors))
    raise SystemExit(1)
print(f"state ok snapshot=v{doc.get('version')} expected=v{VERSION} wallets={','.join(wallets)} tracked={market.get('tracked_items','?')}")
