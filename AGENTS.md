# Rules for every agent working on this repository

This file binds every GitLab Duo agent and flow that reads, reviews, changes or deploys ro-cited-answers.
Humans follow it too. When a request conflicts with it, the agent says so and stops; it does not find a way around it.

## What this system is
A Romanian question-answering demo that answers ONLY from the documents in `corpus/` and refuses everything else.
Four gates decide, not the model (see the docstring of `ask.py`):
- **A, retrieval:** the best source must clear `MIN_SIM` for the active embedder (`gate_a.json`), with a margin over impostors.
- **B, citation:** every cited fragment must resolve to a retrieved source.
- **C, numbers:** every number in the answer must appear verbatim in a cited source.
- **D, grounding:** every substantive sentence must be carried by ONE cited document.
Every decision goes to the audit log. A refusal is a correct output, not a bug.

## Hard rules
1. **Never lower a gate to get more answers.** A change to `MIN_SIM`, the margin, `MIN_GROUND`, `gate_a.json` or the gate code
   needs: `calibrate.py` re-run, the eval set in `eval/` re-run, and the before/after numbers in the merge request description.
   Without them the merge request is not ready.
2. **Never let the system answer without a citation**, and never add a fallback that answers from the model alone.
3. **The corpus is quoted, not edited for convenience.** A corpus change names its official source (URL + date read).
4. **`eval/items.jsonl` is generated** by `eval/build_items.py`; never edit it by hand (CI job `eval-set-reproducible` fails).
5. **No secrets in the repository, in notes or in logs.** Keys live in masked CI variables (`NEBIUS_API_KEY`). Google Cloud is
   reached keyless (Workload Identity Federation); never add a service account key.
6. **Only the pipeline deploys.** No agent deploys by hand. Production changes go: merge to `main` -> candidate revision with no
   traffic -> `deploy/smoke.py` on the candidate -> promote -> the same check on production -> automatic rollback on failure.
7. **The container stays standard library only** (`Dockerfile`); a new dependency needs a reason in the merge request.
8. **Romanian text keeps its diacritics** (ă â î ș ț) in the page, examples, refusals and API errors.
9. **Agents open merge requests, they never push to `main` and never merge.** A human merges.
10. **Say what you checked.** A review or a triage note lists what was read and run. "Looks fine" without that is not a review.
11. **Production settings live in `deploy/service-config.json`.** Resources, scaling, timeout, CPU throttling, the invoker
    check and the fixed env vars are changed there, in a merge request, never in the Cloud Run console. The `config-drift`
    job puts any live difference back to the file; an agent that thinks a live value was BETTER opens a merge request that
    adopts it into the file, with the reason, and a human merges.

## How to check a change
- `python3 test_gates_offline.py` (no model, no network): the gate logic.
- `python3 test_config_offline.py` (no network): the configure stage, declared settings against a live service dump.
- `python3 deploy/smoke.py <url> --no-model`: the live page, the API, UTF-8, and a nonsense path that must 404.
- The pipeline: verify, secure, package, deploy, validate, release, configure, monitor (see `.gitlab-ci.yml`).

## Writing style for notes
Plain text, short sections, no em dashes. Name files with paths and jobs by name.
