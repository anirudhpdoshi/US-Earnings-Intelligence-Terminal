# Data-Source Integration Spec v1 — US Earnings Intelligence Terminal

Status as of Oct 29, 2026. Built and live: category 1 (EDGAR) and the Alpha Vantage spot-check leg of category 2. Evaluation-required (no purchase made): Polygon, FMP, EODHD, Zacks, Finnhub. Category 5 in progress.

## 1. Primary regulatory & financial data — SEC EDGAR · LIVE

Implementation: `~/workspace/earnings-data-layer/edgar_layer.py`
- **CIK map**: built from SEC `company_tickers.json` → **100/100 universe tickers mapped** (`cik_map.json`). No hand-typed CIKs.
- **Submissions API** `data.sec.gov/submissions/CIK##########.json`: per-ticker filing history; release detection = new 8-K with Item 2.02. First live poll (Oct 29, 2026, ~09:05 ET) detected same-morning earnings 8-Ks for **LLY, MA, MRK, BMY, CAT** (all Item 2.02, filed Oct 29) and correctly none yet for the AMC names. Side result: CAT's calendar date was ESTIMATED — the filing itself confirms it.
- **Company Facts API** `data.sec.gov/api/xbrl/companyfacts/CIK##########.json`: standardized XBRL; single quarters derived by differencing YTD cumulatives; validated — Q3 2026 and TTM reconcile to release figures for META/TSLA.
- **EDGAR current-filings feed** (`browse-edgar?action=getcurrent`): designated as the global tripwire for the 15-minute polling loop in the backend build (per-ticker submissions polls then confirm).
- Operating rules: declared User-Agent with contact email (anonymous bots get 403), ≤8 req/s, gzip handling, fail-soft per ticker, never overwrite good data with a failure, dedupe by accession number.

## 2. Market pricing — Alpha Vantage LIVE (spot checks) · Polygon EVALUATE

- Alpha Vantage (existing connector, free tier 25 req/day): `GLOBAL_QUOTE` verified Oct 29, 2026; `TIME_SERIES_DAILY` verified — used to compute verified post-earnings reactions now shown on the cards: **META −6.98%** (Oct 22 close vs Oct 21; cross-checked vs the selloff register) and **TSLA −3.08%** (cross-checked vs two independent market reports). Role stays limited: daily closes and reaction math, budgeted calls. Not a streaming or pre/post-market feed.
- Polygon.io: evaluation candidate for real-time/pre/post-market ticks. Gate before purchase: (a) confirm after-hours print coverage for the reaction window (16:00–20:00 ET), (b) confirm redistribution/display terms for a hosted page, (c) trial against 5 known earnings reactions vs exchange closes.

## 3. Analyst consensus & estimates — EVALUATION REQUIRED (no live feed)

- **FMP**: Analyst Estimates, Earnings Surprises, Historical Consensus endpoints; transcripts included (see §4). Prior research: Ultimate $99/mo billed annually (vendor-published, conflicting figures seen across crawls — confirm in writing), display licence extra.
- **EODHD**: Earnings Trends = consensus as of 7/30/60/90 days ago (point-in-time-ish, Grade B), €59.99 Fundamentals / €99.99 All-In-One.
- **Zacks via Nasdaq Data Link**: industry-standard consensus (Grade A with direct Zacks); sales/portal terms to confirm, including the as-of timestamp semantics in writing.
- **Hard gate for all three**: point-in-time integrity test on 10 tickers with known past surprises (from the provider research) — the vendor must reproduce the pre-release consensus, not the revised one. No consensus is displayed until a provider passes; until then the terminal shows the labelled frozen snapshot only.
- Regardless of provider: start our own daily consensus freeze store now (once any feed exists) so future quarters are provable.

## 4. Earnings transcripts — EVALUATION REQUIRED

- FMP `/api/v3/earning_call_transcript/{ticker}` (bundled with §3 FMP decision).
- Finnhub (user brief: "Discounting API, formerly Finnhub") earnings-call transcripts with speaker attribution — evaluate attribution quality and Q&A completeness on META/TSLA Q3 2026 calls vs the known record.
- Alternatives already researched: Quartr, Aiera, FactSet Transcripts.
- Gate: a transcript source must deliver full Q&A, not prepared remarks only; until one passes, cards stay "Preliminary — Awaiting Call" and never auto-complete.

## 5. Decentralized IR sites — REGISTRY IN PROGRESS

- Registry: `~/workspace/earnings-data-layer/ir_registry.csv` — one row per universe company: ticker, CIK, IR URL, URL status (VERIFIED = fetched 200 on Oct 29, 2026 / UNVERIFIED = not yet checked), host pattern (Q4 / Intrado / bespoke / unknown), feed status.
- Method: verify URLs by fetching; never guess-and-publish. Q4/Intrado-hosted sites often expose JSON/RSS endpoints — discover per site during the backend build, record in the registry, do not assume.
- Role: press-release/deck/webcast detection as a cross-check against EDGAR 8-K detection (two-source rule), not as the primary trigger.

## Refresh architecture (backend step, designed, not yet scheduled)

EDGAR current-filings tripwire every 15 min → submissions confirm per ticker → release detected → card pipeline (release + 10-Q + XBRL) → consensus snapshot join (when licensed) → transcript join (when licensed) → gate check → archive/auto-stop. Every datapoint carries source, publication timestamp, retrieval timestamp, and status (Current / Awaiting / Stale / Failed / Manually Verified). No cron is live for this platform yet — scheduling starts only on the user's go.
