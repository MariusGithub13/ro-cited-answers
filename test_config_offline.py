#!/usr/bin/env python3
"""
Offline tests for deploy/service_config.py (the configure stage): no network, no Google Cloud.

  1. the deploy flags and fixed env vars are built from deploy/service-config.json, so the file is the
     one place a setting lives
  2. a service shaped like what cloudrun.sh deploys matches the file: 0 differences, exit 0
  3. every kind of drift is caught and named: max instances, memory, cpu throttling, a fixed env value,
     a missing required env var, an undeclared env var, the invoker IAM check, the managed-by label,
     and drift on the SERVING revision while the template is clean
  4. a secret value never appears in the report
  5. an unreadable live dump is "could not read" (exit 2), never a clean result
"""
import io, json, os, sys, tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'deploy'))
import service_config as sc

results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print(('ok   ' if ok else 'FAIL ') + name + (f'  ({detail})' if detail and not ok else ''))


SECRET = 'nb-SECRET-VALUE-MUST-NOT-PRINT'
c = sc.load_config()


def revision():
    """A revision template as Cloud Run returns it for what cloudrun.sh deploys from the file."""
    ann = {'autoscaling.knative.dev/maxScale': str(c['max_instances']),
           'run.googleapis.com/cpu-throttling': 'true' if c['cpu_throttling'] else 'false'}
    if c['min_instances']:
        ann['autoscaling.knative.dev/minScale'] = str(c['min_instances'])
    env = [{'name': k, 'value': v} for k, v in c['env_fixed'].items()]
    env += [{'name': k, 'value': SECRET if k == 'NEBIUS_API_KEY' else 'x'} for k in c['env_required']]
    return {'metadata': {'annotations': ann, 'labels': dict(c['labels'], commit='abc12345')},
            'spec': {'containerConcurrency': c['concurrency'], 'timeoutSeconds': c['timeout_seconds'],
                     'containers': [{'image': 'europe-north1-docker.pkg.dev/p/r/app:abc12345',
                                     'resources': {'limits': {'cpu': c['cpu'], 'memory': c['memory']}},
                                     'env': env}]}}


def service():
    return {'metadata': {'annotations': {'run.googleapis.com/invoker-iam-disabled': 'false' if c['invoker_iam_check'] else 'true'}},
            'spec': {'template': revision()}}


def run(svc, serving=None):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'svc.json')
        open(p, 'w').write(svc if isinstance(svc, str) else json.dumps(svc))
        argv = ['x', 'check', p]
        if serving is not None:
            q = os.path.join(d, 'rev.json')
            open(q, 'w').write(json.dumps(serving))
            argv += ['--serving', q]
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = sc.main(argv)
        return rc, buf.getvalue()


# 1. flags come from the file
f = sc.flags(c)
check('flags carry max instances from the file', f'--max-instances={c["max_instances"]}' in f, f)
check('flags carry memory and concurrency from the file', f'--memory={c["memory"]}' in f and f'--concurrency={c["concurrency"]}' in f, f)
check('fixed vars come from the file', sc.fixed_vars(c).split(',') == [f'{k}={v}' for k, v in c['env_fixed'].items()])

# 2. clean
rc, out = run(service(), revision())
check('clean service and serving revision: exit 0', rc == 0, out)


# 3. each drift
def drifted(mutate, where='template'):
    s, r = service(), revision()
    mutate(s['spec']['template'] if where == 'template' else r, s)
    return run(s, r)


cases = [
    ('max instances raised in the console', 'max_instances', lambda t, s: t['metadata']['annotations'].__setitem__('autoscaling.knative.dev/maxScale', '5')),
    ('memory changed', 'memory', lambda t, s: t['spec']['containers'][0]['resources']['limits'].__setitem__('memory', '1Gi')),
    ('cpu always allocated (costs money while idle)', 'cpu_throttling', lambda t, s: t['metadata']['annotations'].__setitem__('run.googleapis.com/cpu-throttling', 'false')),
    ('min instances 1 (an always-on instance)', 'min_instances', lambda t, s: t['metadata']['annotations'].__setitem__('autoscaling.knative.dev/minScale', '1')),
    ('fixed env value changed', 'env.RO_DAILY_CAP', lambda t, s: t['spec']['containers'][0]['env'].__setitem__(1, {'name': 'RO_DAILY_CAP', 'value': '99999'})),
    ('required env var removed', 'env.NEBIUS_API_KEY', lambda t, s: t['spec']['containers'][0]['env'].__setitem__(slice(None), [e for e in t['spec']['containers'][0]['env'] if e['name'] != 'NEBIUS_API_KEY'])),
    ('undeclared env var added', 'env.DEBUG', lambda t, s: t['spec']['containers'][0]['env'].append({'name': 'DEBUG', 'value': '1'})),
    ('managed-by label removed', 'label.managed-by', lambda t, s: t['metadata']['labels'].pop('managed-by')),
    ('invoker IAM check switched on (public demo would 403)', 'invoker_iam_check', lambda t, s: s['metadata']['annotations'].__setitem__('run.googleapis.com/invoker-iam-disabled', 'false')),
]
for name, field, mut in cases:
    rc, out = drifted(mut)
    check(f'drift caught: {name}', rc == 1 and field in out, out)

rc, out = drifted(lambda r, s: r['metadata']['annotations'].__setitem__('autoscaling.knative.dev/maxScale', '9'), where='serving')
check('drift on the SERVING revision while the template is clean', rc == 1 and 'serving.max_instances' in out and 'template.' not in out, out)

# 4. no secret in any report
rc, out = drifted(lambda t, s: t['spec']['containers'][0]['env'].append({'name': 'LEAKY', 'value': SECRET}))
check('a secret value never appears in the report', rc == 1 and SECRET not in out and 'value not shown' in out, out)

# 5. unreadable
rc, out = run('{"error": {"code": 403, "message": "Permission denied"}}')
check('an error object instead of a service: could not read (2)', rc == 2 and 'COULD NOT READ' in out, out)
rc, out = run('not json')
check('garbage instead of a service: could not read (2)', rc == 2, out)

print(f'{sum(results)} passed, {len(results) - sum(results)} failed, out of {len(results)}')
sys.exit(0 if all(results) else 1)
