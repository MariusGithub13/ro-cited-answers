#!/usr/bin/env python3
"""
Offline tests for web/otel.py: no model, no network except a stub collector on 127.0.0.1.

  1. the span is valid OTLP/HTTP JSON: ids of the right length, service.version, outcome and gate
  2. end to end through the real app: a question carrying a fake name and a fake CNP is sent, and
     the bytes the collector receives contain neither (nor any other text of the question)
  3. a dead collector: record() returns at once, the failure is counted, the answer is not delayed
  4. a slow collector (10 s): record() still returns at once
  5. no endpoint configured: telemetry is off, record() is a no-op
"""
import importlib, json, os, socket, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'web'))
sys.path.insert(0, HERE)

received = []


class Collector(BaseHTTPRequestHandler):
    delay = 0

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
        time.sleep(self.delay)
        received.append((self.path, body))
        self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'{}')

    def log_message(self, *a):
        pass


def serve(handler, port=0):
    srv = ThreadingHTTPServer(('127.0.0.1', port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p


def load_otel(endpoint):
    if endpoint is None:
        os.environ.pop('OTEL_EXPORTER_OTLP_ENDPOINT', None)
    else:
        os.environ['OTEL_EXPORTER_OTLP_ENDPOINT'] = endpoint
    import otel
    return importlib.reload(otel)


def wait_for(cond, seconds=5):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


results = []


def check(name, ok, detail=''):
    results.append(ok)
    print(('PASS' if ok else 'FAIL') + f'  {name}' + (f'  ({detail})' if detail else ''))


# 1. span shape
os.environ['APP_VERSION'] = 'test1234'
otel = load_otel(None)
span = otel.build_span('refused', 'A_RETRIEVAL', 200, 1_000_000_000, 1_250_000_000)
attrs = {a['key']: list(a['value'].values())[0] for a in span['attributes']}
res = {a['key']: list(a['value'].values())[0] for a in otel.payload([span])['resourceSpans'][0]['resource']['attributes']}
check('span ids and timing', len(span['traceId']) == 32 and len(span['spanId']) == 16 and attrs['ro.latency_ms'] == '250')
check('outcome and gate on a refusal', attrs['ro.outcome'] == 'refused' and attrs['ro.gate'] == 'A_RETRIEVAL')
check('service.version from APP_VERSION', res['service.version'] == 'test1234' and res['service.name'] == 'ro-cited')
ok_span = otel.build_span('answered', 'A_RETRIEVAL', 200, 0, 1)
check('no gate on an answered question', 'ro.gate' not in {a['key'] for a in ok_span['attributes']})
check('unknown outcome becomes error', {a['key']: list(a['value'].values())[0] for a in otel.build_span('x', None, 502, 0, 1)['attributes']}['ro.outcome'] == 'error')

# 5. off without an endpoint
otel.record('answered', None, 200, time.time_ns())
check('no endpoint: telemetry off', not otel.enabled() and otel.status()['sent'] == 0)

# 2. end to end through the app, with a fake name and CNP in the question
collector = serve(Collector)
otel = load_otel(f'http://127.0.0.1:{collector.server_port}')
import app  # noqa: E402  (imports the same otel module object)
app.otel = otel
app_srv = serve(app.Handler)
secret_question = 'Ion Popescu, CNP 1800101123456, ' + 'x' * 400   # too long: rejected, no model call
req = urllib.request.Request(f'http://127.0.0.1:{app_srv.server_port}/api/ask',
                             data=json.dumps({'question': secret_question}).encode(),
                             headers={'Content-Type': 'application/json'}, method='POST')
try:
    urllib.request.urlopen(req, timeout=5)
    status = 200
except urllib.error.HTTPError as e:
    status = e.code
check('app answers 400 for the over-long question', status == 400)
check('a span reached the collector', wait_for(lambda: received), f'{len(received)} request(s)')
raw = b''.join(b for _, b in received)
check('collector path is /v1/traces', all(p == '/v1/traces' for p, _ in received))
check('the question text never left the app',
      b'1800101123456' not in raw and b'Popescu' not in raw and b'xxxxxxxxxx' not in raw)
body = json.loads(received[0][1])
sp = body['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
check('outcome rejected, status 400', {a['key']: list(a['value'].values())[0] for a in sp['attributes']}['ro.outcome'] == 'rejected')
health = json.load(urllib.request.urlopen(f'http://127.0.0.1:{app_srv.server_port}/health', timeout=5))
check('/health reports telemetry on and counts', health['telemetry']['enabled'] and health['telemetry']['sent'] >= 1)

# 3. dead collector
otel = load_otel(f'http://127.0.0.1:{free_port()}')
t = time.time(); otel.record('answered', None, 200, time.time_ns()); dt = time.time() - t
check('dead collector: record returns at once', dt < 0.05, f'{dt*1000:.1f} ms')
check('dead collector: failure counted', wait_for(lambda: otel.status()['failed'] >= 1))

# 4. slow collector
Collector.delay = 10
slow = serve(Collector)
otel = load_otel(f'http://127.0.0.1:{slow.server_port}')
t = time.time(); otel.record('answered', None, 200, time.time_ns()); dt = time.time() - t
check('slow collector: record returns at once', dt < 0.05, f'{dt*1000:.1f} ms')
check('slow collector: times out and counts a failure', wait_for(lambda: otel.status()['failed'] >= 1, 5))

print(f'{sum(results)} passed, {len(results) - sum(results)} failed, out of {len(results)}')
sys.exit(0 if all(results) else 1)
