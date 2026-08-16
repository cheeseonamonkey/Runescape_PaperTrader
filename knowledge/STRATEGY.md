# Strategy model — v0.3

The market layer is strategy-neutral. It computes spread, quote age, 5m/1h midpoint momentum, volume acceleration, turnover and liquidity once.

## Velocity
High-turnover flow wallet. Objective emphasizes momentum, volume acceleration and capital recycling. More slots, lower reserve, faster rotation.

## Market Maker
Liquidity-provision wallet. Objective emphasizes post-tax spread rent, completion probability, turnover/liquidity and adverse-selection control. Fewer slots, more patience.

Both wallets:
- start at 10M fake GP;
- maintain separate state, journals and equity histories;
- use deterministic sizing/exits;
- mark inventory conservatively to liquidation;
- treat AI as commentary only.

Historical diagnostics may alter candidate scores when available, but missing history must degrade to a neutral signal rather than blocking trading.
