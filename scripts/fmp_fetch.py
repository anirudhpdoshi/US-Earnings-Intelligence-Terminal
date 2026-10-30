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


def main():
    if not KEY:
        print("ERROR: FMP_KEY env var is empty - repository secret missing or not mapped.", file=sys.stderr)
        return 2

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
