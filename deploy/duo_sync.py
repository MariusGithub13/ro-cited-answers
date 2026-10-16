#!/usr/bin/env python3
"""Apply the Duo flows in .gitlab/duo/ to the GitLab project: the repository is the source of truth.

For each flow in .gitlab/duo/flows.json: create it in the AI Catalog if missing, otherwise push the YAML from the repo
as a new patch version; then make sure it is enabled on the project with its triggers and conditions.
Token: GITLAB_TOKEN in the environment (never printed). --dry-run shows what would change.
"""
import json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DUO = os.path.join(HERE, '..', '.gitlab', 'duo')
DRY = '--dry-run' in sys.argv


def gql(query, variables=None):
    req = urllib.request.Request('https://gitlab.com/api/graphql',
        data=json.dumps({'query': query, 'variables': variables or {}}).encode(),
        headers={'Authorization': 'Bearer ' + os.environ['GITLAB_TOKEN'], 'Content-Type': 'application/json'})
    out = json.load(urllib.request.urlopen(req, timeout=60))
    if out.get('errors'):
        raise SystemExit(f"GraphQL error: {out['errors']}")
    return out['data']


def fail_on(payload, what):
    if payload.get('errors'):
        raise SystemExit(f"{what}: {payload['errors']}")


def main():
    manifest = json.load(open(os.path.join(DUO, 'flows.json')))
    proj = gql('query($p: ID!) { project(fullPath: $p) { id } }', {'p': manifest['project']})['project']
    if not proj:
        raise SystemExit(f"project not found or not visible: {manifest['project']}")
    pid = proj['id']
    items = gql('query($p: ID!) { project(fullPath: $p) { aiCatalogItems(itemTypes: [FLOW], first: 100) '
                '{ nodes { id name latestVersion { versionName ... on AiCatalogFlowVersion { definition } } } } } }', {'p': manifest['project']})['project']['aiCatalogItems']['nodes']
    by_name = {i['name']: i['id'] for i in items}
    current = {i['name']: (i.get('latestVersion') or {}) for i in items}
    for f in manifest['flows']:
        definition = open(os.path.join(DUO, 'flows', f['file']), encoding='utf-8').read()
        iid = by_name.get(f['name'])
        if iid is None:
            print(f"{f['name']}: create")
            if DRY:
                continue
            r = gql('mutation($in: AiCatalogFlowCreateInput!) { aiCatalogFlowCreate(input: $in) { errors item { id } } }',
                    {'in': {'projectId': pid, 'name': f['name'], 'description': f['description'], 'visibility': 'PRIVATE',
                            'release': True, 'definition': definition}})['aiCatalogFlowCreate']
            fail_on(r, f['name'])
            iid = r['item']['id']
        elif (current[f['name']].get('definition') or '').strip() == definition.strip():
            print(f"{f['name']}: unchanged, version {current[f['name']].get('versionName')} ({iid})")
        else:
            # A released version is frozen: the change goes in as a new released patch version.
            print(f"{f['name']}: new version from the repo ({iid}, was {current[f['name']].get('versionName')})")
            if not DRY:
                r = gql('mutation($in: AiCatalogFlowUpdateInput!) { aiCatalogFlowUpdate(input: $in) { errors } }',
                        {'in': {'id': iid, 'definition': definition, 'release': True,
                                'versionBump': 'PATCH'}})['aiCatalogFlowUpdate']
                fail_on(r, f['name'])
        consumer = None if DRY and iid is None else gql(
            'query($p: ID!, $i: AiCatalogItemID!) { project(fullPath: $p) { aiCatalogItemConsumerForItem(id: $i) { id } } }',
            {'p': manifest['project'], 'i': iid})['project']['aiCatalogItemConsumerForItem']
        if consumer:
            print(f"  enabled ({consumer['id']}), triggers {f['triggers']}")
            continue
        print(f"  enable with triggers {f['triggers']}")
        if DRY:
            continue
        inp = {'itemId': iid, 'target': {'projectId': pid}, 'triggerTypes': f['triggers']}
        if f.get('conditions'):
            inp['triggerConditions'] = f['conditions']
        r = gql('mutation($in: AiCatalogItemConsumerCreateInput!) { aiCatalogItemConsumerCreate(input: $in) '
                '{ errors itemConsumer { id } } }', {'in': inp})['aiCatalogItemConsumerCreate']
        fail_on(r, f['name'] + ' enable')
        print(f"  enabled ({r['itemConsumer']['id']})")


if __name__ == '__main__':
    main()
