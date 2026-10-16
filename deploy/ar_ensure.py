#!/usr/bin/env python3
"""
Make sure the Artifact Registry Docker repository exists (create it once).

  python3 deploy/ar_ensure.py TOKEN_FILE

Exit 0 when it exists or was created. Anything else exits non-zero with
Google's message, because a push into a missing repository fails later with a
much less readable error.
"""
import json, os, sys, urllib.error, urllib.request

PROJECT = os.environ.get('GCP_PROJECT', 'ro-cited-gitlab')
REGION = os.environ.get('GCP_REGION', 'europe-north1')
REPO = os.environ.get('AR_REPO', 'ro-cited')
API = f'https://artifactregistry.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/repositories'


def call(url, token, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': 'Bearer ' + token,
                                          'Content-Type': 'application/json'})
    try:
        return urllib.request.urlopen(req, timeout=30).status, ''
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def main():
    token = open(sys.argv[1]).read().strip()
    code, msg = call(f'{API}/{REPO}', token)
    if code == 200:
        print(f'repository {REPO} exists in {REGION}')
        return 0
    if code != 404:
        sys.exit(f'could not read the repository: HTTP {code} {msg}')
    code, msg = call(f'{API}?repositoryId={REPO}', token,
                     {'format': 'DOCKER', 'description': 'RO Cited Answers images'})
    if code not in (200, 409):
        sys.exit(f'could not create the repository: HTTP {code} {msg}')
    print(f'repository {REPO} created in {REGION}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
