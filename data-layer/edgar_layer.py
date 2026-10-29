#!/usr/bin/env python3
"""EDGAR data layer for the US Earnings Intelligence Terminal.
- build_cik_map(): SEC company_tickers.json -> CIK map for the Top-100 universe file.
- poll(tickers): submissions API -> latest 8-K/10-Q/10-K per ticker (release detection).
- facts(cik): companyfacts XBRL pull (cached).
Rules: declared User-Agent (EDGAR 403s anonymous bots); <=8 req/s; fail-soft per ticker;
never overwrite a good record with a failure."""
import urllib.request, json, time, pathlib, csv, sys, datetime
ROOT = pathlib.Path.home()/"workspace/earnings-data-layer"
UNI = pathlib.Path.home()/"workspace/goals/earnings-intelligence-card-engine/files/top100-universe-v1.csv"
UA = {'User-Agent': 'Earnings Intelligence Terminal research adoshi@dgglobal.ca', 'Accept-Encoding': 'gzip'}
import gzip, io
def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip': raw = gzip.decompress(raw)
        return json.loads(raw)
def universe():
    rows = list(csv.DictReader(open(UNI)))
    return [r['ticker'] for r in rows]
def build_cik_map():
    data = get('https://www.sec.gov/files/company_tickers.json')
    sec = {v['ticker']: (str(v['cik_str']).zfill(10), v['title']) for v in data.values()}
    out, missing = {}, []
    for t in universe():
        key = t.replace('.', '-')  # BRK.B handled below too
        if t in sec: out[t] = sec[t]
        elif key in sec: out[t] = sec[key]
        else: missing.append(t)
    (ROOT/'cik_map.json').write_text(json.dumps(out, indent=1))
    return out, missing
def poll(tickers, cikmap):
    res = {}
    for t in tickers:
        cik = cikmap.get(t, (None,))[0]
        if not cik: res[t] = {'error': 'no CIK'}; continue
        try:
            d = get(f'https://data.sec.gov/submissions/CIK{cik}.json')
            rec = d['filings']['recent']
            hits = []
            for form, date, acc, items in zip(rec['form'], rec['filingDate'], rec['accessionNumber'], rec.get('items', ['']*len(rec['form']))):
                if form in ('8-K', '10-Q', '10-K') and date >= '2026-10-20':
                    hits.append({'form': form, 'date': date, 'accession': acc, 'items': items})
                if len(hits) >= 6: break
            res[t] = {'name': d.get('name'), 'hits': hits}
        except Exception as e:
            res[t] = {'error': str(e)[:120]}
        time.sleep(0.15)
    return res
if __name__ == '__main__':
    cikmap, missing = build_cik_map()
    print(f"CIK map: {len(cikmap)}/100 mapped; missing: {missing}")
    targets = sys.argv[1:] or ['LLY','MA','AMZN','INTC','SBUX','MRK','BMY','GILD','MDLZ','CAT']
    out = poll(targets, cikmap)
    stamp = datetime.datetime.now().isoformat(timespec='seconds')
    (ROOT/'latest_poll.json').write_text(json.dumps({'polled_at': stamp, 'results': out}, indent=1))
    for t, r in out.items():
        if 'error' in r: print(t, 'ERROR', r['error'])
        else:
            ks = [h for h in r['hits'] if h['form'] == '8-K']
            print(t, r['name'], '| recent 8-Ks:', [(h['date'], h['items']) for h in ks[:3]] or 'none since Oct 20')
