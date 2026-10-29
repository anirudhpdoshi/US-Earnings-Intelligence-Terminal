# US Earnings Intelligence Terminal

Institutional-grade earnings intelligence for the US Top 100: what the Street expected, what the company delivered, what management is signalling, and how much real cash the business generates — with a dedicated AI-economics view.

**Open `index.html`** — the terminal (dark, Bloomberg-style): Earnings Command Center, Earnings Calendar, manual Earnings Watchlist with automatic stop-tracking, US Top 100 universe, Free Cash Flow Monitor, AI Impact Monitor, company research cards, Completed Archive, and Data Sources & System Status.

## Data integrity
- All figures in the terminal come from verified files in `data/` — SEC EDGAR primary sources (releases, 10-Qs) cross-checked release ↔ filing ↔ XBRL.
- Consensus shown for META/TSLA is a labelled pre-release groundwork snapshot (frozen Oct 19–20, 2026), **not** a licensed consensus feed. No licensed consensus or transcript feed is connected yet — those fields are marked NOT AVAILABLE rather than filled.
- Earnings dates are labelled CONFIRMED / ESTIMATED / UNKNOWN. Estimated dates must be re-verified against the company's own scheduling release before use.
- META/TSLA analyses are **Preliminary — Awaiting Call** (transcripts not retrieved), so they have not been auto-stopped/archived as complete.

## Contents
- `index.html` — the terminal (single file, watchlist persists in browser storage)
- `data/` — Top-100 universe, earnings calendar, verified META/TSLA v3 card data
- `docs/` — platform blueprint, watchlist spec + registry schema, consensus/transcript provider research

## Automated price data (Twelve Data via GitHub Actions)

A scheduled workflow (`.github/workflows/twelvedata-refresh.yml`, weekdays
~08:05 / 12:35 / 16:25 ET, plus manual "Run workflow") runs
`scripts/td_fetch.py`, which uses the repository secret **TWELVE_DATA**
(never stored in any file) to refresh:

- `data/prices.json` — batched quotes for the Top-100 universe
- `data/reactions.json` — first-full-session post-earnings reaction for
  tickers listed in `data/reporters.json`
- `data/td_earnings.json` — earnings-date cross-check
- `data/td_usage.json` — daily API usage snapshot

Budget discipline: the script checks `/api_usage` first and stops for the
day at 560 credits; a normal day uses ~75 calls (hard cap: under 600/day).
The terminal page reads `prices.json` / `reactions.json` at load and fails
soft to its card-verified data when the files are absent.
Committing refreshed data requires Settings → Actions → General →
Workflow permissions = "Read and write permissions".
