# RuneScape PaperTrader v0.4

> Two fake 10M-GP funds compete on the same live OSRS economy tape. Deterministic execution tracks market microstructure; a cheap AI research sidecar reads catalysts and critiques; every hourly cycle leaves an audit trail.

**Real market observations. Fake GP. Two deterministic strategies. Shared research. Auditable maths.**

## v0.4: reliability release

v0.4 deliberately does not reinvent the project. It hardens what has now been running continuously for hours:

- fixes friction-induced stop-loss churn discovered in the live journal;
- migrates existing wallet positions without resetting them;
- keeps mark-to-liquidation P&L conservative while measuring stop-losses against **market movement**, not the simulator's own initial tax/slippage haircut;
- fixes entry-fill vs two-leg completion probability bookkeeping;
- ignores dangerously stale quotes for forced exits;
- caches historical diagnostics between refreshes instead of dropping the historical signal on non-refresh hours;
- caches periodic DDGS results and reports refresh/staleness state explicitly;
- normalizes and bounds AI output so provider/schema drift cannot balloon public history files;
- compacts the AI context packet;
- records a structured run audit for every successful trading cycle;
- adds an **Ops** view to Pages;
- adds a separate long-term reliability workflow with unit, ledger, archive, synthetic-regime and live-API testing.

## Two wallets, one economy

```text
latest + 5m + 1h Wiki market data
                 │
                 ▼
        shared feature vector
  spread · momentum · flow · liquidity
       turnover · freshness · history
                 │
         ┌──────┴────────┐
         ▼                ▼
      Velocity        Market Maker
         │                │
    independent       independent
    state / logs       state / logs
    P&L / exits        P&L / exits
         └───────┬────────┘
                 ▼
      research + intelligence
                 ▼
       public mobile terminal
```

Each wallet starts with **10,000,000 fake GP** and owns its cash, inventory, trade journal and equity curve independently.

### Velocity

High-turnover flow/momentum strategy. It places more weight on short-horizon price impulse, volume acceleration and capital recycling.

### Market Maker

Liquidity-provision/spread-capture strategy. It places more weight on post-tax microstructure rent, completion probability, turnover and adverse-selection control.

LLM output never calculates or mutates cash, P&L, position sizing or execution.

## Execution accounting

A candidates a passive entry and passive exit from the observable low/high market tape. The scoring model combines:

- post-tax spread rent;
- entry and exit fill probability;
- two-leg completion probability;
- inventory/adverse-selection penalty;
- short-horizon momentum;
- volume acceleration;
- liquidity/turnover;
- quote freshness;
- cached historical context.

Open inventory is conservatively valued at an estimated **mark-to-liquidation**:

```text
liquidation unit = observed low × (1 - modeled slippage) - GE tax
wallet equity    = cash + Σ(position qty × liquidation unit)
```

That accounting haircut exists immediately after a passive entry. v0.3 accidentally compared the stop-loss directly against that already-haircut mark, causing many positions to stop out almost immediately. v0.4 stores an **entry liquidation baseline**:

```text
reported P&L ROI = current liquidation / passive entry - 1
market-move ROI  = current liquidation / entry liquidation baseline - 1
```

Take-profit still requires actual net profitability. Stop-loss uses market-move ROI, so it responds to adverse movement rather than transaction-cost bookkeeping.

## Shared economy reference

Every cycle exposes a common market tape with:

- latest high/low observations;
- 5-minute and 1-hour average midpoints;
- spread and quote age;
- 5m/1h volume;
- volume acceleration;
- hourly GP turnover;
- liquidity proxy;
- strategy-specific opportunity books.

The public site is therefore both a paper-trading experiment and a compact OSRS economy reference.

## Historical calibration

Historical sampling is intentionally bounded. The Wiki timeseries layer calculates:

- hourly log-return volatility;
- price z-score;
- recent 6h trend;
- maximum drawdown;
- median hourly volume;
- bounded drift projection and rough noise-derived confidence.

v0.4 persists the last valid sample and reuses it between refreshes. A delayed GitHub scheduler can no longer accidentally erase historical features simply because it started in the wrong UTC hour.

## Research + cheap intelligence

Deterministic research:

- Jagex RSS every trading cycle;
- DDGS broader-web scout on a bounded refresh interval;
- cached historical price context.

OpenRouter intelligence:

- cheap primary qualitative analyst;
- selective server-side web search/fetch;
- optional subagent;
- `openrouter/free` auxiliary analyst critique;
- `openrouter/free` wallet red-team;
- `openrouter/free` deterministic-news triage.

v0.4 validates and bounds the AI-facing schema. Evidence labels are normalized to:

```text
OFFICIAL
CONFIRMED_COMMUNITY
COMMUNITY
RUMOR
MODEL_INFERENCE
```

Free-model failures are supplementary failures only; wallet execution continues.

## Every run is observable

Successful trading cycles now write a run record under:

```text
data/runs/YYYY-MM-DD/<github-run-id>.json
```

and a compact rolling index:

```text
data/runs/index.json
```

A run record includes:

- GitHub Actions run ID/link, trigger, SHA and attempt;
- wall-clock engine duration;
- scheduled-run delay from the nominal `:07` start;
- health status and warnings;
- tracked-market coverage;
- history/research cache state;
- primary AI model, status, token usage, tool calls, web-search count and reported cost;
- free-router success/unavailable counts;
- each wallet's equity, cash, P&L, positions, buys and sells.

The Pages **Ops** tab renders the recent run tape and links directly to GitHub Actions.

## Long-term quality suite

`.github/workflows/longterm-tests.yml` is separate from the trader and has **read-only repository permissions**. It cannot mutate wallet state.

Fast regression checks run on relevant pushes/PRs:

- Python compilation;
- browser JS syntax;
- focused unit/regression tests;
- persisted snapshot invariants;
- exact journal → cash/inventory ledger reconstruction;
- realized-P&L reconciliation;
- equity/archive chronology;
- strategy differentiation checks;
- deterministic synthetic microstructure stress matrix;
- static Pages build smoke test.

A scheduled/manual **deep** pass additionally runs:

- 500 seeded synthetic market cases across spread/momentum/flow/liquidity regimes;
- live read-only Wiki market/timeseries smoke tests;
- live Jagex RSS smoke test;
- an optional `openrouter/free` critique of the deterministic quality report, used only to propose missing tests or suspicious assumptions.

Test reports are uploaded as Actions artifacts and summarized directly on the workflow run.

## Persistence

```text
data/
├── latest_snapshot.json
├── historical/latest.json
├── research/latest.json
├── intelligence/
│   ├── latest.json
│   └── history.jsonl
├── runs/
│   ├── index.json
│   └── YYYY-MM-DD/<run-id>.json
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

Wallet state is schema-versioned and strategy-tagged. v0.4 migrates v0.3 inventory in place.

## Pages terminal

Mobile-first views:

- **Now** — wallet scoreboard, P&L, intelligence, inventory and opportunity book;
- **Market** — common economy tape, historical diagnostics and research;
- **Method** — execution assumptions and architecture;
- **History** — daily hourly wallet tape;
- **Ops** — workflow health, scheduler lag, AI cost/tool use and recent run status.

The UI remains intentionally restrained: dense typography, square-ish panels, thin borders, no giant cards or excessive decoration.

## Configuration

Required for AI:

```text
OPENROUTER_API_KEY
```

Optional repository variables:

```text
OPENROUTER_MODEL=openai/gpt-oss-20b
OPENROUTER_FREE_MODEL=openrouter/free
OPENROUTER_SUBAGENT_MODEL=openrouter/free
ENABLE_FREE_AUX=1
FREE_AUX_PASSES=3
ENABLE_WEB_RESEARCH=1
ENABLE_SUBAGENT=0
ENABLE_DDGS=1
DDGS_EVERY_HOURS=6
HISTORY_EVERY_HOURS=6
HISTORY_ITEMS=5
OSRS_WIKI_USER_AGENT=Runescape_PaperTrader/0.4 - your contact
```

## Run locally

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 scripts/run.py
python3 scripts/build_site.py
python3 -m http.server -d public 8000
```

Long-term deterministic audit:

```bash
python3 scripts/longterm_test.py --mode deep
```

Reset both fake wallets:

```bash
python3 scripts/run.py --reset
```

## Caveat

This remains a research toy, not a real Grand Exchange execution simulator. Public Wiki observations are not guaranteed fills; fill probability, slippage, adverse-selection costs and projections are explicit heuristics. The point of the accumulated journals and test suite is to make those assumptions measurable and replaceable rather than hiding them behind an “AI trader” label.
