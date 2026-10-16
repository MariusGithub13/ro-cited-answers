#!/usr/bin/env python3
"""
The live demo: one page and a small JSON API around ask.py.

Every answer goes through the same four gates as the command line. The page
shows the verdict, the gate that decided it, and for an accepted answer the
source each sentence came from, so a reader can check the claim instead of
trusting it.

Standard library only, so the image stays small and there is nothing to patch
but Python itself.

  GET  /            the page
  POST /api/ask     {"question": "..."} -> verdict, gate, answer, sources, attribution
  GET  /health      liveness plus the version and the gate thresholds in use
                    (not /healthz: Cloud Run reserves paths ending in z, 16.10.2026)
  GET  /api/stats   how many questions today, accepted and refused, by gate

Telemetry (web/otel.py): one span per POST /api/ask to GitLab Observability when
OTEL_EXPORTER_OTLP_ENDPOINT is set: outcome, gate, status, latency. Never the question.

Limits, because the model is a paid API: 300 characters per question, 6
questions per minute per address, and a daily cap for the whole service.
"""
import collections, datetime, html, json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ask  # noqa: E402
import otel  # noqa: E402  (web/otel.py: one span per question, off when no endpoint is set)

VERSION = os.environ.get('APP_VERSION', 'dev')
PORT = int(os.environ.get('PORT', '8080'))
MAX_LEN = 300
PER_MINUTE = int(os.environ.get('RO_PER_MINUTE', '6'))
DAILY_CAP = int(os.environ.get('RO_DAILY_CAP', '400'))
# Sent on every response: no referrer leaks the question URL, and the page asks for no device features.
SECURITY_HEADERS = {
    'Referrer-Policy': 'no-referrer',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
}

_lock = threading.Lock()          # one model call at a time: predictable cost and load
_hits = collections.defaultdict(collections.deque)
_day = {'date': None, 'total': 0, 'verdicts': collections.Counter()}


def _today():
    return datetime.datetime.now(datetime.UTC).date().isoformat()


def _rate_ok(addr):
    now = time.time()
    q = _hits[addr]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= PER_MINUTE:
        return False
    q.append(now)
    return True


def _count(verdict, gate):
    if _day['date'] != _today():
        _day.update(date=_today(), total=0, verdicts=collections.Counter())
    _day['total'] += 1
    _day['verdicts'][f"{verdict}:{gate or '-'}"] += 1


def answer(question):
    """Run the gates and shape the result for the page and the API."""
    docs = {d['id']: d for d in ask.load_docs()}
    with _lock:
        record, text = ask.ask(question, verbose=False)
    out = {
        'question': question,
        'verdict': record['verdict'],
        'gate': record.get('gate'),
        'reason': record.get('reason'),
        'model': record.get('model'),
        'retrieved': record.get('retrieved', []),
        'version': VERSION,
    }
    if record['verdict'] == 'ACCEPTAT':
        out['answer'] = text.split('\n\nSURSE:')[0].strip()
        out['sources'] = [{'id': c, 'title': docs[c]['titlu'], 'url': docs[c]['sursa'],
                           'checked': docs[c]['verificat']} for c in record.get('cited', [])]
        out['attribution'] = record.get('attribution', [])
        out['dropped_as_padding'] = record.get('cited_dropped_as_padding', [])
    else:
        out['answer'] = ask.REFUSAL
    return out


EXAMPLES = [
    'În câte zile se returnează un colet dacă nu depun documentele?',
    'Când am nevoie de cod EORI pentru un colet?',
    'Cum verific dacă un număr EORI este valid?',
    'Care este capitala Franței?',
]

PAGE = """<!doctype html>
<html lang="ro"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RO Cited Answers</title>
<meta name="description" content="Răspunsuri în limba română care trec prin patru porți de verificare: fiecare propoziție are sursa ei, altfel răspunsul este refuzat.">
<style>
:root{--bg:#ffffff;--fg:#1a1a1a;--muted:#4a4a4a;--line:#d0d0d0;--ok:#0b6b2f;--no:#9b1c1c;--card:#f5f5f5;--link:#0b4f9c}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#ececec;--muted:#b8b8b8;--line:#3a3a3a;--ok:#6fd492;--no:#ff9b9b;--card:#1e1e1e;--link:#8cc4ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px 48px}h1{font-size:1.6rem;margin:0 0 4px}
p.lead{color:var(--muted);margin:0 0 20px}form{display:flex;gap:8px;flex-wrap:wrap}
input{flex:1 1 260px;min-width:0;padding:12px;font:inherit;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg)}
button{padding:12px 18px;font:inherit;border:0;border-radius:8px;background:var(--fg);color:var(--bg);cursor:pointer}
.ex{margin:12px 0 24px;display:flex;flex-wrap:wrap;gap:8px}.ex button{background:var(--card);color:var(--fg);border:1px solid var(--line);padding:6px 10px;font-size:.9rem;text-align:left}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;overflow-wrap:anywhere}
.v{font-weight:700}.v.ok{color:var(--ok)}.v.no{color:var(--no)}small{color:var(--muted)}a{color:var(--link)}
ol{padding-left:20px}li{margin:6px 0}footer{margin-top:32px;color:var(--muted);font-size:.9rem}
</style></head><body><main>
<h1>RO Cited Answers</h1>
<p class="lead">Întrebați despre returnarea coletelor și codul EORI. Răspunsul trece prin patru porți: sursa potrivită, citarea, cifrele și fiecare propoziție susținută de o sursă. Dacă o poartă pică, răspunsul este refuzat.</p>
<form id="f"><input id="q" maxlength="300" placeholder="Întrebarea dumneavoastră" aria-label="Întrebarea"><button>Întreabă</button></form>
<div class="ex">__EXAMPLES__</div>
<div id="out" aria-live="polite"></div>
<footer>Model: __MODEL__ · versiunea __VERSION__ · cod sursă MIT: <a href="__REPO__">__REPO__</a></footer>
</main><script>
const f=document.getElementById('f'),q=document.getElementById('q'),out=document.getElementById('out');
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function go(text){q.value=text;out.innerHTML='<p><small>Se verifică...</small></p>';
 try{const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:text})});
 const d=await r.json();if(!r.ok){out.innerHTML='<div class="card">'+esc(d.error||'Eroare')+'</div>';return}
 const ok=d.verdict==='ACCEPTAT';let h='<div class="card"><p class="v '+(ok?'ok':'no')+'">'+(ok?'ACCEPTAT':'REFUZAT')+(d.gate?' · poarta '+esc(d.gate):'')+'</p><p>'+esc(d.answer)+'</p>';
 if(d.reason)h+='<p><small>'+esc(d.reason)+'</small></p>';
 if(ok){h+='<p><b>Fiecare propoziție și sursa ei</b></p><ol>'+d.attribution.map(a=>'<li>'+esc(a.sentence)+' <small>['+esc(a.source)+', '+Math.round(a.overlap*100)+'%]</small></li>').join('')+'</ol>';
  h+='<p><b>Surse</b></p><ol>'+d.sources.map(s=>'<li>'+esc(s.title)+'<br><a href="'+esc(s.url)+'" rel="noopener">'+esc(s.url)+'</a> <small>verificat la '+esc(s.checked)+'</small></li>').join('')+'</ol>'}
 out.innerHTML=h+'</div>'}catch(e){out.innerHTML='<div class="card">Eroare de rețea.</div>'}}
f.addEventListener('submit',e=>{e.preventDefault();if(q.value.trim())go(q.value.trim())});
document.querySelectorAll('.ex button').forEach(b=>b.addEventListener('click',()=>go(b.textContent)));
</script></body></html>"""

REPO = os.environ.get('RO_REPO_URL', 'https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43427415/ro-cited-answers')


def render_page():
    ex = ''.join(f'<button type="button">{html.escape(e)}</button>' for e in EXAMPLES)
    return (PAGE.replace('__EXAMPLES__', ex).replace('__MODEL__', html.escape(ask.MODEL))
            .replace('__VERSION__', html.escape(VERSION)).replace('__REPO__', html.escape(REPO)))


class Handler(BaseHTTPRequestHandler):
    server_version = 'ro-cited'

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else (
            json.dumps(body, ensure_ascii=False).encode() if not isinstance(body, str) else body.encode())
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def _addr(self):
        return (self.headers.get('CF-Connecting-IP') or self.headers.get('X-Real-IP')
                or self.client_address[0])

    def log_message(self, fmt, *args):   # one line per request, no question text
        sys.stderr.write('%s %s\n' % (self.log_date_time_string(), fmt % args))

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/':
            return self._send(200, render_page(), 'text/html; charset=utf-8')
        if path in ('/health', '/healthz'):
            return self._send(200, {'ok': True, 'version': VERSION, 'backend': ask.BACKEND,
                                    'model': ask.MODEL, 'embed': ask.EMBED,
                                    'min_sim': ask.MIN_SIM, 'min_ground': ask.MIN_GROUND,
                                    'telemetry': otel.status()})
        if path == '/api/stats':
            return self._send(200, {'date': _day['date'], 'total': _day['total'],
                                    'by_verdict_gate': dict(_day['verdicts'])})
        return self._send(404, {'error': 'not found'})

    def do_POST(self):
        if self.path.split('?')[0] != '/api/ask':
            return self._send(404, {'error': 'not found'})
        t0 = time.time_ns()

        def done(code, body, outcome, gate=None):
            otel.record(outcome, gate, code, t0)     # verdict, gate, status, timing: nothing else
            return self._send(code, body)
        try:
            n = int(self.headers.get('Content-Length') or 0)
            q = (json.loads(self.rfile.read(min(n, 4096)) or b'{}').get('question') or '').strip()
        except (ValueError, AttributeError):
            return done(400, {'error': 'JSON invalid'}, 'rejected')
        if not q or len(q) > MAX_LEN:
            return done(400, {'error': f'Întrebarea trebuie să aibă între 1 și {MAX_LEN} de caractere.'}, 'rejected')
        if not _rate_ok(self._addr()):
            return done(429, {'error': 'Prea multe întrebări într-un minut. Reveniți puțin mai târziu.'}, 'rate_limited')
        if _day['date'] == _today() and _day['total'] >= DAILY_CAP:
            return done(429, {'error': 'Limita zilnică a demonstrației a fost atinsă. Reveniți mâine.'}, 'daily_cap')
        try:
            out = answer(q)
        except Exception as e:           # a model or network failure is reported, never hidden
            sys.stderr.write(f'ask failed: {e!r}\n')
            return done(502, {'error': 'Modelul nu a răspuns. Încercați din nou.'}, 'error')
        _count(out['verdict'], out['gate'])
        return done(200, out, 'answered' if out['verdict'] == 'ACCEPTAT' else 'refused', out['gate'])

if __name__ == '__main__':
    ask.build_index(ask.load_docs())   # build or load the vector cache before the first visitor
    print(f'ro-cited {VERSION} on :{PORT} backend={ask.BACKEND} model={ask.MODEL}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
