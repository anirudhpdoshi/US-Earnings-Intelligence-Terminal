# Manual Earnings Watchlist — with Automatic Stop-Tracking
Module spec v1 · Oct 29, 2026 · Add-on to the US Top 100 Earnings Intelligence Platform
Independence rule: this queue is **separate from the permanent Top 100 universe**.
Adding a ticker here never adds it to the Top 100, to any scheduled sweep, or to any
other tracking list. Removing/auto-stopping here never touches the Top 100 record.

## 1. Entry — manual only
- User adds one ticker, or a bulk list. **Never auto-populated** — not from the Top 100,
  not from news, not from holdings. No ticker enters without an explicit user add.
- On add: validate ticker → company name, exchange, sector. Unvalidatable = flagged
  `VALIDATION FAILED`, not guessed. Then auto-retrieve (where a verified source exists):
  company profile, next earnings date + BMO/AMC + CONFIRMED/ESTIMATED status, fiscal
  period, previous-quarter results, latest financials. Consensus / historical context
  only from a connected feed — otherwise ⚪ NOT AVAILABLE (see provider gap, Blueprint §3).
- Duplicate guard: unique key = `ticker + fiscal_period`. A second add for the same
  event returns the existing entry, it does not create a duplicate or restart analysis.
- Entry controls: remove, pause, resume, priority (High / Normal / Low). Paused entries
  do not poll and do not alert, but keep their state.

## 2. Lifecycle — state machine (only these transitions)
```
ADDED → PRE-EARNINGS MONITORING → EARNINGS RELEASED → ANALYSIS IN PROGRESS
      → ANALYSIS COMPLETE → AUTO-STOPPED
Side states: PAUSED (from any active state, resume returns to prior state)
             AWAITING INFORMATION (from RELEASED / IN PROGRESS, see §4)
             PRELIMINARY — AWAITING CALL (a sub-status of IN PROGRESS, never COMPLETE)
```
- **Pre-earnings:** track date/time changes, consensus revisions (if feed exists),
  guidance changes, material product/regulatory/AI developments, and prior-quarter
  commitments vs delivery. Material changes only — unchanged data is never re-alerted.
  Priority/escalation rises as a CONFIRMED date approaches; no claim of real-time
  monitoring — every view shows `last_successful_refresh` and a stale warning on failure.
- **Release detection:** on the official release — capture timestamp, release + statements
  (EDGAR/IR primary), the *pre-release* consensus snapshot (frozen, eligible cutoff only),
  compute surprises, FCF/capex/working capital/conversion, guidance, segments/geography.
  Release published ≠ analysis complete.
- **Corrections:** amended release / corrected filing on a completed event creates a
  clearly labelled **“Correction update”** on the archived card. It does **not** silently
  reactivate monitoring. Postponed/cancelled events stay in Upcoming with the new date
  labelled, or are closed as `EVENT CANCELLED` if the company confirms cancellation.

## 3. Completion gate — ALL must be true to mark ANALYSIS COMPLETE
1. Official earnings release retrieved (primary source filed in the record)
2. Revenue + EPS compared with eligible pre-release consensus — **or** missing
   consensus explicitly disclosed on the card
3. Cash flow + capex analysed from reported data (FCF = OCF − capex; company-defined
   FCF shown separately if different)
4. Guidance evaluated (raised/maintained/lowered/withdrawn/not provided)
5. Material management commentary reviewed, including the call **when a transcript
   is verifiably available**
6. AI impact updated, unsupported conclusions labelled as such
7. Key segment + geographic results reviewed where disclosed
8. Final v3 earnings card + three verdicts generated
9. All material data gaps listed on the card

Missing call/filing/consensus → status is `AWAITING INFORMATION` or
`PRELIMINARY — AWAITING CALL`. **Never falsely complete.**

## 4. Auto-stop — what happens at completion
Status → `AUTO-STOPPED — EARNINGS COMPLETE`. Removed from Upcoming/Reporting views and
from all routine polling/alerts for that event. Archived intact: final card, sources,
consensus snapshot, calculations, commentary, verdicts — searchable in Completed Archive.
**No auto-reactivation** — not for unrelated news, not for the next quarter. Reactivation
only by: (a) user manually re-adding the ticker for a new fiscal event, or (b) user
explicitly enabling recurring tracking for that ticker (off by default, per-ticker).

## 5. Views (4)
| View | Contents |
|---|---|
| Upcoming | Active, awaiting earnings — Ticker \| Company \| Date \| Time \| Fiscal Period \| Consensus Status \| Tracking Status \| Next Action (+ countdown only where date+time are reliable) |
| Reporting Now | Released, analysis underway (incl. Preliminary — Awaiting Call) |
| Awaiting Information | Missing transcript / consensus / filing / other material data, itemised per ticker |
| Completed Archive | Finalised + auto-stopped, searchable, with completion timestamp + auto-stop reason |

## 6. Alerts — whitelist only, de-duplicated
Date/time change · material consensus revision · significant pre-earnings development ·
official release detected · analysis completed · analysis delayed (critical data missing).
Nothing else. Auto-stopped = all routine alerts for that event suppressed. Idempotent:
a repeated detection/refresh never re-sends an alert or re-runs a completed analysis.

## 7. Persisted record (per entry — see watchlist-registry-schema.json)
ticker, company_id (CIK where available), company name, fiscal_period, event_id,
date_added, earnings_date + confirmation_status + BMO/AMC, lifecycle_state, priority,
paused flag, last_successful_refresh, release_detected_at, analysis_completed_at,
missing_data_checklist[], consensus_snapshot_ref, final_card_ref, auto_stop_reason,
correction_updates[].

Live registry starts empty: `hidden_files/watchlist.json` — entries are created only
by user adds.
