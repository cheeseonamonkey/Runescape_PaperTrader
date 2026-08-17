# RuneScape PaperTrader v0.5

> Three fake 10M-GP funds compete on the same live OSRS economy tape. Deterministic execution owns accounting and market math; a deliberately weak semantic ensemble contributes only bounded priors.

**Real market observations. Fake GP. Three independent funds. Shared economics. Auditable maths.**

## v0.5 — economics + ensemble release

v0.5 expands the project from a two-wallet trading dashboard into a small experimental market laboratory:

- **Net worth** is the primary fund value; **Liquid GP** is cash/liquidity, not the whole portfolio.
- adds **Frontier Lab**, an intentionally high-risk experimental third strategy;
- expands the common market layer into a broader cross-sectional economics ledger;
- lets cheap LLMs contribute a small, explicitly capped semantic prior to scoring and sizing;
- separates the **4h advisory prior** from the slower **8h State of the Economy report**;
- sends the same advisory packet to one tiny-cost paid anchor plus two `openrouter/free` peers by default;
- adds deterministic awareness of the usual weekly update window, while keeping actual news as a separate evidence source;
- adds current-thesis decay to exits, volume-participation capacity limits, conviction sizing and Frontier pyramiding;
- adds a per-fund expandable action tape with the deterministic reasoning/math behind each buy/sell;
- expands Pages with a compact economics table, strategy layers, report history and a client-side factor what-if mixer;
- fixes the 72h replay so historical patch risk uses each replay timestamp rather than today's clock;
- preserves the last valid semantic report/prior if an LLM refresh fails.

## Three funds, one economy

```text
Wiki latest + 5m + 1h market data
              │
              ▼
      full common market state
spread · momentum · flow · turnover · liquidity
imbalance · impact · concentration · freshness
              │
              ├──────── economics cross-section
              │         breadth · pressure · HHI/Gini
              │         stress · temperature · patch prior
              │
              ├──────── bounded semantic advisory
              │         paid tiny model + free peers
              │         macro/item priors only
              │
        ┌─────┼──────────────┐
        ▼     ▼              ▼
   Velocity  Market Maker  Frontier Lab
        │     │              │
        └──── independent cash / holdings / journals
              │
              ▼
       mobile economy terminal
```

Each fund starts with **10,000,000 fake GP**. State, holdings, journals, realized P&L and net-worth curves remain independent.

### Velocity

High-turnover flow follower. Its stack emphasizes:

- momentum;
- volume acceleration;
- cross-factor confirmation;
- spread carry;
- fast capital recycling;
- light history/patch/semantic overlays.

### Market Maker

Liquidity/spread-capture strategy. Its stack emphasizes:

- post-tax spread rent;
- completion probability;
- liquidity;
- selective mean reversion;
- volatility and crowding control;
- conservative capacity participation.

### Frontier Lab

The experimental/high-risk fund. It deliberately combines more lenses:

- spread carry;
- trend and flow;
- mean reversion;
- interaction terms;
- historical state;
- volatility/shock behavior;
- crowding;
- patch-window shock logic;
- bounded semantic priors;
- conviction-weighted sizing;
- **pyramiding** into strengthening positions, up to a small tranche limit.

Frontier is intentionally the least conservative model, but it still cannot bypass cash, GE item limits, observed-volume capacity, fill assumptions or portfolio caps.

## Net worth vs Liquid GP

The public UI now treats the balance sheet correctly:

```text
net worth = liquid GP + Σ(mark-to-liquidation value of holdings)
```

Open inventory is marked conservatively:

```text
liquidation unit ≈ observed low × (1 − modeled slippage) − GE tax
```

So **Liquid GP** is immediately spendable cash; it is not the fund's total value.

## Candidate economics

The two-leg execution model remains explicit:

```text
completion probability
  = P(entry fill) × P(exit fill)

inventory-state probability
  = P(entry fill) × [1 − P(exit fill)]

spread-capture EV
  = completion probability × post-tax quoted edge

inventory-risk EV
  = inventory-state probability × adverse-selection cost

expected edge
  = spread-capture EV − inventory-risk EV
```

A candidate then receives profile-specific factor contributions:

```text
score = edge
      + momentum
      + flow
      + liquidity
      + history
      + mean reversion
      + cross-factor interaction
      − volatility / crowding controls
      + patch term
      + bounded AI prior
      + freshness
```

The score is an **ordinal objective, not a probability**. Every contribution is persisted so Pages can show exactly why a candidate ranked where it did.

## Conviction, sizing and capacity

v0.5 derives additional values from the factor state:

- factor-consensus **conviction**;
- a clearly labeled **Kelly-inspired sizing proxy**;
- profile-specific deterministic risk budget;
- bounded semantic risk multiplier;
- observed-volume participation capacity;
- GE item-limit capacity where available.

Final quantity is constrained by cash, portfolio risk, item limits and a profile-specific fraction of observed hourly volume. The market tape therefore limits fantasy fills instead of allowing arbitrary paper size.

## Economics ledger

The engine ingests the full valid common-market cross-section every hour. The browser publishes only a bounded hot subset of individual item rows so the Git repository does not balloon needlessly.

The aggregate layer now includes:

### Direction

- raw breadth;
- turnover-weighted breadth;
- turnover-weighted price pressure;
- median momentum;
- median absolute momentum;
- momentum dispersion;
- advancing / declining / flat counts.

### Activity / flow

- active share;
- median and P90 volume acceleration;
- turnover-weighted high/low transaction-volume imbalance;
- shock share;
- total hourly GP turnover;
- total hourly unit volume;
- median item turnover.

### Liquidity / friction

- median spread;
- turnover-weighted spread;
- spread dispersion;
- median liquidity;
- stale-quote share;
- extreme-spread share;
- composite liquidity-stress proxy.

### Concentration

- top-1 / top-5 / top-10 turnover shares;
- turnover HHI;
- turnover Gini;
- members-item turnover share.

### Regime / risk

- risk-appetite proxy;
- market-temperature index;
- usual weekly update-window phase and proximity risk.

These are descriptive short-run market-structure proxies. They are not labeled CPI, inflation, sentiment truth or calibrated probabilities when they are not those things.

## Cheap semantic ensemble

v0.5 intentionally gives language models **less authority and less cadence**.

Default paid anchor:

```text
OPENROUTER_MODEL=inclusionai/ling-2.6-flash
```

Default cadence:

```text
advisory prior       every 4h
State of Economy     every 8h
free advisory peers  2 per advisory refresh
```

The advisory packet is shared across the ensemble and contains deterministic derived inputs:

- economy metrics;
- largest turnover names;
- largest movers;
- strongest volume acceleration;
- cached historical diagnostics;
- official/community research;
- prior portfolio diagnostics and recent actions;
- patch-window prior.

The ensemble may return only bounded qualitative priors:

```text
macro
momentum
mean_reversion
liquidity
risk
patch_risk
small per-item bias
confidence
```

The engine converts those into a capped additive score term and a small sizing multiplier. Approximate score caps are intentionally tiny relative to the full deterministic score:

- Market Maker: ±4 points;
- Velocity: ±5 points;
- Frontier Lab: ±9 points.

LLM output never directly writes:

- market prices;
- tax;
- P&L;
- cash;
- fills;
- quantities;
- holdings;
- journal state.

If a semantic refresh fails, the engine can reuse a recent last-known-good prior/report with explicit stale-cache status. Trading math continues without it once the prior ages out.

## Weekly update awareness

The engine carries a configurable **usual weekly update schedule prior**. Proximity affects deterministic patch/catalyst risk, especially for Frontier Lab.

That schedule prior is not treated as proof that an update is actually shipping. Jagex RSS/news remains a separate evidence layer supplied to the semantic analyst.

Configuration:

```text
PATCH_WEEKDAY_UTC=2
PATCH_HOUR_UTC=11
PATCH_MINUTE_UTC=30
```

## Fund action tape

Each fund's journal remains the accounting record. v0.5 also exposes a compact recent-action tape to Pages.

A BUY can show:

- cost and quantity;
- expected ROI;
- fill/completion assumptions;
- conviction;
- capacity;
- strongest score contributions;
- strategy-lens values;
- AI-prior contribution;
- Kelly-inspired proxy;
- patch term;
- human-readable deterministic reason.

A SELL can show:

- realized P&L;
- net ROI;
- market-move ROI;
- holding time;
- take-profit / stop / rotation / max-hold reason;
- entry score versus current score when available.

## 72h replay

The read-only diagnostic replay continues to rebuild each fund from 10M GP over a bounded 1h historical tape.

v0.5 fixes two important replay semantics:

- the weekly patch prior is evaluated at each historical timestamp rather than using today's clock;
- current replay candidate signals are supplied to thesis-decay exits.

The semantic LLM prior is deliberately disabled in replay. This keeps the diagnostic deterministic and reproducible.

It is still not a claim of exact GE queue execution: 1h bars cannot reconstruct intrahour order priority or every fill path.

## Pages terminal

Primary navigation:

- **General** — three-fund net-worth board, economy pulse, model prior and slow economy brief;
- **Traders** — one fund at a time: net worth, liquidity, holdings, portfolio economics, opportunity attribution and action tape;
- **Items** — bounded hot commodity tape;
- **Economy** — compact full economics ledger + replay;
- **More** — Research, Reports, History, Ops and Method.

Method includes a **client-side what-if factor mixer**. It can toggle existing score contributions for inspection, but it cannot mutate the live trading configuration. Production strategy changes remain code/version controlled.

## Persistence

```text
data/
├── latest_snapshot.json
├── historical/latest.json
├── research/latest.json
├── simulations/latest_72h.json
├── intelligence/
│   ├── advisory.json
│   ├── advisory_history.jsonl
│   ├── latest.json
│   └── history.jsonl
├── runs/
│   ├── index.json
│   └── YYYY-MM-DD/<run-id>.json
├── wallets/
│   ├── velocity/
│   ├── market_maker/
│   └── frontier/
└── days/
    ├── index.json
    └── YYYY-MM-DD.json
```

Legacy two-fund state migrates in place. Frontier begins as a new independent 10M-GP paper fund on its first v0.5 trading cycle.

## Quality / observability

Every live trading cycle still writes a structured run record with:

- GitHub run metadata;
- market coverage;
- cache/research status;
- separate advisory/report cadence and token/cost accounting;
- health warnings;
- every fund's net worth, cash, P&L, holdings and action counts.

The read-only long-term workflow still checks:

- Python compilation;
- JS syntax;
- unit/regression tests;
- snapshot invariants;
- journal → cash/inventory reconstruction;
- realized-P&L reconciliation;
- archive chronology;
- synthetic strategy stress;
- live read-only market/API smoke tests;
- optional free-router test critique.

## Configuration

Required only for model features:

```text
OPENROUTER_API_KEY
```

Useful repository variables:

```text
OPENROUTER_MODEL=inclusionai/ling-2.6-flash
OPENROUTER_FREE_MODEL=openrouter/free
ENABLE_WEB_RESEARCH=0
ENABLE_SUBAGENT=0
ENABLE_FREE_AUX=1
FREE_AUX_PASSES=2
ADVISORY_EVERY_HOURS=4
INTELLIGENCE_EVERY_HOURS=8
AI_PRIOR_MAX_AGE_HOURS=12
ENABLE_DDGS=1
DDGS_EVERY_HOURS=8
HISTORY_EVERY_HOURS=6
HISTORY_ITEMS=8
REPLAY_EVERY_HOURS=8
REPLAY_HOURS=72
REPLAY_ITEMS=24
PATCH_WEEKDAY_UTC=2
PATCH_HOUR_UTC=11
PATCH_MINUTE_UTC=30
OSRS_WIKI_USER_AGENT=Runescape_PaperTrader/0.5 - your contact
```

## Run locally

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 scripts/run.py
python3 scripts/build_site.py
python3 -m http.server -d public 8000
```

Read-only deterministic quality pass:

```bash
python3 scripts/longterm_test.py --mode deep
```
