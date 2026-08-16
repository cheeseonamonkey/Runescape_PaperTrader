import unittest
from datetime import datetime, timezone, timedelta

from src.config import PROFILES, STARTING_GP
from src.strategy import ge_tax, liquidation_unit, entry_liquidation_baseline, common_features, wallet_candidates
from src.portfolio import fresh_wallet, normalize_wallet, close_positions, open_positions
from src.history import _metrics
from src.intelligence import normalize_intelligence


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
        wallet = fresh_wallet(profile)
        wallet["cash_gp"] -= entry * 10
        wallet["positions"] = [{
            "item_id": 1, "name": "fixture", "qty": 10, "entry_price": entry,
            "entry_liquidation_unit": baseline, "opened_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "entry_expected_roi": .03, "entry_momentum": .02,
        }]
        trades = close_positions(wallet, {"1": {"low": low, "lowTime": int(datetime.now(timezone.utc).timestamp())}}, profile)
        self.assertEqual(trades, [])
        self.assertEqual(len(wallet["positions"]), 1)

    def test_true_adverse_move_triggers_stop(self):
        profile = PROFILES["velocity"]
        low = 10_000
        entry = 10_010
        baseline = liquidation_unit(low, profile)
        wallet = fresh_wallet(profile)
        wallet["cash_gp"] -= entry * 10
        wallet["positions"] = [{
            "item_id": 1, "name": "fixture", "qty": 10, "entry_price": entry,
            "entry_liquidation_unit": baseline, "opened_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            "entry_expected_roi": .03, "entry_momentum": .02,
        }]
        moved_low = int(low * .96)
        trades = close_positions(wallet, {"1": {"low": moved_low, "lowTime": int(datetime.now(timezone.utc).timestamp())}}, profile)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["reason"], "stop_loss")
        self.assertLess(trades[0]["market_move_roi"], profile.stop_loss)

    def test_stale_quote_does_not_force_exit(self):
        profile = PROFILES["velocity"]
        wallet = fresh_wallet(profile)
        wallet["positions"] = [{
            "item_id": 1, "name": "fixture", "qty": 1, "entry_price": 10_000,
            "entry_liquidation_unit": entry_liquidation_baseline(10_000, profile),
            "opened_at": (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat(),
            "entry_expected_roi": .03, "entry_momentum": -.1,
        }]
        stale = int((datetime.now(timezone.utc) - timedelta(hours=3)).timestamp())
        self.assertEqual(close_positions(wallet, {"1": {"low": 8_000, "lowTime": stale}}, profile), [])

    def test_open_records_entry_fill_not_completion_probability(self):
        profile = PROFILES["market_maker"]
        wallet = fresh_wallet(profile)
        candidate = {
            "id": 5, "name": "fixture", "passive_entry": 1000, "low": 999, "risk_budget_pct": .1,
            "limit": 1000, "entry_fill_probability": .8, "fill_probability": .5,
            "score": 100, "expected_roi": .02, "momentum_5m_vs_1h": .01,
        }
        trades = open_positions(wallet, [candidate], {"5": {"low": 999}}, profile)
        self.assertEqual(len(trades), 1)
        self.assertEqual(wallet["positions"][0]["entry_fill_probability"], .8)
        self.assertEqual(wallet["positions"][0]["entry_completion_probability"], .5)
        self.assertGreaterEqual(wallet["cash_gp"], 0)

    def test_normalize_migrates_old_position(self):
        profile = PROFILES["velocity"]
        state = {"strategy_id": "velocity", "cash_gp": 1, "positions": [{"item_id": 1, "name": "x", "qty": 1, "entry_price": 100, "opened_at": datetime.now(timezone.utc).isoformat()}], "realized_pnl_gp": 0}
        migrated = normalize_wallet(state, profile)
        self.assertEqual(migrated["schema"], 2)
        self.assertIn("entry_liquidation_unit", migrated["positions"][0])


class FeatureTests(unittest.TestCase):
    def test_common_features_are_sane(self):
        now = int(datetime.now(timezone.utc).timestamp())
        latest = {"1": {"high": 110, "low": 100, "highTime": now, "lowTime": now}}
        five = {"1": {"avgHighPrice": 108, "avgLowPrice": 102, "highPriceVolume": 10, "lowPriceVolume": 10}}
        hourly = {"1": {"avgHighPrice": 105, "avgLowPrice": 100, "highPriceVolume": 100, "lowPriceVolume": 100}}
        rows = common_features(latest, five, hourly, {"1": {"name": "fixture", "limit": 100}})
        self.assertEqual(len(rows), 1)
        self.assertGreaterEqual(rows[0]["quote_age_minutes"], 0)
        self.assertGreater(rows[0]["turnover_gp_1h"], 0)

    def test_history_metrics_are_bounded(self):
        rows = [{"avgHighPrice": 100+i, "avgLowPrice": 98+i, "highPriceVolume": 10, "lowPriceVolume": 10} for i in range(20)]
        metrics = _metrics(rows)
        self.assertGreater(metrics["points"], 10)
        self.assertGreaterEqual(metrics["projection_confidence"], 0)
        self.assertLessEqual(metrics["projection_confidence"], 1)
        self.assertGreaterEqual(metrics["projected_6h_pct"], -.12)
        self.assertLessEqual(metrics["projected_6h_pct"], .12)

    def test_intelligence_schema_normalizes_drift(self):
        raw = {
            "market_mood": "busy", "regime": "momentum", "summary": "x",
            "notable_events": [{"title": "event", "type": "OFFICIAL", "source": "Jagex"}],
            "wallet_notes": {"Velocity": {"summary": "counterpoint"}},
            "watchlist": ["foo"],
        }
        normalized = normalize_intelligence(raw)
        self.assertEqual(normalized["notable_events"][0]["evidence_class"], "OFFICIAL")
        self.assertIsInstance(normalized["wallet_notes"], list)
        self.assertLessEqual(len(normalized["summary"]), 1600)


if __name__ == "__main__":
    unittest.main()
