# v0.2 research policy

Research is layered. Deterministic sources run independently of the language model: official Jagex RSS is checked every run; a best-effort DDGS web scout runs periodically (six-hour cadence by default). OpenRouter then receives those findings plus computed market state and may selectively use server-side web search/fetch.

Evidence classes: `OFFICIAL`, `CONFIRMED_COMMUNITY`, `COMMUNITY`, `RUMOR`, `MODEL_INFERENCE`.

The paid/cheap primary model writes the substantive qualitative read. `openrouter/free` may run a non-critical sanity pass; failure or disagreement never blocks trading. Free routing is intentionally not used for arithmetic or portfolio mutation.
