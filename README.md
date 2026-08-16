# RuneScape PaperTrader v0.2

> A 10M-GP fake fund watching the OSRS Grand Exchange every hour: deterministic microstructure trading, live economy telemetry, Jagex/community research, and a compact public market terminal.

**Real OSRS market data. Fake GP. Auditable maths. Cheap AI for semantics only.**

## v0.2 in one screen

```text
Wiki latest + 5m + 1h prices
        │
        ├─ microstructure engine
        │   ├─ passive spread capture
        │   ├─ momentum + volume acceleration
        │   ├─ liquidity / turnover
        │   ├─ adverse-selection-adjusted EV
        │   └─ adaptive deterministic risk budget
        │
        ├─ deterministic research
        │   ├─ Jagex RSS every hour
        │   └─ DDGS scout periodically
        │
        └─ OpenRouter analyst
            ├─ selective web_search / web_fetch
            ├─ optional subagent
            └─ optional openrouter/free sanity pass
                    ↓
          mobile-first economy terminal
```

v0.2 is not merely a simulated portfolio. The Pages site is intended to function as a compact **OSRS economy guide / live reference**: current opportunity set, live inventory, market regime, catalysts, official news, community-search results, methodology, and navigable daily tape.

## Aggressive strategy

The v0.1 spread model conflated immediate-buy and immediate-sell observations and therefore made spread capture structurally unattractive. v0.2 separates three concepts:

- **Passive entry:** estimate a limit buy near the observed low.
- **Passive exit:** estimate a limit sell near the observed high, after GE tax.
- **Mark-to-liquidation:** conservative value if inventory had to be dumped near the observed low with extra slippage.

Candidate ranking then incorporates:

| Signal | Economic interpretation |
|---|---|
| post-tax spread | gross microstructure rent available to a market maker |
| expected edge | spread rent discounted by heuristic fill probability and adverse selection |
| 5m / 1h momentum | short-horizon price impulse |
| volume acceleration | whether current flow is unusually intense versus the last hour |
| hourly GP turnover | liquidity / likely capacity |
| quote freshness | staleness / information risk |
| risk budget | deterministic position allocation driven by signal quality and liquidity |

Defaults are intentionally punchier: up to **14 positions**, only **3% reserve**, position risk budgets up to **16% of equity**, **+0.8% take-profit**, **-2.8% stop**, thesis rotation after **3h**, hard exit after **8h**.

None of the fill probabilities are claimed to be statistically calibrated. They are explicit heuristics so they can be measured and replaced later.

## Research stack

Every run gets official Jagex RSS deterministically. Every six hours by default, a best-effort `ddgs` query scouts the broader web for the strongest current candidates and economy news. The result is supplied to OpenRouter as context before the model decides whether server-side search is worth spending money on.

The primary model is intentionally cheap. `openrouter/free` is used for a disposable second-opinion/sanity pass only. Server-side subagents remain optional.

AI never owns P&L, tax, pricing, position sizing, execution, or bankroll mutation.

## Mobile market terminal

The Pages UI has four dense views:

- **Now:** equity, realized/unrealized P&L, AI regime read, live inventory, opportunity set, economy wire.
- **Market:** candidate table with EV, momentum, volume acceleration, liquidity and score.
- **Method:** the actual formulas, tax assumptions, inventory limits and exit policy.
- **History:** a paginated daily tape. Each date contains up to 30 hourly observations and can be traversed older/newer without a backend.

The styling intentionally avoids oversized cards, excessive rounding, gradients, dashboard chrome, and desktop-first layouts.

## Persistence

Git is still the database in v0.2:

```text
data/
├── portfolio.json
├── latest_snapshot.json
├── journal.jsonl
├── equity_history.jsonl
├── intelligence/
│   ├── latest.json
│   └── history.jsonl
└── days/
    ├── index.json
    └── YYYY-MM-DD.json
```

That is enough for daily navigation and a public historical tape without adding a server. If the dataset gets large or arbitrary queries become desirable, Caddy + SQLite is the natural next step.

## GitHub configuration

Secret:

```text
OPENROUTER_API_KEY
```

Useful repo variables:

```text
OPENROUTER_MODEL=openai/gpt-oss-20b
OPENROUTER_FREE_MODEL=openrouter/free
OPENROUTER_SUBAGENT_MODEL=openrouter/free
ENABLE_WEB_RESEARCH=1
ENABLE_SUBAGENT=0
ENABLE_FREE_SANITY_PASS=1
ENABLE_DDGS=1
DDGS_EVERY_HOURS=6
OSRS_WIKI_USER_AGENT=Runescape_PaperTrader/0.2 - your contact
```

Run locally:

```bash
python3 -m pip install -r requirements.txt
python3 scripts/run.py
python3 scripts/build_site.py
python3 -m http.server -d public 8000
```

## Caveats

This is an experiment, not a live execution simulator. Wiki prices are observations, not guaranteed fills. Community narratives can be manipulated. The useful question is not whether the bot can produce plausible stories; it is whether its deterministic signals and timestamped qualitative calls predict subsequent market outcomes often enough to justify their complexity.
