# Strategy

The trader is deterministic. The language model is an observer in v0.1.

Goals: prefer fresh, liquid opportunities with meaningful post-tax edge; preserve a cash reserve; cap concentration; exit winners, losers, and stale positions mechanically.

The engine models 2% GE seller tax (5m GP per-item cap) plus a small slippage haircut. It intentionally avoids stale quotes, low hourly volume, tiny post-tax edge, and implausibly wide spreads.
