# RuneScape PaperTrader

> What if a tiny bot had **10 million fake GP**, watched the OSRS Grand Exchange every hour, read Jagex news and community rumors, and kept receipts on whether its ideas worked?

A public OSRS paper-trading experiment: **real market data, fake money, deterministic trading, cheap AI research.**

## The 20-second version

```text
OSRS Wiki prices ──→ deterministic trader ──→ fake portfolio
                         │
                         └──→ OpenRouter analyst
                               ├─ selective web search
                               ├─ dev/news context
                               └─ community/rumor context
                                      │
                                      ▼
                            mobile GitHub Pages report
```

Python owns every number. The LLM owns interpretation and prose. In v0.1 the AI **cannot execute, size, price, or veto trades**.

## What happens every hour

1. Pull `/latest`, `/1h`, and `/mapping` from the OSRS Wiki real-time prices API.
2. Mark and mechanically exit existing paper positions.
3. Rank fresh candidates using post-tax edge, liquidity, freshness, and spread sanity.
4. Send the already-computed state to a cheap OpenRouter model.
5. Let the analyst selectively use OpenRouter server-side web research for meaningful context.
6. Open new paper positions deterministically.
7. Persist the portfolio, trade journal, equity history, and intelligence history.
8. Build and deploy a tiny mobile-first dashboard with GitHub Pages.

## Strategy defaults

| Rule | Default |
|---|---:|
| Starting bankroll | 10,000,000 gp |
| Max positions | 8 |
| Max new position | 14% of cash |
| Starting-bankroll reserve | 10% |
| Min hourly volume | 250 |
| Max quote age | 30 min |
| Min post-tax edge | 60 gp/item |
| Min post-tax ROI | 0.40% |
| Max raw spread | 18% |
| Take profit | +1.20% |
| Stop loss | -3.50% |
| Forced exit | 18h |

The model assumes the current **2% GE seller tax, capped at 5m GP per item**, plus a small configurable slippage haircut.

## AI intelligence

The hourly analyst gets current positions and the best deterministic candidates. It may research external context and labels findings as:

`OFFICIAL` · `CONFIRMED_COMMUNITY` · `COMMUNITY` · `RUMOR` · `MODEL_INFERENCE`

Useful targets include Jagex updates/dev notes, Wiki changes, Reddit/community chatter, rumors, and plausible catalysts for unusual moves. A boring hour is allowed to remain boring.

OpenRouter server tools are beta, so research failure is deliberately non-fatal: deterministic paper trading continues.

### GitHub secrets / variables

Required for AI:

```text
OPENROUTER_API_KEY
```

Optional repository variables:

```text
OPENROUTER_MODEL=openai/gpt-oss-20b
OPENROUTER_SUBAGENT_MODEL=openai/gpt-oss-20b
ENABLE_WEB_RESEARCH=1
ENABLE_SUBAGENT=0
OSRS_WIKI_USER_AGENT=Runescape_PaperTrader - your contact
```

Subagents are off by default in v0.1 so the first version stays cheap and predictable.

## Run locally

```bash
python3 scripts/run.py
python3 scripts/build_site.py
python3 -m http.server -d public 8000
```

Reset the fake bankroll:

```bash
python3 scripts/run.py --reset
```

No third-party Python packages are required.

## Persistent data

GitHub itself is the database for v0.1:

```text
data/
├── portfolio.json
├── latest_snapshot.json
├── journal.jsonl
├── equity_history.jsonl
└── intelligence/
    ├── latest.json
    └── history.jsonl
```

This means GitHub Pages can remain completely static. If the experiment later needs arbitrary queries, private controls, a large history, or multiple strategies, moving the same frontend behind Caddy + SQLite is straightforward.

## Important caveats

This is a toy research project, not a live trading system. Wiki high/low observations are not guaranteed fills. Community chatter can be wrong or manipulated. The goal is to collect enough timestamped evidence to measure whether qualitative AI research adds anything beyond a deterministic strategy.
