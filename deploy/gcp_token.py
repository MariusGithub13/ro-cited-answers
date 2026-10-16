#!/usr/bin/env python3
"""
Turn the GitLab CI identity token into a short-lived Google Cloud access token.

No service account key exists anywhere: the organisation blocks key creation, and
that is the right default. Instead Google trusts gitlab.com as an identity
provider (Workload Identity Federation):

  1. GitLab signs a JWT for this job (id_tokens: GCP_ID_TOKEN in .gitlab-ci.yml).
  2. Google STS checks it against the pool's provider and its attribute condition
     and returns a federated token.
  3. IAM Credentials exchanges that for a one-hour token of the deploy account.

Standard library only, so it runs in any image that has Python.

  python3 deploy/gcp_token.py > token.txt    # prints the access token
"""
import json, os, sys, urllib.parse, urllib.request

PROJECT_NUMBER = os.environ.get('GCP_PROJECT_NUMBER', '210002791432')
POOL = os.environ.get('GCP_WIF_POOL', 'gitlab-pool')
PROVIDER = os.environ.get('GCP_WIF_PROVIDER', 'gitlab')
SA = os.environ.get('GCP_SERVICE_ACCOUNT', 'gitlab-deployer@ro-cited-gitlab.iam.gserviceaccount.com')
SCOPE = 'https://www.googleapis.com/auth/cloud-platform'
AUDIENCE = (f'//iam.googleapis.com/projects/{PROJECT_NUMBER}/locations/global/'
            f'workloadIdentityPools/{POOL}/providers/{PROVIDER}')


def _post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        # The body names the failing condition; it carries no secret.
        sys.exit(f'{url} -> HTTP {e.code}: {e.read().decode()[:400]}')


def main():
    jwt = os.environ.get('GCP_ID_TOKEN')
    if not jwt:
        sys.exit('GCP_ID_TOKEN is not set: the job needs id_tokens: GCP_ID_TOKEN')
    sts = _post('https://sts.googleapis.com/v1/token', urllib.parse.urlencode({
        'grant_type': 'urn:ietf:params:oauth:grant-type:token-exchange',
        'audience': AUDIENCE,
        'scope': SCOPE,
        'requested_token_type': 'urn:ietf:params:oauth:token-type:access_token',
        'subject_token_type': 'urn:ietf:params:oauth:token-type:jwt',
        'subject_token': jwt,
    }).encode(), {'Content-Type': 'application/x-www-form-urlencoded'})
    sa = _post(f'https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{SA}:generateAccessToken',
               json.dumps({'scope': [SCOPE], 'lifetime': '3600s'}).encode(),
               {'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + sts['access_token']})
    sys.stdout.write(sa['accessToken'])


if __name__ == '__main__':
    main()
