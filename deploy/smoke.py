#!/usr/bin/env python3
"""
Post-deploy check. A deploy is not live until this passes against its URL.

A 200 proves nothing on its own (a proxy, a shell page or an error page can all
answer 200), so every check reads the CONTENT, and one deliberately wrong path
must FAIL, so a server that answers everything cannot read as healthy.

  python3 deploy/smoke.py https://example.run.app [--no-model]

Checks:
  1. /health answers ok and names the expected version (APP_VERSION, if set)
  2. / is the real page (its title), served as UTF-8
  3. a nonsense path returns 404, not 200
  4. an in-corpus question is ACCEPTED with at least one source and every
     attributed sentence above the grounding floor
  5. an out-of-corpus question is REFUSED at gate A
Checks 4 and 5 call the model; --no-model skips them (used by the monitor).

Exit 0 = every check passed. Exit 1 = a check failed. Exit 2 = could not reach it.
"""
import json, os, sys, urllib.error, urllib.request

ACCEPT_Q = 'Cand am nevoie de cod EORI pentru un colet?'
REFUSE_Q = 'Care este capitala Frantei?'


def fetch(url, data=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'} if data else {})
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, r.headers.get('Content-Type', ''), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Content-Type', ''), e.read().decode('utf-8', 'replace')


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: smoke.py BASE_URL [--no-model]')
    base = sys.argv[1].rstrip('/')
    want_version = os.environ.get('APP_VERSION')
    results = []

    def check(name, ok, detail=''):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f'  ({detail})' if detail else ''))

    try:
        code, _, body = fetch(base + '/health')   # /healthz is reserved by Cloud Run
    except Exception as e:                       # DNS, TLS, timeout: unknown, not "down"
        print(f'COULD NOT REACH {base}: {e!r}')
        return 2
    h = json.loads(body) if code == 200 else {}
    check('health ok', code == 200 and h.get('ok') is True, f'HTTP {code}')
    if want_version:
        check('health version', h.get('version') == want_version, f"{h.get('version')} vs {want_version}")

    code, ctype, body = fetch(base + '/')
    check('page is the real page', code == 200 and '<title>RO Cited Answers</title>' in body, f'HTTP {code}, {len(body)} chars')
    check('page served as UTF-8', 'charset=utf-8' in ctype.lower(), ctype)

    code, _, _ = fetch(base + '/zz-nonsense-path-control')
    check('nonsense path is 404', code == 404, f'HTTP {code}')

    if '--no-model' not in sys.argv:
        code, _, body = fetch(base + '/api/ask', json.dumps({'question': ACCEPT_Q}).encode(), timeout=120)
        d = json.loads(body) if code == 200 else {}
        grounded = all(a['overlap'] >= h.get('min_ground', 0.5) for a in d.get('attribution', []))
        check('in-corpus question accepted with sources',
              d.get('verdict') == 'ACCEPTAT' and d.get('sources') and d.get('attribution') and grounded,
              f"HTTP {code}, verdict {d.get('verdict')}, gate {d.get('gate')}")
        code, _, body = fetch(base + '/api/ask', json.dumps({'question': REFUSE_Q}).encode(), timeout=120)
        d = json.loads(body) if code == 200 else {}
        check('out-of-corpus question refused at gate A',
              d.get('verdict') == 'REFUZAT' and d.get('gate') == 'A_RETRIEVAL',
              f"HTTP {code}, verdict {d.get('verdict')}, gate {d.get('gate')}")

    passed = sum(results)
    print(f'{passed} of {len(results)} checks passed')
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
