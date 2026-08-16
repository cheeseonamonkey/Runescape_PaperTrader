import unittest
from datetime import datetime, timezone, timedelta

from src.config import PROFILES, STARTING_GP
from src.strategy import ge_tax, liquidation_unit, entry_liquidation_baseline, common_features, economy_metrics, wallet_candidates
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
        now = datetime.now(timezone.utc)
        wallet = fresh_wallet(profile)
        wallet["cash_gp"] -= entry * 10
        wallet["positions"] = [{
            "item_id": 1, "name": "fixture", "qty": 10, "entry_price": entry,
            "entry_liquidation_unit": baseline, "opened_at": (now - timedelta(minutes=5)).isoformat(),
            "entry_expected_roi": .03, "entry_momentum": .02,
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
            "entry_expected_roi": .03, "entry_momentum": .02,
        }]
        moved_low = int(low * .96)
        trades = close_positions(wallet, {"1": {"low": moved_low, "lowTime": int(now.timestamp())}}, profile, now=now)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["reason"], "stop_loss")
        self.assertLess(trades[0]["market_move_roi"], profile.stop_loss)

    def test_stale_quote_does_not_force_exit(self):
        profile = PROFILES["velocity"]
        now = datetime.now(timezone.utc)
        wallet = fresh_wallet(profile)
        wallet["positions"] = [{
            "item_id": 1, "name": "fixture", "qty": 1, "entry_price": 10_000,
            "entry_liquidation_unit": entry_liquidation_baseline(10_000, profile),
            "opened_at": (now - timedelta(hours=10)).isoformat(),
            "entry_expected_roi": .03, "entry_momentum": -.1,
        }]
        stale = int((now - timedelta(hours=3)).timestamp())
        self.assertEqual(close_positions(wallet, {"1": {"low": 8_000, "lowTime": stale}}, profile, now=now), [])

    def test_open_records_entry_fill_not_completion_probability(self):
        profile = PROFILES["market_maker"]
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        wallet = fresh_wallet(profile)
        candidate = {
            "id": 5, "name": "fixture", "passive_entry": 1000, "low": 999, "risk_budget_pct": .1,
            "limit": 1000, "entry_fill_probability": .8, "fill_probability": .5,
            "score": 100, "expected_roi": .02, "momentum_5m_vs_1h": .01,
        }
        trades = open_positions(wallet, [candidate], {"5": {"low": 999}}, profile, now=now)
        self.assertEqual(len(trades), 1)
        self.assertEqual(wallet["positions"][0]["entry_fill_probability"], .8)
        self.assertEqual(wallet["positions"][0]["entry_completion_probability"], .5)
        self.assertEqual(wallet["positions"][0]["opened_at"], now.isoformat())
        self.assertGreaterEqual(wallet["cash_gp"], 0)

    def test_normalize_migrates_old_position(self):
        profile = PROFILES["velocity"]
        state = {"strategy_id": "velocity", "cash_gp": 1, "positions": [{"item_id": 1, "name": "x", "qty": 1, "entry_price": 100, "opened_at": datetime.now(timezone.utc).isoformat()}], "realized_pnl_gp": 0}
        migrated = normalize_wallet(state, profile)
        self.assertEqual(migrated["schema"], 2)
        self.assertIn("entry_liquidation_unit", migrated["positions"][0])


class FeatureTests(unittest.TestCase):
    def _rows(self):
        return [
            {"id": 1, "name": "a", "limit": 1000, "high": 11500, "low": 10000, "spread_roi": .15,
             "momentum_5m_vs_1h": .02, "volume_5m": 60, "volume_1h": 500, "volume_acceleration": .5,
             "turnover_gp_1h": 5_000_000, "liquidity_score": .75, "quote_age_minutes": 0},
            {"id": 2, "name": "b", "limit": 1000, "high": 20500, "low": 20000, "spread_roi": .025,
             "momentum_5m_vs_1h": -.01, "volume_5m": 40, "volume_1h": 400, "volume_acceleration": -.2,
             "turnover_gp_1h": 8_000_000, "liquidity_score": .80, "quote_age_minutes": 0},
        ]

    def test_common_features_are_sane(self):
        now = int(datetime.now(timezone.utc).timestamp())
        latest = {"1": {"high": 110, "low": 100, "highTime": now, "lowTime": now}}
        five = {"1": {"avgHighPrice": 108, "avgLowPrice": 102, "highPriceVolume": 10, "lowPriceVolume": 10}}
        hourly = {"1": {"avgHighPrice": 105, "avgLowPrice": 100, "highPriceVolume": 100, "lowPriceVolume": 100}}
        rows = common_features(latest, five, hourly, {"1": {"name": "fixture", "limit": 100}})
        self.assertEqual(len(rows), 1)
        self.assertGreaterEqual(rows[0]["quote_age_minutes"], 0)
        self.assertGreater(rows[0]["turnover_gp_1h"], 0)

    def test_economy_metrics_are_bounded(self):
        e = economy_metrics(self._rows())
        self.assertGreaterEqual(e["breadth"], -1)
        self.assertLessEqual(e["breadth"], 1)
        self.assertGreaterEqual(e["top10_turnover_share"], 0)
        self.assertLessEqual(e["top10_turnover_share"], 1)
        self.assertGreaterEqual(e["turnover_hhi"], 0)
        self.assertLessEqual(e["turnover_hhi"], 1)

    def test_score_components_sum_to_score(self):
        rows = wallet_candidates(self._rows(), PROFILES["market_maker"], None)
        self.assertTrue(rows)
        row = rows[0]
        self.assertAlmostEqual(sum(row["score_components"].values()), row["score"], places=2)
        self.assertAlmostEqual(row["spread_capture_ev_gp"] - row["inventory_risk_ev_gp"], row["expected_edge_gp"], places=2)

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
        self.assertEqual(normalized["economy_brief"], "x")


if __name__ == "__main__":
    unittest.main()
