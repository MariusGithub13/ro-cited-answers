#!/usr/bin/env python3
"""Configure stage: the declared Cloud Run settings (deploy/service-config.json) against the live service.

  service_config.py flags                   gcloud flags for `run deploy`, built from the file
  service_config.py fixed-vars              the fixed env vars, KEY=VALUE,... built from the file
  service_config.py check LIVE.json         compare a `gcloud run services describe --format=json` dump
                                            (and, with --serving REV.json, the revision that serves traffic)

check exits 0 = matches, 1 = DRIFT (each field named), 2 = could not read the live state.
Secret values are never printed: env vars outside env_fixed are compared by NAME only.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.environ.get('SERVICE_CONFIG', os.path.join(HERE, 'service-config.json'))
FIELDS = ('cpu', 'memory', 'concurrency', 'min_instances', 'max_instances', 'timeout_seconds', 'cpu_throttling')


def load_config():
    return json.load(open(CONFIG, encoding='utf-8'))


def flags(c):
    return ' '.join([
        f"--cpu={c['cpu']}", f"--memory={c['memory']}", f"--concurrency={c['concurrency']}",
        f"--min-instances={c['min_instances']}", f"--max-instances={c['max_instances']}",
        f"--timeout={c['timeout_seconds']}",
        '--cpu-throttling' if c['cpu_throttling'] else '--no-cpu-throttling',
        '--invoker-iam-check' if c['invoker_iam_check'] else '--no-invoker-iam-check',
    ])


def fixed_vars(c):
    return ','.join(f'{k}={v}' for k, v in c['env_fixed'].items())


def template_fields(obj):
    """The settings of one revision template (a service's spec.template, or a revision object)."""
    meta = obj.get('metadata') or {}
    spec = obj.get('spec') or {}
    ann = meta.get('annotations') or {}
    containers = spec.get('containers') or []
    if not containers:
        raise ValueError('no container in the template')
    ctr = containers[0]
    limits = (ctr.get('resources') or {}).get('limits') or {}
    return {
        'cpu': str(limits.get('cpu', '')),
        'memory': str(limits.get('memory', '')),
        'concurrency': int(spec.get('containerConcurrency', 80)),
        # Knative leaves minScale out when it is 0.
        'min_instances': int(ann.get('autoscaling.knative.dev/minScale', 0)),
        'max_instances': int(ann.get('autoscaling.knative.dev/maxScale', 100)),
        'timeout_seconds': int(spec.get('timeoutSeconds', 300)),
        'cpu_throttling': str(ann.get('run.googleapis.com/cpu-throttling', 'true')).lower() == 'true',
        'vars': {e['name']: e.get('value') for e in ctr.get('env') or [] if 'name' in e},
        'labels': meta.get('labels') or {},
    }


def compare(c, live, where):
    """(field, declared, live) for every difference. Values outside env_fixed are never shown."""
    out = [(f'{where}.{k}', c[k], live[k]) for k in FIELDS if live[k] != c[k]]
    v = live['vars']
    for k, want in c['env_fixed'].items():
        if v.get(k) != want:
            out.append((f'{where}.env.{k}', want, v.get(k, '<missing>')))
    for k in c['env_required']:
        if not v.get(k):
            out.append((f'{where}.env.{k}', '<set>', '<missing or empty>'))
    for k in sorted(set(v) - set(c['env_fixed']) - set(c['env_required'])):
        out.append((f'{where}.env.{k}', '<not declared>', '<present, value not shown>'))
    for k, want in c['labels'].items():
        if live['labels'].get(k) != want:
            out.append((f'{where}.label.{k}', want, live['labels'].get(k, '<missing>')))
    return out


def check(c, service, serving=None):
    drift = []
    ann = (service.get('metadata') or {}).get('annotations') or {}
    iam_check = str(ann.get('run.googleapis.com/invoker-iam-disabled', 'false')).lower() != 'true'
    if iam_check != c['invoker_iam_check']:
        drift.append(('service.invoker_iam_check', c['invoker_iam_check'], iam_check))
    drift += compare(c, template_fields(service['spec']['template']), 'template')
    if serving is not None:
        drift += compare(c, template_fields(serving), 'serving')
    return drift


def main(argv):
    if len(argv) < 2 or argv[1] not in ('flags', 'fixed-vars', 'check'):
        print(__doc__.strip())
        return 2
    c = load_config()
    if argv[1] == 'flags':
        print(flags(c))
        return 0
    if argv[1] == 'fixed-vars':
        print(fixed_vars(c))
        return 0
    try:
        service = json.load(open(argv[2], encoding='utf-8'))
        serving = None
        if '--serving' in argv:
            serving = json.load(open(argv[argv.index('--serving') + 1], encoding='utf-8'))
        drift = check(c, service, serving)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        print(f'COULD NOT READ the live state: {type(e).__name__}: {e}')
        return 2
    checked = 'service template' + (' and serving revision' if serving is not None else '')
    if not drift:
        print(f'config: the live {checked} matches deploy/service-config.json (0 differences)')
        return 0
    print(f'CONFIG DRIFT: {len(drift)} difference(s) between deploy/service-config.json and the live {checked}')
    print(f"{'field':<40} {'declared':<22} live")
    for f, want, got in drift:
        print(f'{f:<40} {str(want):<22} {got}')
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
