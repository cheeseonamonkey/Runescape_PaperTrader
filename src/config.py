from dataclasses import dataclass
import os

VERSION = "0.4"
STARTING_GP = 10_000_000

@dataclass(frozen=True)
class StrategyProfile:
    slug: str
    name: str
    thesis: str
    max_positions: int
    reserve_pct: float
    base_position_pct: float
    max_position_pct: float
    min_hourly_volume: int
    min_5m_volume: int
    min_expected_edge_gp: int
    min_expected_roi: float
    max_spread_roi: float
    quote_max_age_minutes: int
    passive_entry_penalty: float
    passive_exit_penalty: float
    liquidation_slippage: float
    take_profit: float
    stop_loss: float
    soft_rotate_hours: float
    max_hold_hours: float
    edge_weight: float
    momentum_weight: float
    volume_accel_weight: float
    liquidity_weight: float
    historical_weight: float

PROFILES = {
    "velocity": StrategyProfile(
        slug="velocity", name="Velocity",
        thesis="Flow-following, high-turnover wallet: pays for momentum, volume acceleration and fast capital recycling.",
        max_positions=18, reserve_pct=.01, base_position_pct=.065, max_position_pct=.18,
        min_hourly_volume=50, min_5m_volume=5, min_expected_edge_gp=8, min_expected_roi=.0012,
        max_spread_roi=.11, quote_max_age_minutes=18, passive_entry_penalty=.0010,
        passive_exit_penalty=.0016, liquidation_slippage=.0030, take_profit=.006,
        stop_loss=-.024, soft_rotate_hours=1.75, max_hold_hours=6,
        edge_weight=.24, momentum_weight=.48, volume_accel_weight=.28,
        liquidity_weight=.14, historical_weight=.16),
    "market_maker": StrategyProfile(
        slug="market_maker", name="Market Maker",
        thesis="Liquidity-provision wallet: emphasizes spread rent, completion probability, turnover and adverse-selection control.",
        max_positions=12, reserve_pct=.04, base_position_pct=.075, max_position_pct=.16,
        min_hourly_volume=110, min_5m_volume=9, min_expected_edge_gp=18, min_expected_roi=.0018,
        max_spread_roi=.16, quote_max_age_minutes=26, passive_entry_penalty=.0006,
        passive_exit_penalty=.0010, liquidation_slippage=.0023, take_profit=.009,
        stop_loss=-.030, soft_rotate_hours=3.5, max_hold_hours=10,
        edge_weight=.54, momentum_weight=.10, volume_accel_weight=.10,
        liquidity_weight=.34, historical_weight=.18),
}

GE_TAX_RATE = .02
GE_TAX_CAP = 5_000_000
USER_AGENT = os.getenv("OSRS_WIKI_USER_AGENT", f"Runescape_PaperTrader/{VERSION} - github.com/cheeseonamonkey/Runescape_PaperTrader")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b")
OPENROUTER_FREE_MODEL = os.getenv("OPENROUTER_FREE_MODEL", "openrouter/free")
OPENROUTER_SUBAGENT_MODEL = os.getenv("OPENROUTER_SUBAGENT_MODEL", "openrouter/free")
ENABLE_WEB_RESEARCH = os.getenv("ENABLE_WEB_RESEARCH", "1") == "1"
ENABLE_SUBAGENT = os.getenv("ENABLE_SUBAGENT", "0") == "1"
ENABLE_FREE_AUX = os.getenv("ENABLE_FREE_AUX", "1") == "1"
FREE_AUX_PASSES = max(0, min(3, int(os.getenv("FREE_AUX_PASSES", "3"))))
INTELLIGENCE_EVERY_HOURS = max(1, int(os.getenv("INTELLIGENCE_EVERY_HOURS", "2")))
ENABLE_DDGS = os.getenv("ENABLE_DDGS", "1") == "1"
DDGS_EVERY_HOURS = max(1, int(os.getenv("DDGS_EVERY_HOURS", "6")))
HISTORY_EVERY_HOURS = max(1, int(os.getenv("HISTORY_EVERY_HOURS", "6")))
HISTORY_ITEMS = max(1, min(8, int(os.getenv("HISTORY_ITEMS", "5"))))
REPLAY_EVERY_HOURS = max(1, int(os.getenv("REPLAY_EVERY_HOURS", "6")))
REPLAY_HOURS = max(24, min(168, int(os.getenv("REPLAY_HOURS", "72"))))
REPLAY_ITEMS = max(8, min(40, int(os.getenv("REPLAY_ITEMS", "24"))))
