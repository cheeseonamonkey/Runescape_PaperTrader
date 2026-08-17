import unittest
import os
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from src.config import PROFILES, STARTING_GP
from src.strategy import (
    ge_tax,
    liquidation_unit,
    entry_liquidation_baseline,
    common_features,
    economy_metrics,
    patch_context,
    wallet_candidates,
)
from src.portfolio import fresh_wallet, normalize_wallet, close_positions, open_positions, portfolio_diagnostics
from src.history import _metrics
from src.intelligence import normalize_intelligence, normalize_advisory, _aggregate_advisors, advisory, report, ADVISORY_SCHEMA, SCHEMA


class CoreMathTests(unittest.TestCase):
    def test_tax_is_monotone_and_capped(self):
        self.assertEqual(ge_tax(0), 0)
        self.assertLessEqual(ge_tax(10_000), ge_tax(20_000))
        self.assertEqual(ge_tax(1_000_000_000), 5_000_000)

    def test_entry_friction_does_not_trigger_stop(self):
        profile = PROFILES["velocity"]
        low = 10_000
        entry = 10_010
        baseline = liquidation_unit(low, profile)
        now = datetime.now(timezone.utc)
        wallet = fresh_wallet(profile)
        wallet["cash_gp"] -= entry * 10
        wallet["positions"] = [{
            "item_id": 1, "name": "fixture", "qty": 10, "entry_price": entry,
            "entry_liquidation_unit": baseline, "opened_at": (now - timedelta(minutes=5)).isoformat(),
            "entry_expected_roi": .03, "entry_momentum": .02, "entry_score": 100,
        }]
        trades = close_positions(wallet, {"1": {"low": low, "lowTime": int(now.timestamp())}}, profile, now=now)
        self.assertEqual(trades, [])
        self.assertEqual(len(wallet["positions"]), 1)

    def test_true_adverse_move_triggers_stop(self):
        profile = PROFILES["velocity"]
        low = 10_000
        entry = 10_010
        baseline = liquidation_unit(low, profile)
        now = datetime.now(timezone.utc)
        wallet = fresh_wallet(profile)
        wallet["cash_gp"] -= entry * 10
        wallet["positions"] = [{
            "item_id": 1, "name": "fixture", "qty": 10, "entry_price": entry,
            "entry_liquidation_unit": baseline, "opened_at": (now - timedelta(hours=1)).isoformat(),
            "entry_expected_roi": .03, "entry_momentum": .02, "entry_score": 100,
        }]
        moved_low = int(low * .96)
        trades = close_positions(wallet, {"1": {"low": moved_low, "lowTime": int(now.timestamp())}}, profile, now=now)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["reason"], "stop_loss")
        self.assertIn("reasoning", trades[0])

    def test_ineligible_current_signal_rotates_after_soft_horizon(self):
        profile = PROFILES["velocity"]
        now = datetime.now(timezone.utc)
        low = 10_000
        wallet = fresh_wallet(profile)
        wallet["positions"] = [{
            "item_id": 1, "name": "fixture", "qty": 1, "entry_price": 10_010,
            "entry_liquidation_unit": liquidation_unit(low, profile),
            "opened_at": (now - timedelta(hours=profile.soft_rotate_hours + .2)).isoformat(),
            "entry_expected_roi": .03, "entry_momentum": .05, "entry_score": 120,
        }]
        trades = close_positions(
            wallet, {"1": {"low": low, "lowTime": int(now.timestamp())}}, profile, now=now,
            signals={1: {"eligible": False, "score": 0, "expected_roi": -1}},
        )
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["reason"], "capital_rotation")
        self.assertIn("eligibility", trades[0]["reasoning"])

    def test_stale_quote_does_not_force_exit(self):
        profile = PROFILES["velocity"]
        now = datetime.now(timezone.utc)
        wallet = fresh_wallet(profile)
        wallet["positions"] = [{
            "item_id": 1, "name": "fixture", "qty": 1, "entry_price": 10_000,
            "entry_liquidation_unit": entry_liquidation_baseline(10_000, profile),
            "opened_at": (now - timedelta(hours=10)).isoformat(),
            "entry_expected_roi": .03, "entry_momentum": -.1, "entry_score": 100,
        }]
        stale = int((now - timedelta(hours=3)).timestamp())
        self.assertEqual(close_positions(wallet, {"1": {"low": 8_000, "lowTime": stale}}, profile, now=now), [])

    def test_normalize_migrates_old_position(self):
        profile = PROFILES["velocity"]
        state = {"strategy_id": "velocity", "cash_gp": 1, "positions": [{"item_id": 1, "name": "x", "qty": 1, "entry_price": 100, "opened_at": datetime.now(timezone.utc).isoformat()}], "realized_pnl_gp": 0}
        migrated = normalize_wallet(state, profile)
        self.assertEqual(migrated["schema"], 3)
        self.assertEqual(migrated["positions"][0]["tranches"], 1)


class FeatureTests(unittest.TestCase):
    def _rows(self):
        return [
            {"id": 1, "name": "a", "limit": 1000, "high": 11500, "low": 10000, "spread_roi": .15,
             "momentum_5m_vs_1h": .02, "volume_5m": 60, "volume_1h": 500, "volume_acceleration": .5,
             "high_low_volume_imbalance": .2, "turnover_gp_1h": 5_000_000, "turnover_share": .38,
             "liquidity_score": .75, "market_impact_proxy": .001, "quote_age_minutes": 0, "members": True},
            {"id": 2, "name": "b", "limit": 1000, "high": 20500, "low": 20000, "spread_roi": .025,
             "momentum_5m_vs_1h": -.01, "volume_5m": 40, "volume_1h": 400, "volume_acceleration": -.2,
             "high_low_volume_imbalance": -.1, "turnover_gp_1h": 8_000_000, "turnover_share": .62,
             "liquidity_score": .80, "market_impact_proxy": .001, "quote_age_minutes": 0, "members": False},
        ]

    def test_common_features_are_sane(self):
        now = int(datetime.now(timezone.utc).timestamp())
        latest = {"1": {"high": 110, "low": 100, "highTime": now, "lowTime": now}}
        five = {"1": {"avgHighPrice": 108, "avgLowPrice": 102, "highPriceVolume": 12, "lowPriceVolume": 8}}
        hourly = {"1": {"avgHighPrice": 105, "avgLowPrice": 100, "highPriceVolume": 100, "lowPriceVolume": 100}}
        rows = common_features(latest, five, hourly, {"1": {"name": "fixture", "limit": 100}})
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["turnover_share"], 1)
        self.assertGreater(rows[0]["high_low_volume_imbalance"], 0)

    def test_economy_metrics_are_bounded_and_expanded(self):
        e = economy_metrics(self._rows(), datetime(2026, 8, 16, 12, tzinfo=timezone.utc))
        for key in ("breadth", "turnover_weighted_breadth"):
            self.assertGreaterEqual(e[key], -1)
            self.assertLessEqual(e[key], 1)
        for key in ("top10_turnover_share", "turnover_hhi", "turnover_gini", "liquidity_stress", "risk_appetite_proxy"):
            self.assertGreaterEqual(e[key], 0)
            self.assertLessEqual(e[key], 1)
        self.assertGreaterEqual(e["market_temperature"], 0)
        self.assertLessEqual(e["market_temperature"], 100)
        self.assertIn("patch", e)

    def test_concentration_is_order_independent(self):
        rows = self._rows()
        a = economy_metrics(rows)
        b = economy_metrics(list(reversed(rows)))
        self.assertEqual(a["top1_turnover_share"], b["top1_turnover_share"])
        self.assertEqual(a["top10_turnover_share"], b["top10_turnover_share"])
        self.assertEqual(a["turnover_hhi"], b["turnover_hhi"])

    def test_patch_window_is_deterministic(self):
        near = patch_context(datetime(2026, 8, 19, 10, 30, tzinfo=timezone.utc))
        far = patch_context(datetime(2026, 8, 16, 10, 30, tzinfo=timezone.utc))
        self.assertEqual(near["phase"], "pre_patch")
        self.assertGreater(near["risk"], far["risk"])

    def test_score_components_sum_to_score_and_ai_is_capped(self):
        advisory = {"status": "ok", "biases": {"macro": 1, "momentum": 1, "mean_reversion": 1, "liquidity": 1, "risk": 1}, "item_biases": {"2": 1}}
        rows = wallet_candidates(self._rows(), PROFILES["market_maker"], None, advisory, {"phase": "normal", "risk": 0})
        self.assertTrue(rows)
        row = rows[0]
        self.assertAlmostEqual(sum(row["score_components"].values()), row["score"], places=2)
        self.assertAlmostEqual(row["spread_capture_ev_gp"] - row["inventory_risk_ev_gp"], row["expected_edge_gp"], places=2)
        self.assertLessEqual(abs(row["score_components"]["ai_prior"]), PROFILES["market_maker"].ai_score_cap)
        self.assertLessEqual(row["capacity_qty"], int(row["volume_1h"] * PROFILES["market_maker"].max_participation_rate) or 1)

    def test_frontier_can_scale_in_but_caps_tranches(self):
        profile = PROFILES["frontier"]
        wallet = fresh_wallet(profile)
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        candidate = {
            "id": 5, "name": "fixture", "passive_entry": 1000, "low": 999, "risk_budget_pct": .2,
            "limit": 10000, "capacity_qty": 2000, "entry_fill_probability": .9, "fill_probability": .7,
            "score": 100, "expected_roi": .03, "momentum_5m_vs_1h": .02, "conviction": .8,
            "score_components": {"edge": 40, "ai_prior": 1}, "strategy_lenses": {"trend": .8},
            "spread_capture_ev_gp": 50, "inventory_risk_ev_gp": 10, "kelly_fraction_proxy": .3,
            "ai_risk_multiplier": 1, "patch_signal": 0,
        }
        latest = {"5": {"low": 999}}
        first = open_positions(wallet, [candidate], latest, profile, now=now)
        self.assertEqual(len(first), 1)
        first_qty = wallet["positions"][0]["qty"]
        candidate["score"] = 110
        second = open_positions(wallet, [candidate], latest, profile, now=now + timedelta(hours=1))
        self.assertEqual(len(second), 1)
        self.assertGreater(wallet["positions"][0]["qty"], first_qty)
        self.assertEqual(wallet["positions"][0]["tranches"], 2)
        metrics = portfolio_diagnostics(wallet, latest, profile, now)
        self.assertAlmostEqual(metrics["net_worth_gp"], metrics["liquid_gp"] + metrics["gross_exposure_gp"])

    def test_history_metrics_are_bounded(self):
        rows = [{"avgHighPrice": 100+i, "avgLowPrice": 98+i, "highPriceVolume": 10, "lowPriceVolume": 10} for i in range(20)]
        metrics = _metrics(rows)
        self.assertGreater(metrics["points"], 10)
        self.assertGreaterEqual(metrics["projection_confidence"], 0)
        self.assertLessEqual(metrics["projection_confidence"], 1)

    def test_advisory_ensemble_is_bounded(self):
        a = normalize_advisory({"biases": {"macro": 5, "risk": -5}, "confidence": 2, "patch_risk": -1, "item_biases": {"42": 3}})
        self.assertEqual(a["biases"]["macro"], 1)
        self.assertEqual(a["biases"]["risk"], -1)
        rows = [
            {"label": "paid_anchor", "status": "ok", "result": a},
            {"label": "free_peer_1", "status": "ok", "result": normalize_advisory({"biases": {"macro": -1}, "confidence": .5})},
        ]
        out = _aggregate_advisors(rows)
        self.assertTrue(-1 <= out["biases"]["macro"] <= 1)
        self.assertTrue(0 <= out["confidence"] <= 1)

    def test_stale_advisory_survives_total_refresh_failure(self):
        now = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
        cached = {
            "schema": ADVISORY_SCHEMA, "status": "ok", "generated_at": (now - timedelta(hours=5)).isoformat(),
            "biases": {"macro": .2, "momentum": .1, "mean_reversion": 0, "liquidity": 0, "risk": -.1},
            "patch_risk": .2, "confidence": .5, "item_biases": {}, "rationale": ["cached"], "ensemble": [], "usage": {},
        }
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "x"}), patch("src.intelligence._one_advisor", side_effect=RuntimeError("offline")):
            out = advisory({"economy": {}}, cached, now)
        self.assertEqual(out["status"], "stale_cache")
        self.assertEqual(out["freshness"], "stale_cache")
        self.assertEqual(out["biases"]["macro"], .2)
        self.assertEqual(out["usage"], {})

    def test_report_falls_back_to_stale_valid_report(self):
        now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        cached = {
            "schema": SCHEMA, "status": "ok", "generated_at": (now - timedelta(hours=9)).isoformat(),
            "economy_brief": "known good", "market_mood": "neutral", "regime": "quiet", "summary": "known good",
            "notable_events": [], "wallet_notes": [], "research_summary": "", "watchlist": [],
        }
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "x"}), patch("src.intelligence._call", side_effect=RuntimeError("offline")):
            out = report({"economy": {}}, cached, now)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["freshness"], "stale_cache")
        self.assertEqual(out["economy_brief"], "known good")
        self.assertEqual(out["usage"], {})

    def test_intelligence_schema_normalizes_drift(self):
        raw = {
            "market_mood": "busy", "regime": "momentum", "summary": "x",
            "notable_events": [{"title": "event", "type": "OFFICIAL", "source": "Jagex"}],
            "wallet_notes": {"Velocity": {"summary": "counterpoint"}},
            "watchlist": ["foo"],
        }
        normalized = normalize_intelligence(raw)
        self.assertEqual(normalized["notable_events"][0]["evidence_class"], "OFFICIAL")
        self.assertEqual(normalized["economy_brief"], "x")


if __name__ == "__main__":
    unittest.main()
