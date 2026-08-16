from dataclasses import dataclass
import os

VERSION = "0.2"

@dataclass(frozen=True)
class StrategyConfig:
    starting_gp: int = 10_000_000
    max_positions: int = 14
    reserve_pct: float = 0.03
    base_position_pct: float = 0.075
    max_position_pct: float = 0.16
    min_hourly_volume: int = 80
    min_5m_volume: int = 8
    min_expected_edge_gp: int = 20
    min_expected_roi: float = 0.0020
    max_spread_roi: float = 0.14
    quote_max_age_minutes: int = 24
    passive_entry_penalty: float = 0.0008
    passive_exit_penalty: float = 0.0012
    liquidation_slippage: float = 0.0025
    ge_tax_rate: float = 0.02
    ge_tax_cap: int = 5_000_000
    take_profit: float = 0.008
    stop_loss: float = -0.028
    soft_rotate_hours: float = 3.0
    max_hold_hours: float = 8.0
    momentum_weight: float = 0.35
    volume_accel_weight: float = 0.18
    liquidity_weight: float = 0.22
    edge_weight: float = 0.45
    concentration_penalty: float = 0.15

CFG = StrategyConfig()
USER_AGENT = os.getenv("OSRS_WIKI_USER_AGENT", f"Runescape_PaperTrader/{VERSION} - github.com/cheeseonamonkey/Runescape_PaperTrader")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b")
OPENROUTER_FREE_MODEL = os.getenv("OPENROUTER_FREE_MODEL", "openrouter/free")
OPENROUTER_SUBAGENT_MODEL = os.getenv("OPENROUTER_SUBAGENT_MODEL", "openrouter/free")
ENABLE_WEB_RESEARCH = os.getenv("ENABLE_WEB_RESEARCH", "1") == "1"
ENABLE_SUBAGENT = os.getenv("ENABLE_SUBAGENT", "0") == "1"
ENABLE_FREE_SANITY_PASS = os.getenv("ENABLE_FREE_SANITY_PASS", "1") == "1"
ENABLE_DDGS = os.getenv("ENABLE_DDGS", "1") == "1"
DDGS_EVERY_HOURS = max(1, int(os.getenv("DDGS_EVERY_HOURS", "6")))
