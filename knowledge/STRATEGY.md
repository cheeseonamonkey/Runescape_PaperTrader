# v0.2 strategy: aggressive microstructure

v0.2 is deliberately higher-turnover. It attempts to capture the bid/ask spread with passive paper orders while treating an immediate liquidation as a separate, more conservative mark.

Core signals: post-tax expected edge, 5-minute vs 1-hour midpoint momentum, normalized 5-minute volume acceleration, hourly GP turnover, quote freshness, and an explicit adverse-selection penalty.

Capital is allocated from an equity-based risk budget rather than a percentage of remaining cash. Better liquidity and supportive momentum can earn a larger allocation, but deterministic caps and the GE buy limit remain binding. Inventory rotates after three hours when a thesis is not paying and is forcibly liquidated after eight hours.

This is a paper model. Observed Wiki high/low prices are market observations, not guaranteed executable orders; estimated fill probabilities are heuristics, not calibrated probabilities.
