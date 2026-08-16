# RuneScape PaperTrader v0.3

> Two fake 10M-GP funds compete on the same OSRS market tape while a shared economy terminal tracks microstructure, history, Jagex news, community chatter and cheap AI critiques.

**Real market observations. Fake GP. Two deterministic strategies. Shared research. Auditable maths.**

## Two wallets, one market

v0.3 separates **market facts** from **strategy opinions**.

```text
latest + 5m + 1h OSRS prices
            │
            ▼
     common feature vector
  spread · momentum · flow
 liquidity · turnover · age
            │
     ┌──────┴──────┐
     ▼             ▼
  Velocity     Market Maker
     │             │
 independent    independent
 state/log/P&L  state/log/P&L
     └──────┬──────┘
            ▼
  shared research + terminal
```

Each wallet begins with **10,000,000 fake GP**. They do not share cash, positions, trades, equity curves or execution policy.

### Velocity

A high-turnover **flow/momentum** strategy. It pays more attention to short-horizon price impulse, volume acceleration and opportunity cost, keeps almost no strategic cash idle, opens more positions, and rotates stale inventory quickly.

### Market Maker

A **liquidity-provision / spread-capture** strategy. It pays more attention to post-tax microstructure rent, completion probability, turnover, liquidity and adverse-selection risk. It carries fewer positions and gives a thesis more time to work.

Neither wallet uses LLM output to calculate or execute anything.

## Shared market economics

The common layer computes the observable state once:

- latest high/low transaction observations
- 5-minute and 1-hour average midpoints
- raw spread
- quote age
- 5m and 1h volume
- volume acceleration
- hourly GP turnover
- liquidity proxy

Each wallet then transforms that same feature vector into its own passive entry/exit assumptions, expected edge, objective score and risk budget.

This avoids a subtle failure mode: strategy implementations should disagree about **preferences**, not silently disagree about the underlying market observations.

## Historical calibration

Periodically, v0.3 samples the Wiki `/timeseries` endpoint for the strongest common-market items. The historical layer computes lightweight diagnostics:

- hourly log-return volatility
- rolling mean / price z-score
- recent 6h trend
- maximum drawdown over the fetched window
- median hourly volume
- bounded 6h drift projection + rough noise-derived confidence

These are **diagnostics and features**, not a claim of a calibrated forecasting model. Historical collection is intentionally bounded so the hourly workflow does not hammer the public API.

## Cheap intelligence stack

The paid-cheap OpenRouter analyst is the primary semantic pass. It can selectively use server-side web search/fetch and optional subagents.

`openrouter/free` is used more aggressively for disposable supplementary work:

1. **analyst critique** — unsupported certainty, stale catalysts, missing counterarguments;
2. **wallet red-team** — why each strategy thesis could fail in the present regime;
3. **news triage** — important deterministic headlines versus likely noise/repetition.

Free-router failures never block trading, persistence or Pages deployment.

Deterministic research remains shared:

- Jagex RSS every run;
- DDGS broader-web scout periodically;
- historical price context periodically.

## Persistence

```text
data/
├── latest_snapshot.json          # common terminal payload
├── intelligence/
│   ├── latest.json
│   └── history.jsonl
├── wallets/
│   ├── velocity/
│   │   ├── portfolio.json
│   │   ├── latest.json
│   │   ├── journal.jsonl
│   │   └── equity_history.jsonl
│   └── market_maker/
│       └── ...
└── days/
    ├── index.json
    └── YYYY-MM-DD.json
```

Wallet state carries an explicit `strategy_id` and schema version. A missing/mismatched state file initializes that wallet rather than silently interpreting another strategy's inventory.

## Public terminal

The mobile-first Pages UI exposes:

- wallet scoreboard and instant wallet switching;
- independent equity, cash, realized/unrealized P&L and inventory;
- each wallet's ranked opportunity book;
- shared high-turnover economy tape;
- historical calibration/projection diagnostics;
- official Jagex and periodic web research;
- primary AI market read plus free-router critiques;
- daily wallet tape with older/newer navigation;
- implementation/methodology details.

The UI remains deliberately compact: square-ish panels, dense tables, small typography, no gradients or giant rounded dashboard cards.

## Configuration

Required for AI:

```text
OPENROUTER_API_KEY
```

Useful repository variables:

```text
OPENROUTER_MODEL=openai/gpt-oss-20b
OPENROUTER_FREE_MODEL=openrouter/free
ENABLE_FREE_AUX=1
FREE_AUX_PASSES=3
ENABLE_WEB_RESEARCH=1
ENABLE_SUBAGENT=0
ENABLE_DDGS=1
DDGS_EVERY_HOURS=6
HISTORY_EVERY_HOURS=6
HISTORY_ITEMS=5
OSRS_WIKI_USER_AGENT=Runescape_PaperTrader/0.3 - your contact
```

## Run

```bash
python3 -m pip install -r requirements.txt
python3 scripts/run.py
python3 scripts/build_site.py
python3 -m http.server -d public 8000
```

Reset **both** wallets:

```bash
python3 scripts/run.py --reset
```

## Caveats

This remains a research toy, not a real execution simulator. Wiki observations are not guaranteed fills. Fill probabilities, adverse-selection costs and projections are explicit heuristics. That is intentional: v0.3 records independent wallet outcomes so those assumptions can later be challenged, calibrated or replaced rather than hidden behind vague “AI trading” claims.
