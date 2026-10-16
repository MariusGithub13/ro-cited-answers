"""
One span per /api/ask request, sent to GitLab Observability over OTLP/HTTP JSON.

Standard library only (the image stays stdlib, AGENTS.md rule 7). What a span carries is an
ALLOWLIST: the outcome, the gate that refused, the HTTP status and the latency. Never the
question, the answer, the gate's reason text (gates C and D quote answer text and numbers),
the sources, the client address or any header. The span builder only ever receives those
four values, so the question cannot reach it by accident.

A slow or dead collector can never slow or break an answer: record() only puts the span on a
bounded queue (full = dropped and counted); one daemon thread sends, with a 2 s timeout, and
after 5 failures in a row it pauses 60 s and drops spans meanwhile. No endpoint configured =
nothing starts (no thread, no queue). Export is best effort: Cloud Run throttles the CPU
between requests, so a span can wait for the next request to leave. The group's ingestion
endpoint takes no key, so anyone who knows the group id could post spans to it: treat the
telemetry as an operational signal, never as evidence. Requests from deploy/smoke.py carry
X-RO-Smoke: 1 and are marked ro.synthetic.

  OTEL_EXPORTER_OTLP_ENDPOINT   e.g. https://<group id>.otel.gitlab-o11y.com:14318 (unset = off)
  APP_VERSION                   service.version
  DEPLOY_ENV                    deployment.environment.name (default production)
  GITLAB_PROJECT_ID / GITLAB_PROJECT_NAME   link the telemetry to the GitLab project
"""
import json, os, queue, sys, threading, time, urllib.request

ENDPOINT = (os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT') or '').rstrip('/')
OUTCOMES = {'answered', 'refused', 'rejected', 'rate_limited', 'daily_cap', 'error'}
GATES = {'A_RETRIEVAL', 'B_CITATION', 'C_NUMBERS', 'D_GROUNDING', 'MODEL_ABSTAINED'}
TIMEOUT_S, QUEUE_MAX, BREAK_AFTER, BREAK_FOR_S = 2.0, 100, 5, 60

counters = {'sent': 0, 'failed': 0, 'dropped': 0}
_q = queue.Queue(maxsize=QUEUE_MAX) if ENDPOINT else None
_lock = threading.Lock()


def enabled():
    return _q is not None


def _resource():
    attrs = {'service.name': 'ro-cited',
             'service.version': os.environ.get('APP_VERSION', 'dev'),
             'deployment.environment.name': os.environ.get('DEPLOY_ENV', 'production')}
    for env, key in (('GITLAB_PROJECT_ID', 'gitlab.project.id'), ('GITLAB_PROJECT_NAME', 'gitlab.project.name')):
        if os.environ.get(env):
            attrs[key] = os.environ[env]
    return [_attr(k, v) for k, v in attrs.items()]


def _attr(key, value):
    if isinstance(value, bool):
        return {'key': key, 'value': {'boolValue': value}}
    if isinstance(value, int):
        return {'key': key, 'value': {'intValue': str(value)}}
    return {'key': key, 'value': {'stringValue': str(value)}}


def build_span(outcome, gate, status, start_ns, end_ns, synthetic=False):
    """The whole span, from the four allowed values plus timings. Nothing else goes in."""
    outcome = outcome if outcome in OUTCOMES else 'error'
    attrs = [_attr('http.route', '/api/ask'), _attr('http.request.method', 'POST'),
             _attr('http.response.status_code', int(status)), _attr('ro.outcome', outcome),
             _attr('ro.latency_ms', int((end_ns - start_ns) // 1_000_000))]
    if outcome == 'refused' and gate in GATES:
        attrs.append(_attr('ro.gate', gate))
    if synthetic:                           # the pipeline's own checks, so dashboards can leave them out
        attrs.append(_attr('ro.synthetic', True))
    return {'traceId': os.urandom(16).hex(), 'spanId': os.urandom(8).hex(),
            'name': 'POST /api/ask', 'kind': 2,
            'startTimeUnixNano': str(start_ns), 'endTimeUnixNano': str(end_ns),
            'attributes': attrs, 'status': {'code': 2 if status >= 500 else 0}}


def payload(spans):
    return {'resourceSpans': [{'resource': {'attributes': _resource()},
                               'scopeSpans': [{'scope': {'name': 'ro-cited.web', 'version': '1'},
                                               'spans': spans}]}]}


def record(outcome, gate, status, start_ns, end_ns=None, synthetic=False):
    """Never blocks, never raises."""
    if _q is None:
        return
    try:
        _q.put_nowait(build_span(outcome, gate, status, start_ns, end_ns or time.time_ns(), synthetic))
    except queue.Full:
        with _lock:
            counters['dropped'] += 1
    except Exception:
        with _lock:
            counters['dropped'] += 1


def _post(spans):
    req = urllib.request.Request(ENDPOINT + '/v1/traces', data=json.dumps(payload(spans)).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        if r.status >= 300:
            raise RuntimeError(f'HTTP {r.status}')


def _worker():
    fails, paused_until = 0, 0.0
    while True:
        span = _q.get()
        batch = [span]
        while len(batch) < 20:              # send what is already waiting in one request
            try:
                batch.append(_q.get_nowait())
            except queue.Empty:
                break
        if time.time() < paused_until:
            with _lock:
                counters['dropped'] += len(batch)
            continue
        try:
            _post(batch)
            fails = 0
            with _lock:
                counters['sent'] += len(batch)
        except Exception as e:            # one line, the exception type only: no payload, no URL
            fails += 1
            with _lock:
                counters['failed'] += len(batch)
            sys.stderr.write(f'otel export failed: {type(e).__name__}\n')
            if fails >= BREAK_AFTER:
                paused_until, fails = time.time() + BREAK_FOR_S, 0


def status():
    with _lock:
        return {'enabled': enabled(), **counters}


if _q is not None:
    threading.Thread(target=_worker, name='otel-export', daemon=True).start()
