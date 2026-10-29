#!/usr/bin/env python3
"""Twelve Data refresh for the US Earnings Intelligence Terminal.

Runs inside GitHub Actions. The API key comes ONLY from the environment
variable TWELVE_DATA_KEY, which the workflow maps from the repository
secret TWELVE_DATA. The key never appears in any file, log line, or output.

Budget discipline (user instruction, Oct 29 2026): stay well under
600 API credits/day.
  - /api_usage check first; if today's usage is already >= 560, make no
    further calls and leave data files untouched (fail-soft).
  - Universe quotes: ONE batched /quote call per 50 symbols (2 calls).
  - Reactions: one /time_series call per tracked reporter (capped at 20).
  - Earnings cross-check: one batched /earnings call.
Worst case per run: ~24 calls. At 3 scheduled runs/day: ~72 calls/day,
plus per-symbol credit counting headroom under the 600 cap.

Outputs (only written when the fetch succeeded):
  data/prices.json     latest quotes for the Top-100 universe
  data/reactions.json  first-full-session stock reaction for reporters
  data/td_earnings.json earnings dates cross-check (raw, trimmed)
  data/td_usage.json   API usage snapshot for the day

Fail-soft by module: a failed module leaves its previous file untouched
and never fails the whole run. Auth failure (401/403 on /api_usage)
exits non-zero so the Actions run shows red and the problem is visible.
"""
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://api.twelvedata.com"
KEY = os.environ.get("TWELVE_DATA_KEY", "")
DAILY_HARD_CAP = 600
STOP_AT = 560  # stop making calls once today's usage reaches this
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

calls = 0


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
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)
    print(f"wrote {rel}")


def load_universe():
    path = os.path.join(ROOT, "data", "top100-universe-v1.csv")
    tickers = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t = (row.get("ticker") or "").strip()
            if t:
                tickers.append(t)
    return tickers


def main():
    if not KEY:
        print("ERROR: TWELVE_DATA_KEY env var is empty - repository secret TWELVE_DATA missing or not mapped.", file=sys.stderr)
        return 2

    # 1) Usage check ------------------------------------------------------
    try:
        usage = get("/api_usage", {})
    except Exception as e:
        print(f"ERROR: /api_usage failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    if isinstance(usage, dict) and usage.get("status") == "error":
        print(f"ERROR: Twelve Data rejected the key: {usage.get('message')}", file=sys.stderr)
        return 2
    used = usage.get("current_day_usage")
    limit = usage.get("daily_limit")
    print(f"api_usage: used_today={used} daily_limit={limit} plan={usage.get('plan_category')}/{usage.get('plan_id')}")
    write_json("data/td_usage.json", {"checked_at": now_iso(), "current_day_usage": used,
                                      "daily_limit": limit, "hard_cap_guard": DAILY_HARD_CAP})
    if isinstance(used, (int, float)) and used >= STOP_AT:
        print(f"Budget guard: usage {used} >= {STOP_AT}; skipping all further calls today.")
        return 0

    tickers = load_universe()
    print(f"universe: {len(tickers)} tickers")

    # 2) Batched quotes ----------------------------------------------------
    quotes = {}
    for i in range(0, len(tickers), 50):
        chunk = tickers[i:i + 50]
        try:
            resp = get("/quote", {"symbol": ",".join(chunk)})
        except Exception as e:
            print(f"quote chunk {i}: FAILED {type(e).__name__}: {e}")
            continue
        if isinstance(resp, dict) and resp.get("symbol"):  # single-symbol shape
            resp = {resp["symbol"]: resp}
        if isinstance(resp, dict):
            for sym, q in resp.items():
                if isinstance(q, dict) and q.get("status") != "error" and q.get("close") is not None:
                    try:
                        quotes[sym] = {
                            "price": float(q["close"]),
                            "prev_close": float(q["previous_close"]) if q.get("previous_close") else None,
                            "change_pct": float(q["percent_change"]) if q.get("percent_change") is not None else None,
                            "datetime": q.get("datetime"),
                            "market_open": q.get("is_market_open"),
                        }
                    except (TypeError, ValueError):
                        pass
    if quotes:
        write_json("data/prices.json", {"generated_at": now_iso(), "count": len(quotes), "quotes": quotes})
    else:
        print("quotes: no valid quotes returned; prices.json left untouched")

    # 3) Reactions for tracked reporters -----------------------------------
    rep_path = os.path.join(ROOT, "data", "reporters.json")
    reporters = []
    if os.path.exists(rep_path):
        with open(rep_path, encoding="utf-8") as f:
            reporters = json.load(f).get("reporters", [])
    reactions = {}
    for rep in reporters[:20]:
        tk, edate, timing = rep["ticker"], rep["earnings_date"], rep.get("timing", "AMC")
        try:
            ts = get("/time_series", {"symbol": tk, "interval": "1day", "outputsize": 15})
        except Exception as e:
            print(f"time_series {tk}: FAILED {type(e).__name__}: {e}")
            continue
        vals = ts.get("values") if isinstance(ts, dict) else None
        if not vals:
            print(f"time_series {tk}: no values")
            continue
        days = sorted(vals, key=lambda v: v["datetime"])  # ascending
        closes = [(v["datetime"], float(v["close"])) for v in days]
        if timing == "AMC":
            before = [c for c in closes if c[0] <= edate]
            after = [c for c in closes if c[0] > edate]
        else:  # BMO: reaction is the release session itself vs the prior close
            after = [c for c in closes if c[0] >= edate]
            before = [c for c in closes if c[0] < edate]
        if before and after:
            cb, ca = before[-1][1], after[0][1]
            reactions[tk] = {
                "earnings_date": edate, "timing": timing,
                "close_before": cb, "close_after": ca, "session_after": after[0][0],
                "reaction_pct": round((ca / cb - 1) * 100, 2),
            }
            print(f"reaction {tk}: {reactions[tk]['reaction_pct']:+.2f}% ({cb} -> {ca} on {after[0][0]})")
    if reactions:
        write_json("data/reactions.json", {"generated_at": now_iso(), "reactions": reactions})

    # 4) Earnings-date cross-check (one batched call, fail-soft) ------------
    try:
        er = get("/earnings", {"symbol": ",".join(tickers)})
        if isinstance(er, dict) and er.get("earnings"):
            trimmed = {}
            for sym, rows in er["earnings"].items():
                if isinstance(rows, list):
                    trimmed[sym] = [{"date": r.get("date"), "time": r.get("time"),
                                     "eps_estimate": r.get("epsEstimate"),
                                     "eps_actual": r.get("epsActual")} for r in rows[:6]]
            if trimmed:
                write_json("data/td_earnings.json", {"generated_at": now_iso(), "earnings": trimmed})
    except Exception as e:
        print(f"earnings cross-check: FAILED {type(e).__name__}: {e} (fail-soft)")

    print(f"done. API calls this run: {calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
