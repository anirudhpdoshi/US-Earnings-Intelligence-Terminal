# US Top 100 Earnings Intelligence Platform — Blueprint v1
Date: Oct 29, 2026 · Status: Prepared for user decision — no scheduled runs started
Supersedes/extends: Earnings Intelligence Card Engine Spec v2 (`~/workspace/earnings-card/ENGINE_SPEC.md`, Oct 4, 2026)

## 1. What changes vs. the existing engine

The existing engine already does the hard part correctly: standardized top, sector-adaptive
middle (KPI registry as data, not code), analytical bottom, 5-level guidance hierarchy
(🟢 Management / 🔵 Company target / 🟡 Street / 🟣 Derived-labelled / ⚪ Not provided),
primary sources first, two-source cross-check, never fabricate.

This blueprint keeps that spine and adds, from the new master prompt:

| New element | Decision |
|---|---|
| **Three verdicts, not one** | ADOPT — replaces the single beat/miss label. Every card header shows separately: **Earnings Quality** / **Forward Outlook** / **Cash Quality**. A beat + guidance cut + cash burn must read as exactly that. |
| **FCF as anchor, not a row** | ADOPT — FCF moves to the top financial block: quarterly FCF, TTM FCF, FCF margin, capex, FCF/share, FCF yield, FCF conversion (FCF ÷ net income), SBC, and a cash-allocation waterfall (Beg cash + OCF − Capex − Acq − Div − Buybacks − Debt repaid + Debt issued = End cash, reconciled, no double-count). Banks/insurers exempt from mechanical industrial FCF — use OCF + capital/liquidity instead, per spec §9E. |
| **AI Economics Monitor (not news feed)** | ADOPT — separate scorecard per company, never collapsed to one score: Monetization Proven/Emerging/Unclear · Productivity Quantified/Partial/Evidence-unproven · Investment intensity Low/Mod/High (with metric) · Competitive position Strengthening/Stable/Weakening/Unclear · FCF impact Positive/Negative/Mixed/Not quantifiable · Evidence quality High/Med/Low. Default when undisclosed: “AI revenue not separately disclosed” — ROI then stated as *not calculable*, never estimated. |
| **Promise-vs-delivered tracker** | ADOPT — rolling 4-quarter ledger per company: guidance, capex plan, AI monetization promise, product target → outcome. This is the management-accountability layer. |
| **Top-100 universe + screener** | ADOPT for V2 — landing view ranks strongest/weakest on surprise, FCF momentum, guidance revision, AI economics (traction and burden as *separate* scores). Fundamental Momentum Score formula published with inputs/date; not a return forecast. |
| **Product / market-share modules** | DEFER to V3 — these need licensed / lagged datasets we do not have (see §3). Ship with ⚪ labels until a real source is verified. |

Standing user rules that override anything in the master prompt where they conflict:
two-source cross-check before anything goes out; no vendor/wire names on any visual output
(footer = “Verified <date>” only); data-vintage note on every send; fail-soft per module —
a missing feed degrades that module to ⚪ / 🔵 LATEST VERIFIED, never kills the card;
no buy/sell call from an earnings surprise alone.

## 2. Company card — final section order (v3)

1. Header: identity, period, release timestamp, price reaction (timestamped)
2. **Three verdicts** + 3-line verdict (what mattered / what market may be mispricing / what to monitor)
3. Street vs Actual table: Prev Year | Prev Qtr | Consensus* | Actual | $ surprise | % surprise | YoY | Verdict — revenue, GAAP EPS, adj. EPS, gross/operating/net margin, OCF, capex, FCF, cash, net debt, SBC, + 3–7 sector KPIs
4. **FCF dashboard + allocation waterfall + FCF quality flags** (earnings ↑ / FCF ↓, conversion weakening, WC-driven FCF, buybacks merely offsetting SBC dilution)
5. Guidance & Expectations (existing v2 backbone, unchanged): Prior → Current → Street, Qtr / FY divider, midpoint vs consensus, Raised/Maintained/Lowered/Withdrawn/Not provided
6. Segments, geography (reported groupings only, constant-currency split where disclosed), market share only with sourced methodology
7. **AI Impact scorecard** (as above) + AI capex vs OCF/FCF, funding source, incremental AI capex vs incremental AI revenue where both are disclosed
8. Management Intelligence: signal map (full call, incl. Q&A + avoided topics labelled as judgment, not concealment), Words-vs-Numbers check, 4-quarter theme track
9. Product launches / sector catalysts (confirmed vs announced vs rumour — separated)
10. Historical trend (≥8 quarters where available), post-earnings reaction (1d/5d, vs sector & S&P 500, implied-vs-actual move only if sourced)
11. Final conclusion: the 12-point structured close from the master prompt §17 + bull/base/bear + thesis-changing evidence + valuation context (fundamental quality ≠ stock attractiveness)

*Consensus column populates only from a pre-release snapshot — see §3 gap.

## 3. Data-source audit — checked Oct 29, 2026 (this is the gating item)

| Need | What we actually have | Verdict |
|---|---|---|
| Earnings releases, 10-K/10-Q/8-K, cash-flow statements, segment & geography revenue | **SEC EDGAR — verified working** (submissions JSON; UA-with-contact header required). Primary, free, complete for FCF/OCF/capex/SBC/balance sheet. | 🟢 V1-ready |
| Company guidance in releases / presentations | EDGAR 8-K exhibits + IR releases — manual extraction per name | 🟢 V1-ready (labour-bound) |
| Share price / market cap / reaction | Alpha Vantage connector exists but **free plan = 25 req/day, 5/min** — unusable for 100 names intraday; usable for spot checks only | 🟡 Partial |
| News / wire context | Finlight connector — articles only, no fundamentals | 🟡 Context only |
| Macro context | FRED connector | 🟢 Context only |
| **Pre-release consensus (rev/EPS/OCF) + historical snapshots** | **No licensed consensus feed connected.** No provider in the connector catalog supplies it. | 🔴 **GAP — consensus column stays ⚪ NOT AVAILABLE until a feed is chosen/licensed. Never backfilled post-release, never estimated.** |
| **Full earnings-call transcripts** | **No transcript feed connected.** Some calls via company webcast / IR; no systematic source. | 🔴 **GAP — Management Intelligence runs only where a transcript is verifiably obtained; otherwise ⚪** |
| Market share, prescriptions, shipments, cloud spend etc. | No sector databases connected | 🔴 V3 only |
| Options implied move | No options feed for equities in this stack | 🔴 ⚪ until sourced |

**Implication:** V1 is buildable *now* on primary sources alone — calendar, actuals,
FCF monitor, guidance-vs-prior-guidance, AI scorecard from disclosed capex/R&D/segment
commentary. The two gaps (consensus, transcripts) are purchasing decisions, not build
decisions. Presenting either without a real feed would violate the platform's own rule.

## 4. Universe methodology (Top 100)

- Rank quarterly by market cap + liquidity + FCF scale + strategic/AI-chain importance;
  operating companies only (no ETFs/funds); dual-class counted once; foreign-incorporated
  US-listed names flagged as such, not called US-domiciled.
- Retain exited members in history (no survivorship bias). Fiscal quarters never assumed
  to equal calendar quarters — calendar stores each company's own fiscal label.
- Seed coverage already proven in the existing renderer: JPM, BAC, C, GS, MS, WFC, MU,
  AAPL, NFLX (+ TSLA/META groundwork file). V1 expands from there, it does not restart.

## 5. Build phases

**V1 — Core decision system (buildable today, primary sources only)**
Earnings calendar (confirmed vs estimated dates, BMO/AMC) · v3 company card (§2) ·
FCF Monitor (cross-universe FCF margin / conversion / yield where price available) ·
AI Impact Monitor (scorecards aggregated; flag “spend ↑, returns undisclosed” cohort) ·
Promise-vs-delivered ledger started from this earnings season forward.

**V2 — Expectations layer (requires consensus feed decision)**
Pre-release consensus snapshots (frozen at release), surprise engine, expectation-trend
and estimate-revision modules, screener + Fundamental Momentum Score, market-reaction
tracking at scale.

**V3 — Specialist layer**
Sector databases (pharma pipeline/LOE, semis share, retail comps), product-launch
tracker with adoption data, market-share history.

## 6. Refresh & integrity

Event-driven: release → capture + FCF/guidance update; filing → reconcile prelim vs
10-Q/10-K and log revisions in audit trail; call → commentary within 30–90 min *only
where a transcript source exists*. Every datapoint stored with ticker, fiscal period,
definition, value/units, source + URL, publication ts, retrieval ts, class
(actual/consensus/guidance/estimate/calculated), confidence. Raw ≠ calculated ≠
interpretation — stored separately. Stale data shows its timestamp + warning, never
presented as current.

## 7. Open decisions for the user

1. Start V1 now on primary sources (consensus/transcript columns honestly ⚪), or
   hold the whole build until a consensus + transcript feed is selected?
2. If V1: start with the current earnings wave (the mega-cap AI names reporting now)
   as the live proving set, expanding to 100 — or build the full 100-name calendar
   and universe file first, cards second?
3. Consensus/transcript providers are paid/licensed — do you want options + pricing
   researched (e.g. consensus/transcript vendors) before deciding #1?

## 8. Add-on (Oct 29, 2026): Manual Earnings Watchlist with Auto-Stop

Full spec: `files/earnings-watchlist-spec-v1.md` · Schema: `files/watchlist-registry-schema.json` · Live registry (starts empty): `hidden_files/watchlist.json`

Summary: a temporary, manual earnings-event queue, independent of the Top 100 universe.
User adds tickers (single/bulk, validated, de-duplicated by ticker+fiscal period) →
ADDED → PRE-EARNINGS MONITORING → EARNINGS RELEASED → ANALYSIS IN PROGRESS →
ANALYSIS COMPLETE → AUTO-STOPPED. Completion requires the full 9-point gate (release,
consensus-or-disclosed-gap, FCF/capex, guidance, commentary/call, AI, segments, final
card, gaps listed) — a published release alone never completes it; missing items sit in
Awaiting Information / Preliminary — Awaiting Call. On completion: removed from active
views and polling, all routine alerts suppressed, card + sources + consensus snapshot
archived and searchable, no auto-reactivation for next quarter or unrelated news
(user re-add or explicit per-ticker recurring opt-in only). Four views: Upcoming /
Reporting Now / Awaiting Information / Completed Archive. Alerts limited to the
six-event whitelist, de-duplicated and idempotent.

## 9. Provider research results (Oct 29, 2026 — Task B complete)
Full report: `files/consensus-transcript-providers-v1.md` (no provider trialled yet)

- True point-in-time pre-release consensus (Grade A): LSEG I/B/E/S and Zacks direct
  (both sales-only pricing); FactSet A- pending a written as-of confirmation.
- Workable cheap anchors (Grade B): EODHD Earnings Trends (consensus as of 7/30/60/90d
  ago), Benzinga via Massive (surprise history to 2010), Finnhub surprise pairing.
- Current-only (Grade C): FMP, Alpha Vantage — valid only if WE freeze daily going
  forward; past quarters' pre-release consensus is unrecoverable from them.
- Practical shortlist: Hobbyist ~$160-200/mo = FMP Ultimate ($99/mo, transcripts;
  display licence extra) + EODHD (€99.99 All-In-One) + start our own daily freeze store
  now. Professional = Zacks direct or Intrinio-Zacks (pending point-in-time confirmation
  in writing) + Quartr/Aiera transcripts. Institutional = LSEG or FactSet.
- Next step before any purchase: 10-ticker validation test specified in the report.

## 10. Universe + calendar results (Oct 29, 2026 — Task A complete)
Files: `files/top100-universe-v1.csv` (exactly 100, no duplicates, market_cap =
'to verify quarterly' for all — none invented) · `files/earnings-calendar-next-v1.md`
- Sector mix: Tech 29, Healthcare 17, Financials 16, Comm Services 9, Industrials 9,
  Cons Disc 8, Staples 7, Energy 4, Materials 1. 9 foreign-incorporated US-listed
  names flagged (TSM, ASML, CB, ETN, ACN, LIN, SHOP, ARM, SLB).
- Calendar: CONFIRMED 25 / ESTIMATED 19 / UNKNOWN 56. Disagreements flagged in-file,
  not silently resolved (NVDA 17 vs 18 Nov, CSCO 12 vs 18 Nov, ORCL 9 vs 14 Dec;
  CAT/KLAC/META → UNKNOWN). ESTIMATED dates must be re-verified against the company's
  own scheduling release before use in any alert or card.

## 11. V1 prototype results (Oct 29, 2026 — Task C complete)
META + TSLA Q3 2026 v3 cards rendered (files/prototype-v3-{meta,tsla}-q3-2026.{json,png}),
all figures verified release ↔ 10-Q ↔ EDGAR XBRL. Three verdicts, FCF anchor and AI
scorecard render via the existing card_eic primitives — no engine rework needed.
- META: rev $64.601B +26%; GAAP EPS $3.83 / ex-$9.89B-charge EPS $7.40; standard FCF
  -$1,156M vs company-defined -$2,120M (difference = $964M finance-lease principal —
  both stated, never mixed; this RESOLVES the earlier -$2.12B/-$1.16B open discrepancy).
  Q4 guide $73-76B; FY capex narrowed/raised $135-145B; AI revenue not separately
  disclosed → ROI not calculable. Verdicts: Quality Moderate (High ex-charge) /
  Outlook Positive / Cash Weak in quarter, Mixed TTM.
- TSLA: rev $28.046B -0.2% YoY; GAAP EPS $0.22 / non-GAAP $0.48 (adjustment is mainly
  recurring SBC — stated, not dressed as one-time); FCF +$1,531M (company = standard
  definition), TTM FCF $3,303M vs $6,834M a year ago; guidance NOT PROVIDED (recorded
  as such); storage 13.7 GWh miss. Verdicts: Quality Low-Moderate / Outlook
  Neutral-Unclear / Cash Strong in quarter, deteriorating TTM.
- Gaps on both cards, explicit: consensus = frozen Oct 19-20 groundwork snapshot only
  (labelled not-a-licensed-feed, no backfill); transcripts NOT AVAILABLE (management
  intelligence is release/deck-only, Q&A not inferred); no price reaction included.

## 12. Status — Oct 29, 2026
All four tracks complete: blueprint + V1 prototypes + universe/calendar + provider
research + watchlist module. Open decisions: (1) provider tier / validation test,
(2) first watchlist tickers to add, (3) expand prototypes to the next reporting wave
or pause at proof-of-concept. No scheduled runs or alerts are live.
