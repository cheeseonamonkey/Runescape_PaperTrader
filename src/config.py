from dataclasses import dataclass
import os

@dataclass(frozen=True)
class StrategyConfig:
    starting_gp: int = 10_000_000
    max_positions: int = 8
    max_position_pct: float = 0.14
    reserve_pct: float = 0.10
    min_hourly_volume: int = 250
    min_edge_gp: int = 60
    min_edge_roi: float = 0.004
    max_spread_roi: float = 0.18
    take_profit: float = 0.012
    stop_loss: float = -0.035
    max_hold_hours: int = 18
    quote_max_age_minutes: int = 30
    slippage_pct: float = 0.0015
    ge_tax_rate: float = 0.02
    ge_tax_cap: int = 5_000_000

CFG = StrategyConfig()
USER_AGENT = os.getenv("OSRS_WIKI_USER_AGENT", "Runescape_PaperTrader/0.1 - github.com/cheeseonamonkey/Runescape_PaperTrader")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b")
OPENROUTER_SUBAGENT_MODEL = os.getenv("OPENROUTER_SUBAGENT_MODEL", "openai/gpt-oss-20b")
ENABLE_WEB_RESEARCH = os.getenv("ENABLE_WEB_RESEARCH", "1") == "1"
ENABLE_SUBAGENT = os.getenv("ENABLE_SUBAGENT", "0") == "1"
