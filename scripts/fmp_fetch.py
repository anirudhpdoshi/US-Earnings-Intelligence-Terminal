#!/usr/bin/env python3
"""FMP refresh for the US Earnings Intelligence Terminal.

Runs inside GitHub Actions. The API key comes ONLY from the environment
(FMP_KEY, mapped by the workflow from the repository secret). The key
never appears in any file, log line, or output.

What it fetches (Financial Modeling Prep, /stable API):
  - Earnings calendar for the next 14 days (one call) -> data/fmp_calendar.json
    Carries FMP's consensus estimates for upcoming events. IMPORTANT:
    these are CURRENT estimates, not frozen point-in-time pre-release
    consensus. The terminal labels them as a non-frozen snapshot with the
    retrieval timestamp; they are never backfilled after a release.
  - Earnings surprises history for tracked reporters (one call each)
    -> data/fmp_surprises.json (actual vs estimate as FMP recorded them)
  - Earnings call transcripts for tracked reporters (one call each,
    only when symbol+quarter+year are listed in data/reporters.json)
    -> data/transcripts/<TICKER>-<period>.json (raw transcript payload;
    analysis happens in the card pipeline, not here)

Fail-soft by module: a failed module leaves its previous file untouched.
Auth failure on the first call exits non-zero so the run shows red.
Call budget: calendar 1 + surprises <=20 + transcripts <=20 per run.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://financialmodelingprep.com/stable"
KEY = os.environ.get("FMP_KEY") or os.environ.get("FMP_API_KEY") or ""
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
calls = 0


def scrub(text):
    """Defense-in-depth: never let the API key reach a log line, even if a
    transport error echoes the request URL back. (GitHub also masks secret
    values in Actions logs; this protects every other log sink.)"""
    return text.replace(KEY, "***") if KEY else text


def get(path, params):
    global calls
    params = dict(params)
    params["apikey"] = KEY
    url = API + path + "?" + urllib.parse.urlencode(params)
    calls += 1
    req = urllib.request.Request(url, headers={"User-Agent": "earnings-terminal-actions/1.0"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(rel, obj):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)
    print(f"wrote {rel}")


def _loadj(rel, default):
    try:
        with open(os.path.join(ROOT, "data", rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

INDICES = [("YMUSD", "YM", "DOW FUTURES \u00b7 DEC", False), ("NQUSD", "NQ", "NASDAQ-100 FUTURES \u00b7 DEC", False), ("ESUSD", "ES", "S&P 500 FUTURES \u00b7 DEC", False), ("RTYUSD", "RTY", "RUSSELL 2000 FUTURES \u00b7 DEC", False), ("VXUSD", "VX", "VIX FUTURES \u00b7 FRONT MONTH", False)]

def fetch_indices():
    rows = []
    for sym, short, name, is_vix in INDICES:
        try:
            d = get("/quote", {"symbol": sym})
        except Exception as e:
            print("indices: quote failed for", sym, type(e).__name__)
            continue
        row = (d or [None])[0] if isinstance(d, list) else None
        if row and row.get("price") is not None:
            rows.append({"sym": short, "name": name, "price": row.get("price"), "chg": row.get("changePercentage"), "chg_pts": row.get("change"), **({"vix": True} if is_vix else {})})
    if rows:
        write_json("data/indices.json", {"generated_at": now_iso(), "source": "index quotes via market data feed", "asof": "live futures quote · latest feed run (futures trade nearly 24h — includes extended hours)", "rows": rows})
        print("indices:", len(rows), "rows")

def main():
    if not KEY:
        print("ERROR: FMP_KEY env var is empty - repository secret missing or not mapped.", file=sys.stderr)
        return 2

    fetch_indices()
    fetch_market()
    fetch_fundamentals()
    fetch_poll()

    today = datetime.now(timezone.utc).date()

    # 1) Earnings calendar, next 14 days -----------------------------------
    try:
        cal = get("/earnings-calendar", {"from": today.isoformat(),
                                         "to": (today + timedelta(days=14)).isoformat()})
    except Exception as e:
        print(f"ERROR: earnings-calendar failed: {type(e).__name__}: {scrub(str(e))}", file=sys.stderr)
        return 2
    if isinstance(cal, dict) and cal.get("Error Message"):
        print(f"ERROR: FMP rejected the key: {scrub(str(cal['Error Message']))}", file=sys.stderr)
        return 2
    if isinstance(cal, list):
        write_json("data/fmp_calendar.json", {
            "generated_at": now_iso(),
            "note": "Estimates are FMP current values at retrieval time - NOT a frozen point-in-time consensus snapshot.",
            "events": cal})
        print(f"calendar events: {len(cal)}")

    # Tracked reporters -----------------------------------------------------
    reporters = []
    rep_path = os.path.join(ROOT, "data", "reporters.json")
    if os.path.exists(rep_path):
        with open(rep_path, encoding="utf-8") as f:
            reporters = json.load(f).get("reporters", [])
    fetch_ownership([r["ticker"] for r in reporters[:20]])

    # 2) Earnings surprises for reporters -----------------------------------
    surprises = {}
    for rep in reporters[:20]:
        tk = rep["ticker"]
        try:
            rows = get("/earnings-surprises", {"symbol": tk})
        except Exception as e:
            print(f"surprises {tk}: FAILED {type(e).__name__}: {scrub(str(e))}")
            continue
        if isinstance(rows, list) and rows:
            surprises[tk] = rows[:8]
            print(f"surprises {tk}: {len(rows)} quarters")
    if surprises:
        write_json("data/fmp_surprises.json", {"generated_at": now_iso(), "surprises": surprises})

    # 3) Transcripts for reporters with a fiscal period on file --------------
    for rep in reporters[:20]:
        tk = rep["ticker"]
        q, y = rep.get("fiscal_quarter"), rep.get("fiscal_year")
        if not q or not y:
            continue
        try:
            tr = get("/earning-call-transcript", {"symbol": tk, "quarter": q, "year": y})
        except Exception as e:
            print(f"transcript {tk}: FAILED {type(e).__name__}: {scrub(str(e))}")
            continue
        if isinstance(tr, list) and tr and tr[0].get("content"):
            write_json(f"data/transcripts/{tk}-Q{q}-{y}.json",
                       {"retrieved_at": now_iso(), "symbol": tk, "quarter": q, "year": y,
                        "date": tr[0].get("date"), "content": tr[0]["content"]})
            print(f"transcript {tk} Q{q} {y}: {len(tr[0]['content'])} chars")
        else:
            print(f"transcript {tk} Q{q} {y}: not available yet")

    print(f"done. API calls this run: {calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------- EDGAR poll
def fetch_poll():
    """Release tripwire -> data/poll.json: most recent 8-K Item 2.02 per
    universe ticker within the last 21 days (EDGAR submissions). Lets the
    terminal reflect new releases on the next feed run instead of waiting
    for a manual rebuild."""
    import urllib.request, gzip as _gz, time as _time, datetime as _dt
    ua = {"User-Agent": "Earnings Intelligence Terminal research adoshi@dgglobal.ca",
          "Accept-Encoding": "gzip"}

    def getj(url):
        req = urllib.request.Request(url, headers=ua)
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = _gz.decompress(raw)
            return json.loads(raw)

    try:
        tickers = getj("https://www.sec.gov/files/company_tickers.json")
        cikmap = {v["ticker"]: v["cik_str"] for v in tickers.values()}
    except Exception as e:
        print("poll: cik map failed:", type(e).__name__)
        return
    uni = _loadj("universe_tickers.json", {"tickers": []}).get("tickers", [])
    cutoff = (_dt.date.today() - _dt.timedelta(days=21)).isoformat()
    poll = {}
    for tk in uni:
        _cik = cikmap.get(tk) or cikmap.get(tk.replace(".", "-")) or cikmap.get(tk.replace(".", "/"))
        if not _cik:
            continue
        try:
            sub = getj(f"https://data.sec.gov/submissions/CIK{int(_cik):010d}.json")
        except Exception:
            continue
        _time.sleep(0.13)
        try:
            rec = sub["filings"]["recent"]
            for i, form in enumerate(rec["form"]):
                if form == "8-K" and "2.02" in (rec["items"][i] or "") and rec["filingDate"][i] >= cutoff:
                    poll[tk] = {"date": rec["filingDate"][i],
                                "accession": rec["accessionNumber"][i],
                                "polled_at": now_iso()}
                    break
        except Exception:
            continue
    if poll:
        write_json("data/poll.json", {"generated_at": now_iso(), "poll": poll})
        print("poll:", len(poll), "recent reporters")

# ---------------------------------------------------------------- market pack
def fetch_market():
    """Quotes for the full universe -> 52w range + market cap; $100B milestone detection vs the previous committed snapshot."""
    uni = _loadj("universe_tickers.json", {"tickers": []}).get("tickers", [])
    if not uni:
        print("market: no universe_tickers.json - skipped")
        return
    prev = _loadj("market.json", {})
    prevm = prev.get("stocks", {}) if isinstance(prev, dict) else {}
    stocks = {}
    for i in range(0, len(uni), 50):
        try:
            d = get("/quote", {"symbol": ",".join(uni[i:i + 50])})
        except Exception as e:
            print("market: quote batch failed:", type(e).__name__)
            continue
        for row in (d or []):
            sym = row.get("symbol")
            if sym:
                mc = row.get("marketCap")
                stocks[sym] = {"price": row.get("price"), "chg_pct": row.get("changePercentage"),
                               "mcap_b": round(mc / 1e9, 1) if mc else None,
                               "yhigh": row.get("yearHigh"), "ylow": row.get("yearLow")}
    if not stocks:
        return
    events = []
    for sym, s in stocks.items():
        pm = prevm.get(sym)
        if not pm or not s.get("mcap_b") or not pm.get("mcap_b"):
            continue
        old, new = pm["mcap_b"], s["mcap_b"]
        b_old, b_new = int(old // 100) * 100, int(new // 100) * 100
        if b_new != b_old:
            events.append({"ticker": sym, "kind": "cross", "level_b": max(b_old, b_new) if new > old else b_old,
                           "from_b": old, "to_b": new, "dir": "up" if new > old else "down", "at": now_iso()})
        elif abs(new - old) >= 100:
            events.append({"ticker": sym, "kind": "swing", "from_b": old, "to_b": new,
                           "dir": "up" if new > old else "down", "at": now_iso()})
    write_json("data/market.json", {"generated_at": now_iso(), "stocks": stocks})
    print("market:", len(stocks), "stocks;", len(events), "milestone events")
    if events:
        ms = _loadj("milestones.json", {"events": []})
        merged = (events + ms.get("events", []))[:40]
        write_json("data/milestones.json", {"generated_at": now_iso(), "events": merged})

def fetch_ownership(reporters):
    """Insider transactions + institutional holding trend (top holders, quarterly totals) for reporter tickers."""
    ins, own = {}, {}
    for tk in reporters:
        try:
            d = get("/insider-trading", {"symbol": tk, "limit": 12})
            rows = [{"date": r.get("transactionDate"), "name": r.get("reportingName"), "type": r.get("transactionType"),
                     "shares": r.get("securitiesTransacted"), "price": r.get("price"),
                     "value": (r.get("securitiesTransacted") or 0) * (r.get("price") or 0) or None} for r in (d or [])]
            if rows:
                ins[tk] = rows
        except Exception as e:
            print("insiders:", tk, "failed:", type(e).__name__)
        try:
            d = get("/institutional-holder", {"symbol": tk})
            by_q, holders = {}, {}
            for r in (d or []):
                q = (r.get("dateReported") or "")[:7]
                if q:
                    by_q[q] = by_q.get(q, 0) + (r.get("shares") or 0)
                holders[r.get("holder")] = {"shares": r.get("shares"), "change": r.get("change"), "date": r.get("dateReported")}
            if by_q:
                qs = sorted(by_q)[-5:]
                own[tk] = {"quarters": [{"q": q, "shares": by_q[q]} for q in qs],
                           "top": sorted([{"holder": h, **v} for h, v in holders.items() if h],
                                         key=lambda x: -(x["shares"] or 0))[:8]}
        except Exception as e:
            print("ownership:", tk, "failed:", type(e).__name__)
    if ins:
        write_json("data/insiders.json", {"generated_at": now_iso(), "by_ticker": ins})
        print("insiders:", len(ins), "tickers")
    if own:
        write_json("data/ownership.json", {"generated_at": now_iso(), "by_ticker": own})
        print("ownership:", len(own), "tickers")

# ------------------------------------------------------- fundamentals (EDGAR)
def fetch_fundamentals():
    """SEC EDGAR companyfacts -> data/debt.json + data/ratios.json.
    Debt: anchor concept chain + freshness guard, balances/cash, interest
    (stale-FY rejected), issuance/repayment, maturity schedule, investments.
    Ratios: computed from filed figures (TTM bridge), sector extras for
    Financials. Blended effective rate = reported interest expense based,
    never a bond coupon. Fail-soft per ticker."""
    import urllib.request, gzip as _gz, datetime as _dt, time as _time, csv as _csv
    ua = {"User-Agent": "Earnings Intelligence Terminal research adoshi@dgglobal.ca",
          "Accept-Encoding": "gzip"}
    forms = ("10-Q", "10-K", "10-Q/A", "10-K/A")
    FORMS = forms
    FRESH = "2025-08-01"

    def getj(url):
        req = urllib.request.Request(url, headers=ua)
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = _gz.decompress(raw)
            return json.loads(raw)

    try:
        tickers = getj("https://www.sec.gov/files/company_tickers.json")
        cikmap = {v["ticker"]: v["cik_str"] for v in tickers.values()}
    except Exception as e:
        print("fundamentals: cik map failed:", type(e).__name__)
        return
    uni = _loadj("universe_tickers.json", {"tickers": []}).get("tickers", [])
    sectors = {}
    try:
        with open(os.path.join(ROOT, "data", "top100-universe-v1.csv"), encoding="utf-8") as f:
            sectors = {r["ticker"]: r["sector"] for r in _csv.DictReader(f)}
    except Exception:
        pass
    datetime = _dt

    MAT_SUFFIX = ['InNextTwelveMonths', 'InYearTwo', 'InYearThree', 'InYearFour', 'InYearFive', 'AfterYearFive']
    MAT_KEYS = ['next12', 'y2', 'y3', 'y4', 'y5', 'after5']
    RAISE = ['ProceedsFromIssuanceOfLongTermDebt', 'ProceedsFromDebtNetOfIssuanceCosts', 'ProceedsFromIssuanceOfDebt']
    REPAY = ['RepaymentsOfLongTermDebt', 'RepaymentsOfDebt']
    INTEREST = ['InterestExpenseDebt', 'InterestExpense']
    REV = ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet', 'RevenueFromContractWithCustomerIncludingAssessedTax']

    def units(facts, concept):
        g = facts.get('facts', facts).get('us-gaap', {}).get(concept)
        out = []
        if g:
            for u, rows in g.get('units', {}).items():
                if u.startswith('USD'):
                    out.extend(rows)
        return out

    def latest(facts, concept, max_end=None, fresh_only=False):
        rows = [r for r in units(facts, concept) if r.get('form') in FORMS]
        if max_end:
            rows = [r for r in rows if r['end'] <= max_end]
        if fresh_only:
            rows = [r for r in rows if r['end'] >= FRESH]
        if not rows:
            return None
        rows.sort(key=lambda r: (r['end'], r.get('filed', '')))
        return rows[-1]

    def at_end(facts, concept, end):
        r = latest(facts, concept, max_end=end)
        return r if r and r['end'] == end else None

    def smap(facts, concept):
        by = {}
        for r in sorted([x for x in units(facts, concept) if x.get('form') in FORMS],
                        key=lambda x: x.get('filed', '')):
            by[r['end']] = r['val']
        return by

    def flow(facts, concepts, end_date, lo, hi):
        for c in concepts:
            best = None
            for r in units(facts, c):
                if r.get('form') not in FORMS or 'start' not in r:
                    continue
                if end_date and r['end'] != end_date:
                    continue
                days = (datetime.date.fromisoformat(r['end']) - datetime.date.fromisoformat(r['start'])).days
                if lo <= days <= hi and (best is None or (r['end'], days) > (best[3], best[0])):
                    best = (days, r['val'], c, r['end'])
            if best:
                return best
        return None

    def extract(facts):
        """Return (total, lt_nc, current, basis, anchor_series_map) or None."""
        # (a) components
        ltnc = latest(facts, 'LongTermDebtNoncurrent', fresh_only=True)
        if ltnc:
            end = ltnc['end']
            ltc = at_end(facts, 'LongTermDebtCurrent', end)
            stb = at_end(facts, 'ShortTermBorrowings', end)
            dc = at_end(facts, 'DebtCurrent', end)
            lt_c = ltc['val'] if ltc else 0
            st = stb['val'] if stb else 0
            total = ltnc['val'] + lt_c + st
            current = dc['val'] if dc else (lt_c + st)
            s = {}
            m1, m2, m3 = smap(facts, 'LongTermDebtNoncurrent'), smap(facts, 'LongTermDebtCurrent'), smap(facts, 'ShortTermBorrowings')
            for e in m1:
                s[e] = m1[e] + m2.get(e, 0) + m3.get(e, 0)
            return total, ltnc['val'], current, 'LT noncurrent + current portion + ST borrowings', s, end, ltnc.get('filed')
        # (b) carrying amount
        ca = latest(facts, 'DebtInstrumentCarryingAmount', fresh_only=True)
        if ca:
            end = ca['end']
            dc = at_end(facts, 'DebtCurrent', end)
            return ca['val'], None, dc['val'] if dc else None, 'Total debt carrying amount as reported', smap(facts, 'DebtInstrumentCarryingAmount'), end, ca.get('filed')
        # (c) incl. current maturities
        inc = latest(facts, 'LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities', fresh_only=True)
        if inc:
            end = inc['end']
            stb = at_end(facts, 'ShortTermBorrowings', end)
            st = stb['val'] if stb else 0
            s = {e: v + (smap(facts, 'ShortTermBorrowings').get(e, 0)) for e, v in smap(facts, 'LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities').items()}
            return inc['val'] + st, None, None, 'LT debt & finance leases incl. current maturities', s, end, inc.get('filed')
        # (d) parent + current
        par = latest(facts, 'LongTermDebtAndCapitalLeaseObligations', fresh_only=True)
        if par:
            end = par['end']
            cur = at_end(facts, 'LongTermDebtAndCapitalLeaseObligationsCurrent', end)
            mp, mc = smap(facts, 'LongTermDebtAndCapitalLeaseObligations'), smap(facts, 'LongTermDebtAndCapitalLeaseObligationsCurrent')
            s = {e: mp[e] + mc.get(e, 0) for e in mp}
            if cur:
                return par['val'] + cur['val'], par['val'], cur['val'], 'LT debt & finance leases incl. current portion', s, end, par.get('filed')
            # (f) parent alone
            return par['val'], par['val'], None, 'LT debt & finance leases (noncurrent as reported)', {e: v for e, v in mp.items()}, end, par.get('filed')
        # (e) plain LongTermDebt
        lt = latest(facts, 'LongTermDebt', fresh_only=True)
        if lt:
            end = lt['end']
            stb = at_end(facts, 'ShortTermBorrowings', end)
            st = stb['val'] if stb else 0
            return lt['val'] + st, None, None, 'LongTermDebt as reported', smap(facts, 'LongTermDebt'), end, lt.get('filed')
        return None

    def maturity(facts, end):
        best = None
        floor = (datetime.date.fromisoformat(end) - datetime.timedelta(days=400)).isoformat()
        for fam, label in (('LongTermDebtMaturitiesRepaymentsOfPrincipal', 'long-term debt'),
                           ('LongTermDebtAndCapitalLeaseObligationsMaturitiesRepaymentsOfPrincipal', 'debt & finance leases')):
            # candidate ends: any bucket end <= asof and >= floor; use the latest end with >=3 buckets
            ends = set()
            for suf in MAT_SUFFIX:
                for r in units(facts, fam + suf):
                    if r.get('form') in FORMS and floor <= r['end'] <= end:
                        ends.add(r['end'])
            for cand in sorted(ends, reverse=True):
                vals, n = {}, 0
                for suf, key in zip(MAT_SUFFIX, MAT_KEYS):
                    r = at_end(facts, fam + suf, cand)
                    if r:
                        vals[key] = round(r['val'] / 1e6, 1); n += 1
                if n >= 3:
                    if best is None or (n, cand) > (best[3], best[0]):
                        best = (cand, vals, label, n)
        if not best:
            return None
        return {'buckets': best[1], 'family': best[2], 'asof': best[0]}

    def dei_units(facts, concept):
        g = facts.get('facts', facts).get('dei', {}).get(concept)
        out = []
        if g:
            for u, rows in g.get('units', {}).items():
                out.extend(rows)
        return out

    def shares_out(facts):
        rows = dei_units(facts, 'EntityCommonStockSharesOutstanding')
        if not rows:
            return None
        rows.sort(key=lambda r: (r['end'], r.get('filed', '')))
        return rows[-1]['val']

    def dur_rows(facts, concepts):
        for c in concepts:
            rows = []
            for r in units(facts, c):
                if r.get('form') in FORMS and 'start' in r:
                    days = (datetime.date.fromisoformat(r['end']) - datetime.date.fromisoformat(r['start'])).days
                    rows.append((r['start'], r['end'], days, r['val']))
            if rows:
                return rows, c
        return [], None

    def _ttm_one(rows, asof):
        if not rows:
            return None
        fys = [r for r in rows if 330 <= r[2] <= 400 and r[1] <= asof]
        fy = max(fys, key=lambda r: (r[1], r[2])) if fys else None
        ytds = [r for r in rows if r[1] == asof and 60 <= r[2] <= 330]
        ytd = max(ytds, key=lambda r: r[2]) if ytds else None
        if fy and ytd and fy[1] < asof:
            pri = [r for r in rows if 60 <= r[2] <= 330 and abs((datetime.date.fromisoformat(asof) - datetime.date.fromisoformat(r[1])).days - 365) <= 45 and abs(r[2] - ytd[2]) <= 50]
            if pri:
                pr = max(pri, key=lambda r: r[1])
                return (fy[3] + ytd[3] - pr[3], 'TTM', fy[1], True)
            return (fy[3], 'FY', fy[1], False)
        if fy:
            return (fy[3], 'FY', fy[1], ytd is not None)
        return None

    def ttm(facts, concepts, asof):
        """Evaluate every concept in the chain; pick the freshest (YTD at asof wins,
        then latest FY end). Rejects concepts whose data ends long before asof."""
        best = None
        floor = (datetime.date.fromisoformat(asof) - datetime.timedelta(days=400)).isoformat()
        for c in concepts:
            rows = []
            for r in units(facts, c):
                if r.get('form') in FORMS and 'start' in r:
                    days = (datetime.date.fromisoformat(r['end']) - datetime.date.fromisoformat(r['start'])).days
                    rows.append((r['start'], r['end'], days, r['val']))
            cand = _ttm_one(rows, asof)
            if not cand:
                continue
            val, basis, fy_end, has_ytd = cand
            if not has_ytd and fy_end < floor:
                continue
            score = (1 if has_ytd else 0, fy_end)
            if best is None or score > best[0]:
                best = (score, val, basis)
        if not best:
            return None, None
        return best[1], best[2]

    def ytd_val(facts, concepts, asof):
        for c in concepts:
            rows, _ = dur_rows(facts, [c])
            cand = [r for r in rows if r[1] == asof and 60 <= r[2] <= 330]
            if cand:
                return max(cand, key=lambda r: r[2])[3]
            fys = [r for r in rows if 330 <= r[2] <= 400 and r[1] == asof]
            if fys:
                return fys[0][3]
        return None

    def ytd_growth(facts, concepts, asof):
        for c in concepts:
            rows, _ = dur_rows(facts, [c])
            ytds = [r for r in rows if r[1] == asof and 60 <= r[2] <= 330]
            if not ytds:
                continue
            ytd = max(ytds, key=lambda r: r[2])
            pri = [r for r in rows if 60 <= r[2] <= 330 and abs((datetime.date.fromisoformat(asof) - datetime.date.fromisoformat(r[1])).days - 365) <= 45 and abs(r[2] - ytd[2]) <= 50]
            if pri:
                pr = max(pri, key=lambda r: r[1])
                return (ytd[3] / pr[3] - 1) * 100 if pr[3] else None
        return None

    def inst(facts, concepts, end):
        for c in concepts:
            r = at_end(facts, c, end)
            if r:
                return r['val']
        return None

    out = {}
    ratios_out = {}
    stats = {'total_debt': 0, 'interest': 0, 'raised': 0, 'failed': 0}
    for tk in uni:
        _cik = cikmap.get(tk) or cikmap.get(tk.replace('.', '-')) or cikmap.get(tk.replace('.', '/'))
        if not _cik:
            continue
        try:
            facts = getj(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(_cik):010d}.json")
        except Exception as e:
            stats['failed'] += 1
            print(tk, 'FETCH FAIL', type(e).__name__)
            continue
        _time.sleep(0.13)
        ex = extract(facts)
        if not ex:
            out[tk] = {'status': 'no_xbrl_debt'}
            continue
        total, lt_nc, current, basis, ser_map, end, filed = ex
        cash_r = at_end(facts, 'CashAndCashEquivalentsAtCarryingValue', end)
        cash = cash_r['val'] if cash_r else None
        inte = flow(facts, INTEREST, end, 90, 330)
        inte_fy = None
        if not inte:
            cand = flow(facts, INTEREST, None, 330, 400)
            if cand and cand[3] <= end:
                inte_fy = cand
        rai = flow(facts, RAISE, end, 90, 330)
        rep = flow(facts, REPAY, end, 90, 330)
        rai_fy = flow(facts, RAISE, None, 330, 400)
        rep_fy = flow(facts, REPAY, None, 330, 400)
        # staleness guard: FY flows are only usable if their period ends within
        # ~15 months of the balance date (some filers stopped tagging interest
        # expense after FY2023 — a stale FY figure must never pose as current)
        _asof = datetime.date.fromisoformat(end)
        def _stale(f):
            return f is not None and (_asof - datetime.date.fromisoformat(f[3])).days > 460
        if _stale(inte_fy): inte_fy = None
        if _stale(rai_fy): rai_fy = None
        if _stale(rep_fy): rep_fy = None
        ser = [[e, round(v / 1e6, 1)] for e, v in sorted(ser_map.items())[-8:]]
        eff = None
        if inte and len(ser) >= 2:
            avg = (ser[0][1] + ser[-1][1]) / 2 * 1e6
            if avg > 0 and inte[0] > 0:
                eff = round((inte[1] * 365 / inte[0]) / avg * 100, 2)
        elif inte_fy:
            base = dict(ser).get(inte_fy[3])
            if base:
                eff = round(inte_fy[1] / (base * 1e6) * 100, 2)
        M = lambda v: round(v / 1e6, 1) if v is not None else None
        rec = {'asof': end, 'filed': filed, 'basis': basis,
               'total_debt_m': M(total), 'lt_noncurrent_m': M(lt_nc),
               'current_m': M(current), 'cash_m': M(cash),
               'net_debt_m': M(total - cash) if cash is not None else None,
               'interest_ytd_m': M(inte[1]) if inte else None,
               'interest_days': inte[0] if inte else None,
               'interest_fy_m': M(inte_fy[1]) if inte_fy else None,
               'interest_fy_end': inte_fy[3] if inte_fy else None,
               'eff_rate_pct': eff, 'eff_basis': 'ytd' if inte else ('fy' if inte_fy else None),
               'raised_ytd_m': M(rai[1]) if rai else None,
               'repaid_ytd_m': M(rep[1]) if rep else None,
               'raised_fy_m': M(rai_fy[1]) if rai_fy and rai_fy[3] <= end else None,
               'repaid_fy_m': M(rep_fy[1]) if rep_fy and rep_fy[3] <= end else None,
               'series': ser, 'sector': sectors.get(tk, '')}
        rec['maturity'] = maturity(facts, end)
        rec['shares_out'] = shares_out(facts)
        _Mv = lambda x: x / 1e6 if x is not None else None
        capex_y = ytd_val(facts, ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets'], end)
        ms_c = inst(facts, ['MarketableSecuritiesCurrent'], end)
        ms_nc = inst(facts, ['MarketableSecuritiesNoncurrent'], end)
        sec = ((ms_c or 0) + (ms_nc or 0)) if (ms_c is not None or ms_nc is not None) else inst(facts, ['AvailableForSaleSecuritiesDebtSecurities'], end)
        rec['invest'] = {'capex_ytd_m': M(capex_y), 'ppe_net_m': M(inst(facts, ['PropertyPlantAndEquipmentNet'], end)),
                         'securities_m': M(sec), 'equity_inv_m': M(inst(facts, ['EquityMethodInvestments'], end)),
                         'acq_ytd_m': M(ytd_val(facts, ['PaymentsToAcquireBusinessesNetOfCashAcquired'], end))}
        rev, rbasis = ttm(facts, REV, end)
        oi, _b = ttm(facts, ['OperatingIncomeLoss'], end)
        ni, _b = ttm(facts, ['NetIncomeLoss'], end)
        da, _b = ttm(facts, ['DepreciationDepletionAndAmortization', 'DepreciationAmortizationAndAccretionNet', 'Depreciation'], end)
        ocf, _b = ttm(facts, ['NetCashProvidedByUsedInOperatingActivities'], end)
        cpx, _b = ttm(facts, ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets'], end)
        gp, _b = ttm(facts, ['GrossProfit'], end)
        div, _b = ttm(facts, ['PaymentsOfDividendsCommonStock', 'PaymentsOfDividends'], end)
        bbk, _b = ttm(facts, ['PaymentsForRepurchaseOfCommonStock'], end)
        sbc, _b = ttm(facts, ['ShareBasedCompensation'], end)
        rd, _b = ttm(facts, ['ResearchAndDevelopmentExpense'], end)
        cor, _b = ttm(facts, ['CostOfRevenue', 'CostOfGoodsAndServicesSold', 'CostOfGoodsSold'], end)
        tax, _b = ttm(facts, ['IncomeTaxExpenseBenefit'], end)
        pre, _b = ttm(facts, ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments'], end)
        assets = inst(facts, ['Assets'], end); ac = inst(facts, ['AssetsCurrent'], end)
        lc = inst(facts, ['LiabilitiesCurrent'], end)
        eq = inst(facts, ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'], end)
        inv = inst(facts, ['InventoryNet'], end)
        interest_used = (inte[1] * 365 / inte[0]) if inte else (inte_fy[1] if inte_fy else None)
        ebitda = (oi + da) if (oi is not None and da is not None) else None
        fcf = (ocf - cpx) if (ocf is not None and cpx is not None) else None
        R = {}
        def put(k, v):
            if v is not None: R[k] = round(v, 2)
        if rev:
            put('gross_margin', gp / rev * 100 if gp is not None else None)
            put('operating_margin', oi / rev * 100 if oi is not None else None)
            put('net_margin', ni / rev * 100 if ni is not None else None)
            put('ebitda_margin', ebitda / rev * 100 if ebitda is not None else None)
            put('fcf_margin', fcf / rev * 100 if fcf is not None else None)
            put('capex_intensity', cpx / rev * 100 if cpx is not None else None)
            put('sbc_pct', sbc / rev * 100 if sbc is not None else None)
            put('rd_intensity', rd / rev * 100 if rd is not None else None)
        if ebitda:
            put('debt_ebitda', total / ebitda)
            put('net_debt_ebitda', (total - cash) / ebitda if cash is not None else None)
        if ebitda and interest_used: put('interest_coverage', ebitda / interest_used)
        if fcf is not None and oi: put('fcf_conversion', fcf / oi * 100)
        if ac and lc: put('current_ratio', ac / lc)
        if eq and eq > 0: put('debt_capital', total / (total + eq) * 100)
        if ni is not None and eq and eq > 0: put('roe', ni / eq * 100)
        if ni is not None and assets: put('roa', ni / assets * 100)
        if oi is not None and eq is not None and eq > 0 and cash is not None:
            trate = (tax / pre) if (tax is not None and pre) else None
            if trate is not None and 0 <= trate <= 0.6:
                put('roic', oi * (1 - trate) / (total + eq - cash) * 100)
        if fcf and fcf > 0 and (div is not None or bbk is not None):
            put('payout_pct', ((div or 0) + (bbk or 0)) / fcf * 100)
        put('rev_growth_pct', ytd_growth(facts, REV, end))
        if inv and cor: put('inventory_turns', cor / inv)
        if R.get('rev_growth_pct') is not None and R.get('fcf_margin') is not None:
            put('rule40', R['rev_growth_pct'] + R['fcf_margin'])
        if rec['sector'] == 'Financials':
            dep = inst(facts, ['Deposits'], end)
            loans = inst(facts, ['LoansAndLeasesReceivableNetOfDeferredIncome', 'LoansReceivableNet'], end)
            nii, _b = ttm(facts, ['InterestIncomeExpenseNet', 'InterestIncomeExpenseAfterProvisionForLoanLoss'], end)
            nie, _b = ttm(facts, ['NoninterestExpense'], end)
            nii2, _b = ttm(facts, ['NoninterestIncome'], end)
            if dep and loans: put('loans_deposits', loans / dep * 100)
            if eq and assets: put('equity_assets', eq / assets * 100)
            if nie is not None and nii and nii2 is not None: put('efficiency', nie / (nii + nii2) * 100)
        if R:
            ratios_out[tk] = {'asof': end, 'sector': rec['sector'], 'basis': rbasis or 'FY',
                              'inputs_m': {'revenue': _Mv(rev), 'operating_income': _Mv(oi), 'net_income': _Mv(ni),
                                           'ebitda': _Mv(ebitda), 'fcf': _Mv(fcf), 'interest_used': _Mv(interest_used),
                                           'ocf': _Mv(ocf), 'capex': _Mv(cpx)},
                              'ratios': R}
        out[tk] = rec
        stats['total_debt'] += 1
        if rec['interest_ytd_m'] is not None or rec['interest_fy_m'] is not None: stats['interest'] += 1
        if rec['raised_ytd_m'] is not None: stats['raised'] += 1
    snap = {'generated_at': now_iso(), 'by_ticker': out}
    write_json("data/debt.json", snap)
    rsnap = {'generated_at': now_iso(), 'by_ticker': ratios_out}
    write_json("data/ratios.json", rsnap)
    print('ratios coverage:', len(ratios_out), '| maturities:', sum(1 for r in out.values() if r.get('maturity')))
    print('coverage:', stats, 'of', len(uni))
