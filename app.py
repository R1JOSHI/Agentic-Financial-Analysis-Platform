import json, time, urllib.request, urllib.error, pathlib
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE = pathlib.Path(__file__).parent
CACHE_DIR = BASE / 'cache'
CACHE_DIR.mkdir(exist_ok=True)
SEC_HEADERS = {
    'User-Agent': 'FinancialAgentAI RiddhishJoshi your_email@example.com',
    'Accept-Encoding': 'identity',
    'Host': ''
}
SEC_BASE = 'https://data.sec.gov'
SEC_WWW = 'https://www.sec.gov'
LAST_REQUEST = {'t': 0.0}

def sec_get(url, host='data.sec.gov'):
    # polite SEC fair-access: far below 10/sec
    now = time.time()
    wait = 0.25 - (now - LAST_REQUEST['t'])
    if wait > 0:
        time.sleep(wait)
    LAST_REQUEST['t'] = time.time()
    headers = dict(SEC_HEADERS)
    headers['Host'] = host
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))

def cached_json(name, fetcher, ttl=86400):
    path = CACHE_DIR / name
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        return json.loads(path.read_text(encoding='utf-8'))
    data = fetcher()
    path.write_text(json.dumps(data), encoding='utf-8')
    return data

def tickers():
    return cached_json('company_tickers.json', lambda: sec_get(f'{SEC_WWW}/files/company_tickers.json', host='www.sec.gov'), ttl=86400)

def cik10(cik):
    return str(cik).zfill(10)

def search_companies(q):
    q = (q or '').lower().strip()
    rows = []
    for _, item in tickers().items():
        ticker = item.get('ticker','')
        title = item.get('title','')
        if not q or q in ticker.lower() or q in title.lower() or q in str(item.get('cik_str','')):
            rows.append({'ticker': ticker, 'title': title, 'cik': cik10(item.get('cik_str'))})
        if len(rows) >= 25:
            break
    return rows

def companyfacts(cik):
    return cached_json(f'facts_{cik10(cik)}.json', lambda: sec_get(f'{SEC_BASE}/api/xbrl/companyfacts/CIK{cik10(cik)}.json'), ttl=21600)

def submissions(cik):
    return cached_json(f'sub_{cik10(cik)}.json', lambda: sec_get(f'{SEC_BASE}/submissions/CIK{cik10(cik)}.json'), ttl=21600)

def find_concept(facts, tags, unit='USD'):
    usgaap = facts.get('facts',{}).get('us-gaap',{})
    best = []
    for tag in tags:
        obj = usgaap.get(tag)
        if not obj: continue
        units = obj.get('units',{})
        candidates = units.get(unit) or units.get('USD/shares') or next(iter(units.values()), [])
        for v in candidates:
            if v.get('val') is None: continue
            form = v.get('form','')
            fy = v.get('fy') or 0
            end = v.get('end','')
            filed = v.get('filed','')
            score = (10 if form == '10-K' else 5 if form == '10-Q' else 1, fy, end, filed)
            best.append((score, tag, v))
    if not best:
        return None
    best.sort(key=lambda x: x[0], reverse=True)
    tag, v = best[0][1], best[0][2]
    return {'tag': tag, 'value': v.get('val'), 'fy': v.get('fy'), 'fp': v.get('fp'), 'form': v.get('form'), 'filed': v.get('filed'), 'end': v.get('end')}

def concept_series(facts, tags, unit='USD'):
    usgaap = facts.get('facts',{}).get('us-gaap',{})
    rows = []
    seen = set()
    for tag in tags:
        obj = usgaap.get(tag)
        if not obj: continue
        units = obj.get('units',{})
        candidates = units.get(unit) or next(iter(units.values()), [])
        for v in candidates:
            if v.get('val') is None or v.get('form') != '10-K' or not v.get('fy'): continue
            key = (v.get('fy'), tag, v.get('end'))
            if key in seen: continue
            seen.add(key)
            rows.append({'fy': v.get('fy'), 'value': v.get('val'), 'tag': tag, 'filed': v.get('filed'), 'end': v.get('end')})
    rows.sort(key=lambda r: (r['fy'], r.get('end','')), reverse=True)
    by_year = {}
    for r in rows:
        by_year.setdefault(r['fy'], r)
    return [by_year[y] for y in sorted(by_year.keys(), reverse=True)[:5]]

def safe_div(a,b):
    try:
        if a is None or b in (None,0): return None
        return a/b
    except Exception:
        return None

def analyze(cik):
    facts = companyfacts(cik)
    subs = submissions(cik)
    concepts = {
        'Revenue': ['Revenues','RevenueFromContractWithCustomerExcludingAssessedTax','SalesRevenueNet'],
        'Net Income': ['NetIncomeLoss'],
        'Assets': ['Assets'],
        'Liabilities': ['Liabilities'],
        'Equity': ['StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
        'Operating Cash Flow': ['NetCashProvidedByUsedInOperatingActivities'],
        'Capex': ['PaymentsToAcquirePropertyPlantAndEquipment'],
        'Long Term Debt': ['LongTermDebtNoncurrent','LongTermDebtAndFinanceLeaseObligationsNoncurrent'],
        'Current Assets': ['AssetsCurrent'],
        'Current Liabilities': ['LiabilitiesCurrent'],
        'Cash': ['CashAndCashEquivalentsAtCarryingValue','CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents'],
    }
    latest = {name: find_concept(facts, tags) for name,tags in concepts.items()}
    revenue_series = concept_series(facts, concepts['Revenue'])
    ni_series = concept_series(facts, concepts['Net Income'])
    rev = latest['Revenue']['value'] if latest['Revenue'] else None
    ni = latest['Net Income']['value'] if latest['Net Income'] else None
    assets = latest['Assets']['value'] if latest['Assets'] else None
    liab = latest['Liabilities']['value'] if latest['Liabilities'] else None
    equity = latest['Equity']['value'] if latest['Equity'] else None
    ocf = latest['Operating Cash Flow']['value'] if latest['Operating Cash Flow'] else None
    capex = latest['Capex']['value'] if latest['Capex'] else None
    debt = latest['Long Term Debt']['value'] if latest['Long Term Debt'] else None
    ca = latest['Current Assets']['value'] if latest['Current Assets'] else None
    cl = latest['Current Liabilities']['value'] if latest['Current Liabilities'] else None
    fcf = (ocf - abs(capex)) if ocf is not None and capex is not None else None
    rev_growth = None
    if len(revenue_series) >= 2 and revenue_series[1]['value']:
        rev_growth = (revenue_series[0]['value'] - revenue_series[1]['value']) / abs(revenue_series[1]['value'])
    metrics = {
        'Revenue Growth YoY': rev_growth,
        'Net Margin': safe_div(ni, rev),
        'ROA': safe_div(ni, assets),
        'Debt to Equity': safe_div(debt or liab, equity),
        'Current Ratio': safe_div(ca, cl),
        'Free Cash Flow': fcf,
        'FCF Margin': safe_div(fcf, rev),
        'Liabilities / Assets': safe_div(liab, assets),
    }
    score = 50
    reasons = []
    def add(cond, pts, text):
        nonlocal score
        if cond is True:
            score += pts; reasons.append('+'+str(pts)+' '+text)
        elif cond is False:
            score -= abs(pts); reasons.append('-'+str(abs(pts))+' '+text)
    add(metrics['Revenue Growth YoY'] is not None and metrics['Revenue Growth YoY'] > 0.05, 10, 'Revenue growing above 5% YoY')
    add(metrics['Net Margin'] is not None and metrics['Net Margin'] > 0.10, 10, 'Healthy net margin')
    add(metrics['FCF Margin'] is not None and metrics['FCF Margin'] > 0.05, 10, 'Positive free-cash-flow generation')
    add(metrics['Debt to Equity'] is not None and metrics['Debt to Equity'] < 1.5, 10, 'Debt level manageable versus equity')
    add(metrics['Current Ratio'] is not None and metrics['Current Ratio'] > 1.0, 5, 'Short-term liquidity looks acceptable')
    add(metrics['Liabilities / Assets'] is not None and metrics['Liabilities / Assets'] < 0.75, 5, 'Balance-sheet leverage not excessive')
    score = max(0, min(100, score))
    if score >= 75: verdict = 'Strong / Watchlist Buy candidate'
    elif score >= 60: verdict = 'Moderate / Needs valuation check'
    elif score >= 45: verdict = 'Neutral / Hold for deeper due diligence'
    else: verdict = 'High risk / Avoid until fundamentals improve'
    recent = subs.get('filings',{}).get('recent',{})
    filings = []
    for i, form in enumerate(recent.get('form',[])[:80]):
        if form in ('10-K','10-Q','8-K','DEF 14A','S-1','4'):
            accession = recent.get('accessionNumber',[None]*80)[i]
            primary = recent.get('primaryDocument',[None]*80)[i]
            doc_url = None
            if accession and primary:
                doc_url = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-","")}/{primary}'
            filings.append({'form': form, 'filingDate': recent.get('filingDate',[None]*80)[i], 'reportDate': recent.get('reportDate',[None]*80)[i], 'document': primary, 'url': doc_url})
        if len(filings) >= 12: break
    return {'entityName': facts.get('entityName') or subs.get('name'), 'cik': cik10(cik), 'latest': latest, 'series': {'Revenue': revenue_series, 'Net Income': ni_series}, 'metrics': metrics, 'score': round(score), 'verdict': verdict, 'reasons': reasons, 'filings': filings, 'source': 'SEC EDGAR companyfacts + submissions'}

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()
    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        try:
            if parsed.path == '/api/search':
                return self.json(search_companies(qs.get('q',[''])[0]))
            if parsed.path == '/api/analyze':
                cik = qs.get('cik',[''])[0]
                if not cik: raise ValueError('Missing cik')
                return self.json(analyze(cik))
            if parsed.path == '/api/health':
                return self.json({'status':'ok','source':'SEC EDGAR','token':'No API token required; User-Agent used'})
            return super().do_GET()
        except Exception as e:
            self.send_response(500); self.send_header('Content-Type','application/json'); self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())
    def json(self, data):
        self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
        self.wfile.write(json.dumps(data).encode())

if __name__ == '__main__':
    port = 8000
    print(f'Financial SEC Real Agent running at http://localhost:{port}/index.html')
    print('SEC token: no token required. Update User-Agent in app.py with your name/email for production.')
    ThreadingHTTPServer(('localhost', port), Handler).serve_forever()
