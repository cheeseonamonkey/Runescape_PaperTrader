from dataclasses import dataclass
import os

VERSION = "0.5"
STARTING_GP = 10_000_000


@dataclass(frozen=True)
class StrategyProfile:
    slug: str
    name: str
    thesis: str
    modules: tuple[str, ...]
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
    mean_reversion_weight: float
    cross_factor_weight: float
    volatility_penalty_weight: float
    crowding_penalty_weight: float
    patch_weight: float
    ai_sensitivity: float
    ai_score_cap: float
    max_participation_rate: float
    conviction_sizing: float
    allow_scale_in: bool = False
    max_tranches: int = 1


PROFILES = {
    "velocity": StrategyProfile(
        slug="velocity",
        name="Velocity",
        thesis="Flow-following, high-turnover wallet: momentum + volume acceleration + fast capital recycling, with carry and regime overlays.",
        modules=("spread_carry", "momentum", "flow", "cross_factor", "history", "patch_control", "ai_prior"),
        max_positions=20,
        reserve_pct=.01,
        base_position_pct=.068,
        max_position_pct=.20,
        min_hourly_volume=50,
        min_5m_volume=5,
        min_expected_edge_gp=8,
        min_expected_roi=.0012,
        max_spread_roi=.11,
        quote_max_age_minutes=18,
        passive_entry_penalty=.0010,
        passive_exit_penalty=.0016,
        liquidation_slippage=.0030,
        take_profit=.006,
        stop_loss=-.024,
        soft_rotate_hours=1.75,
        max_hold_hours=6,
        edge_weight=.22,
        momentum_weight=.42,
        volume_accel_weight=.28,
        liquidity_weight=.12,
        historical_weight=.14,
        mean_reversion_weight=-.04,
        cross_factor_weight=.22,
        volatility_penalty_weight=.08,
        crowding_penalty_weight=.05,
        patch_weight=.07,
        ai_sensitivity=.55,
        ai_score_cap=5.0,
        max_participation_rate=.06,
        conviction_sizing=.22,
    ),
    "market_maker": StrategyProfile(
        slug="market_maker",
        name="Market Maker",
        thesis="Liquidity-provision wallet: spread rent + completion quality + low market impact, with selective reversion and catalyst control.",
        modules=("spread_carry", "liquidity", "mean_reversion", "history", "volatility_control", "patch_control", "ai_prior"),
        max_positions=14,
        reserve_pct=.035,
        base_position_pct=.078,
        max_position_pct=.18,
        min_hourly_volume=110,
        min_5m_volume=9,
        min_expected_edge_gp=18,
        min_expected_roi=.0018,
        max_spread_roi=.16,
        quote_max_age_minutes=26,
        passive_entry_penalty=.0006,
        passive_exit_penalty=.0010,
        liquidation_slippage=.0023,
        take_profit=.009,
        stop_loss=-.030,
        soft_rotate_hours=3.5,
        max_hold_hours=10,
        edge_weight=.48,
        momentum_weight=.08,
        volume_accel_weight=.08,
        liquidity_weight=.30,
        historical_weight=.14,
        mean_reversion_weight=.14,
        cross_factor_weight=.12,
        volatility_penalty_weight=.16,
        crowding_penalty_weight=.08,
        patch_weight=.10,
        ai_sensitivity=.42,
        ai_score_cap=4.0,
        max_participation_rate=.035,
        conviction_sizing=.14,
    ),
    "frontier": StrategyProfile(
        slug="frontier",
        name="Frontier Lab",
        thesis="Experimental high-risk ensemble: carry + trend + reversion + shock/catalyst interactions, convex sizing and bounded semantic priors.",
        modules=("spread_carry", "momentum", "flow", "mean_reversion", "cross_factor", "history", "volatility", "crowding", "patch_shock", "ai_prior", "pyramiding"),
        max_positions=22,
        reserve_pct=.005,
        base_position_pct=.085,
        max_position_pct=.25,
        min_hourly_volume=35,
        min_5m_volume=4,
        min_expected_edge_gp=5,
        min_expected_roi=.0007,
        max_spread_roi=.22,
        quote_max_age_minutes=16,
        passive_entry_penalty=.0012,
        passive_exit_penalty=.0018,
        liquidation_slippage=.0037,
        take_profit=.012,
        stop_loss=-.045,
        soft_rotate_hours=1.5,
        max_hold_hours=12,
        edge_weight=.22,
        momentum_weight=.24,
        volume_accel_weight=.18,
        liquidity_weight=.12,
        historical_weight=.14,
        mean_reversion_weight=.20,
        cross_factor_weight=.30,
        volatility_penalty_weight=.06,
        crowding_penalty_weight=.05,
        patch_weight=.18,
        ai_sensitivity=.90,
        ai_score_cap=9.0,
        max_participation_rate=.085,
        conviction_sizing=.48,
        allow_scale_in=True,
        max_tranches=3,
    ),
}

GE_TAX_RATE = .02
GE_TAX_CAP = 5_000_000
USER_AGENT = os.getenv("OSRS_WIKI_USER_AGENT", f"Runescape_PaperTrader/{VERSION} - github.com/cheeseonamonkey/Runescape_PaperTrader")

# Ling is intentionally tiny-cost here; qualitative priors are bounded and never own accounting.
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "inclusionai/ling-2.6-flash")
OPENROUTER_FREE_MODEL = os.getenv("OPENROUTER_FREE_MODEL", "openrouter/free")
OPENROUTER_SUBAGENT_MODEL = os.getenv("OPENROUTER_SUBAGENT_MODEL", "openrouter/free")
ENABLE_WEB_RESEARCH = os.getenv("ENABLE_WEB_RESEARCH", "0") == "1"
ENABLE_SUBAGENT = os.getenv("ENABLE_SUBAGENT", "0") == "1"
ENABLE_FREE_AUX = os.getenv("ENABLE_FREE_AUX", "1") == "1"
FREE_AUX_PASSES = max(0, min(3, int(os.getenv("FREE_AUX_PASSES", "2"))))
ADVISORY_EVERY_HOURS = max(1, int(os.getenv("ADVISORY_EVERY_HOURS", "4")))
INTELLIGENCE_EVERY_HOURS = max(1, int(os.getenv("INTELLIGENCE_EVERY_HOURS", "8")))
AI_PRIOR_MAX_AGE_HOURS = max(ADVISORY_EVERY_HOURS, int(os.getenv("AI_PRIOR_MAX_AGE_HOURS", "12")))
ENABLE_DDGS = os.getenv("ENABLE_DDGS", "1") == "1"
DDGS_EVERY_HOURS = max(1, int(os.getenv("DDGS_EVERY_HOURS", "8")))
HISTORY_EVERY_HOURS = max(1, int(os.getenv("HISTORY_EVERY_HOURS", "6")))
HISTORY_ITEMS = max(1, min(16, int(os.getenv("HISTORY_ITEMS", "8"))))
REPLAY_EVERY_HOURS = max(1, int(os.getenv("REPLAY_EVERY_HOURS", "8")))
REPLAY_HOURS = max(24, min(168, int(os.getenv("REPLAY_HOURS", "72"))))
REPLAY_ITEMS = max(8, min(40, int(os.getenv("REPLAY_ITEMS", "24"))))

# Usual OSRS weekly update window; configurable because Jagex can move/cancel it.
PATCH_WEEKDAY_UTC = max(0, min(6, int(os.getenv("PATCH_WEEKDAY_UTC", "2"))))  # Wednesday
PATCH_HOUR_UTC = max(0, min(23, int(os.getenv("PATCH_HOUR_UTC", "11"))))
PATCH_MINUTE_UTC = max(0, min(59, int(os.getenv("PATCH_MINUTE_UTC", "30"))))
