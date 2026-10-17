#!/usr/bin/env bash
# Cloud Run deploy with a candidate revision, a check, and automatic rollback.
#
#   deploy/cloudrun.sh ensure-repo          create the Artifact Registry repo once
#   deploy/cloudrun.sh candidate IMAGE      new revision, NO traffic, tagged c-<short sha>
#   deploy/cloudrun.sh promote              send 100% to the candidate, remember the old one
#   deploy/cloudrun.sh rollback             send 100% back to the revision before the promote
#   deploy/cloudrun.sh url [candidate]      print the service (or candidate) URL
#   deploy/cloudrun.sh live-json DIR        write the live service and its serving revision as JSON (configure stage)
#   deploy/cloudrun.sh serving-image        print the image the serving revision runs
#
# The resource settings and fixed env vars come from deploy/service-config.json (configure stage):
# that file is the one place they live, and the config-drift job compares it with the live service.
#
# Auth: an access token from deploy/gcp_token.py in $GCP_TOKEN_FILE (no key file).
# The service scales to zero between visits: no idle compute, no idle cost.
set -euo pipefail

PROJECT="${GCP_PROJECT:-ro-cited-gitlab}"
REGION="${GCP_REGION:-europe-north1}"
SERVICE="${RUN_SERVICE:-ro-cited}"
REPO="${AR_REPO:-ro-cited}"
TOKEN_FILE="${GCP_TOKEN_FILE:-gcp-token.txt}"
STATE_FILE="${ROLLBACK_FILE:-previous-revision.txt}"

g() { gcloud --quiet --project="$PROJECT" --access-token-file="$TOKEN_FILE" "$@"; }

# The revision that serves production = the traffic entry with the highest percent. Never status.traffic[0]:
# a tagged candidate with 0% also has an entry there (rca-review on !7, 17.10.2026). One definition for all callers.
serving_rev() {
  g run services describe "$SERVICE" --region="$REGION" --format=json \
    | python3 -c 'import json,sys; t=json.load(sys.stdin)["status"]["traffic"]; print(max(t, key=lambda x: x.get("percent",0))["revisionName"])'
}

# Each commit gets its OWN candidate tag. A shared "candidate" tag let two main pipelines that ran
# at the same time validate each other's revision (pipeline 2954466465, 16.10.2026, caught by the
# version check and diagnosed by the rca-fix flow in issue #4).
export TAG="${RUN_TAG:-c-${CI_COMMIT_SHORT_SHA:-local}}"

case "${1:-}" in
  ensure-repo)
    g artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 \
      || g artifacts repositories create "$REPO" --location="$REGION" \
           --repository-format=docker --description="RO Cited Answers images"
    ;;
  candidate)
    image="${2:?image}"
    # Model key: passed as an env var from a masked CI variable, never in the image.
    # Cloud Run refuses --no-traffic when it CREATES a service, so the very first
    # deploy takes traffic directly; every later one waits for the check.
    traffic="--no-traffic"
    g run services describe "$SERVICE" --region="$REGION" >/dev/null 2>&1 || traffic=""
    here="$(dirname "$0")"
    cfg_flags="$(python3 "$here/service_config.py" flags)"
    cfg_vars="$(python3 "$here/service_config.py" fixed-vars)"
    # shellcheck disable=SC2086  # cfg_flags is a list of flags built from the config file
    g run deploy "$SERVICE" --image="$image" --region="$REGION" \
      $traffic --tag="$TAG" \
      $cfg_flags \
      --set-env-vars="APP_VERSION=${APP_VERSION:-dev},${cfg_vars},NEBIUS_API_KEY=${NEBIUS_API_KEY:?NEBIUS_API_KEY},OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT:-},GITLAB_PROJECT_ID=${CI_PROJECT_ID:-},GITLAB_PROJECT_NAME=${CI_PROJECT_NAME:-}" \
      --labels="managed-by=gitlab-ci,commit=${COMMIT_LABEL:-${CI_COMMIT_SHORT_SHA:-local}}"
    ;;
  promote)
    # Remember what was serving, so rollback has a target read from the LIVE
    # service at promote time, never a constant written months ago.
    serving_rev > "$STATE_FILE" || true
    echo "serving before promote: $(cat "$STATE_FILE")"
    g run services update-traffic "$SERVICE" --region="$REGION" --to-tags="$TAG=100"
    ;;
  serving-commit)
    # The short sha of the revision serving production, read from the commit label set at deploy.
    rev=$(serving_rev)
    g run revisions describe "$rev" --region="$REGION" --format='value(metadata.labels.commit)'
    ;;
  live-json)
    # The configure stage reads production from here: the service object, and the revision serving traffic.
    out="${2:?dir}"; mkdir -p "$out"
    g run services describe "$SERVICE" --region="$REGION" --format=json > "$out/service.json"
    rev=$(python3 -c 'import json,sys; t=json.load(open(sys.argv[1]))["status"]["traffic"]; print(max(t, key=lambda x: x.get("percent",0))["revisionName"])' "$out/service.json")  # same rule as serving_rev
    g run revisions describe "$rev" --region="$REGION" --format=json > "$out/serving.json"
    echo "$rev" > "$out/serving-revision.txt"
    echo "read live: service $SERVICE, serving revision $rev"
    ;;
  serving-image)
    rev=$(serving_rev)
    g run revisions describe "$rev" --region="$REGION" --format='value(spec.containers[0].image)'
    ;;
  cleanup)
    # Best effort, run only AFTER the production check passed: remove the candidate tags of commits
    # that are ANCESTORS of this one (never a newer commit's tag, which may be under validation),
    # plus the legacy shared "candidate" tag. Any failure here is logged and ignored.
    tags=$(g run services describe "$SERVICE" --region="$REGION" --format=json 2>/dev/null \
      | python3 -c 'import json,sys; t=json.load(sys.stdin)["status"].get("traffic",[]); print(" ".join(sorted({x["tag"] for x in t if x.get("tag")})))' 2>/dev/null) || tags=""
    old=""
    for t in $tags; do
      [ "$t" = "$TAG" ] && continue
      if [ "$t" = candidate ]; then old="$old,$t"; continue; fi
      case "$t" in c-*) ;; *) continue ;; esac
      if git merge-base --is-ancestor "${t#c-}" HEAD 2>/dev/null; then old="$old,$t"; fi
    done
    old="${old#,}"
    if [ -n "$old" ]; then
      g run services update-traffic "$SERVICE" --region="$REGION" --remove-tags="$old" \
        && echo "removed older candidate tags: $old" || echo "tag cleanup failed (ignored): $old"
    else
      echo "no older candidate tags to remove"
    fi
    ;;
  rollback)
    prev="$(cat "$STATE_FILE" 2>/dev/null || true)"
    if [ -z "$prev" ]; then
      echo "no previous revision recorded: first deploy, nothing to roll back to" >&2
      exit 3
    fi
    g run services update-traffic "$SERVICE" --region="$REGION" --to-revisions="$prev=100"
    echo "rolled back to $prev"
    ;;
  url)
    if [ "${2:-}" = candidate ]; then
      g run services describe "$SERVICE" --region="$REGION" --format=json \
        | python3 -c 'import json,sys,os; t=json.load(sys.stdin)["status"]["traffic"]; print(next(x["url"] for x in t if x.get("tag")==os.environ["TAG"]))'
    else
      g run services describe "$SERVICE" --region="$REGION" --format='value(status.url)'
    fi
    ;;
  *)
    sed -n '2,12p' "$0"; exit 2 ;;
esac
