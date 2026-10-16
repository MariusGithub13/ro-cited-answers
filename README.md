# Cited or refused

*(Romanian: „Răspunsuri citate sau refuzate". The prose here is English; the corpus,
the questions and the quoted model output stay in Romanian, because a Romanian-language
grounding demo is the whole point and the quotes are verbatim evidence.)*

A small, self-hosted Romanian question-answering demo that will not give you an
answer it cannot trace to a source document.

It runs two ways, with the same four gates in both:

- **Locally:** an open-weight model on Ollama, on a 4-core VPS in the EU, no
  external API, no key, no data leaving the machine.
- **Live demo:** https://ro-cited-210002791432.europe-north1.run.app , on Google
  Cloud Run, with an open-weight model (gemma-3-27b-it) and embedding model
  (Qwen3-Embedding-8B) behind an OpenAI-compatible API. Every answer still goes
  through the gates; the page shows the verdict, the gate that decided it and the
  source behind each sentence. Deployed only by the GitLab pipeline described in
  [The post-code pipeline](#the-post-code-pipeline-gitlab-added-16-october-2026).

## Why this exists

There is a good argument going on in Europe about sovereign AI: open weights,
open training data, national compute, models governed under national law. That
argument is worth winning.

But sovereignty decides **where the weights sit**. It decides nothing about
**whether a specific answer is true**. A model can be fully sovereign and
confidently wrong at the same time, and in regulated work, confidently wrong is
the failure that costs money.

This repository is a small, checkable demonstration of the other half: an answer
that cannot be traced to a source is refused before anyone reads it.

Here is the same 2B open model, on the same machine, minutes apart.

**Ungrounded**, asked what EORI means:

> Număr EORI (European Union Chamber of Commerce and Industry Number) este un cod
> unic de identificare...

That is invented. EORI is not a chamber of commerce number.

**Grounded through the gates below**, same question:

> EORI este Economic Operators Registration and Identification, care reprezinta
> inregistrarea si identificarea operatorilor economici. Numărul EORI este
> atribuit gratuit si termenul mediu de solutionare este de 5 zile, iar termenul
> maxim este de 30 de zile.
>
> **SURSE:** `[eori-structura]` https://www.customs.ro/e-customs/eori (verificat 2026-07-23)

Same weights. Same hardware. The sovereignty of the model decided nothing. The
gates decided everything.

## The four gates

An answer must clear all four, or it is refused and the refusal is logged.

| | Gate | What it checks |
|---|---|---|
| A | Retrieval | The best-matching document must clear a similarity threshold. |
| B | Citation | Every source the model points at must resolve to a document actually retrieved. |
| C | Numbers | Every number in the answer must appear verbatim in a cited source. |
| D | Grounding | Every substantive sentence must be attributable to one cited document, and the citation list is rebuilt from what was actually used. |

Gate D is the load-bearing one, because it is the only gate that does not depend
on the model cooperating with an instruction. That matters on a 2B model, which
cannot reliably obey a citation format.

## What we measured, and what it broke

Three findings from building this, all reproducible from the code here.

**1. Retrieval similarity cannot separate in-corpus from out-of-corpus questions.**

`calibrate.py` scores 7 legitimate questions and 7 impostors against the corpus.
The two populations **overlap**:

```
lowest legitimate question : 0.697   "Cand am nevoie de cod EORI pentru un colet?"
highest impostor question  : 0.773   "Ce documente imi trebuie pentru un permis de conducere?"
separation margin          : -0.076
```

A question about driving licences scores higher against a customs corpus than
every genuine customs question does. So **no single confidence threshold can
split them**, and any design that leans on a retrieval score as its safety
mechanism is leaning on nothing. The threshold in `ask.py` is set from this
measurement, and gate A is deliberately not load-bearing.

**2. A small model will not echo a string source id.**

Asked to cite `posta-returnare`, the model answered correctly and signed it
`SURSE: 1, 2`. A gate demanding ids threw away two correct answers. Fragments are
now numbered, and the number is mapped back to the real document in code, where
it cannot be got wrong.

**3. Once citing is cheap, models pad their citations.**

With numbered fragments, the model answered a parcel-return question correctly
from `posta-returnare` and then also cited `eori-art18`, which has nothing to do
with the question. The answer was trustworthy and the citation list was noise,
which is exactly backwards for a system selling traceability.

So citations are no longer taken on the model's word. Each sentence is attributed
to its best-matching cited document, and the printed source list is rebuilt from
the documents that actually carried a sentence. Padding is stripped and logged.

## Running it

Requires [Ollama](https://ollama.com) with a chat model and an embedding model, and Python 3.11 or newer
(`ask.py` uses `datetime.UTC`; checked with 3.13). No other Python packages.

```bash
ollama pull gemma2:2b
ollama pull nomic-embed-text

python3 ask.py "Ce inseamna EORI si cat costa obtinerea lui?"
python3 ask.py "Care este capitala Frantei?"      # refused, gate A

python3 calibrate.py     # reproduce the overlap measurement
python3 test_gates.py    # 4 cases: 2 must be refused, 2 must be answered
                         # 27 Jul 2026: 4 of 4. 5 Oct 2026: 3 of 4, see 'Honest limitations'
python3 test_gates_offline.py   # gates B, C, D on canned model output; no Ollama; this is what CI runs
```

If Ollama is not running on `127.0.0.1:11434`, every script above except `test_gates_offline.py` stops with a
`Connection refused` traceback. What ran and what did not on 15 October 2026, on a machine without Ollama,
is in [docs/README-PROOF-2026-10-15.md](docs/README-PROOF-2026-10-15.md).

The hosted backend is one environment variable away, with a key for any
OpenAI-compatible endpoint (Nebius Token Factory by default):

```bash
RO_BACKEND=openai NEBIUS_API_KEY=... python3 ask.py "Cand am nevoie de cod EORI?"
RO_BACKEND=openai NEBIUS_API_KEY=... PORT=8080 python3 web/app.py   # the live page locally
```

Gate A is calibrated per embedding model: `calibrate.py --write` stores the
threshold in `gate_a.json` (Qwen3-Embedding-8B: lowest legitimate question 0.588,
highest impostor 0.426, threshold 0.507, a clean separation that nomic-embed-text
never had). Each embedding model keeps its own vector cache.

The model is pluggable on purpose, because the model is not the differentiator:

```bash
RO_MODEL=llama3.2 python3 ask.py "..."
```

Every decision, accepted or refused, is appended to `audit.jsonl` with the
retrieval scores, the gate that fired, and the per-sentence attribution. A
refusal you cannot reconstruct later is just a different kind of unverifiable
output.

## The post-code pipeline (GitLab, added 16 October 2026)

Everything after the code is written is automated in [`.gitlab-ci.yml`](.gitlab-ci.yml).

The project lives in the GitLab Transcend hackathon workspace:
https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43427415/ro-cited-answers
(pipelines: `/-/pipelines`). The GitHub repository is the original MIT project it started from:
https://github.com/MariusGithub13/ro-cited-answers
A push to `main` goes to production with no human step, and production is only
changed when a check on the LIVE service says the new version works.

| Stage | What runs | What stops the release |
|---|---|---|
| verify | the gate tests on canned model output; the eval items rebuilt from their sources and diffed; the app boots and passes the content checks | any test failing, or an eval file that no longer matches its sources |
| secure | GitLab SAST and secret detection | the job failing |
| package | one image per commit, pushed to the GitLab registry and to Artifact Registry; GitLab container scanning | a failed build or scan job |
| deploy | a new Cloud Run revision tagged `candidate`, receiving **no traffic** | the deploy failing |
| validate | [`deploy/smoke.py`](deploy/smoke.py) against the candidate URL: the version, the real page, UTF-8, a nonsense path that must be 404, a real question that must be ACCEPTED with sources, an impostor that must be REFUSED at gate A | any of the 7 checks |
| release | 100% of traffic to the candidate, then the same check on production; **if it fails, traffic goes back** to the revision recorded at promote time ([`deploy/cloudrun.sh`](deploy/cloudrun.sh) `rollback`); then a GitLab release naming the commit | the production check |
| monitor | a pipeline schedule every 6 hours re-checks production (no model call, so it costs nothing) | a failed check fails the pipeline, which notifies the owner |

Design choices worth checking:

- **No service account key exists.** The Google Cloud organisation blocks key
  creation, and that is the right default. GitLab signs a short-lived identity
  token for each job, Google trusts gitlab.com through Workload Identity
  Federation, and [`deploy/gcp_token.py`](deploy/gcp_token.py) exchanges it for a
  one-hour token of the deploy account. Only pipelines of this project's owner or
  namespace can use it.
- **A 200 is never a pass.** Every check reads the content, and a deliberately
  wrong path must fail, so a proxy or an error page that answers everything
  cannot look healthy. The checks have three outcomes: pass, fail, and could not
  reach (exit 2), which is never reported as "down".
- **The rollback target is read from the live service at promote time**, never a
  constant, so it cannot point at a revision that stopped existing months ago.
- **Scale to zero.** The service runs no instance between visits (cold start
  about 10 seconds), with a daily question cap and a per-address rate limit,
  because the model is a paid API.

What the first runs caught, in the open: Cloud Run reserves URL paths ending in
`z`, so `/healthz` never reached the app and the candidate check stopped the
release (now `/health`); and Artifact Registry creates a repository a few
seconds after confirming it, so the first image push failed until the script
waited for it to be readable. Both are in the pipeline history.

What is new for this repository on or after 5 October 2026: the hosted backend,
the per-model gate A calibration, the live page and API (`web/`), the Dockerfile,
`deploy/` and `.gitlab-ci.yml`. The gates and the corpus predate it.

## The agents after the code (GitLab Duo, added 16 October 2026)

The pipeline proves a change; the agents run the work around it. Five custom Duo flows, one per part of the
lifecycle, each with its own service account, all bound by [AGENTS.md](AGENTS.md): never lower a gate to get more
answers, never answer without a citation, agents open merge requests but never push to `main`, merge or deploy.

| Flow | Starts when | What it does |
|---|---|---|
| `rca-plan` | an issue is created, or it is mentioned | reads the code it concerns and posts a scoped plan: files, whether a gate or the corpus changes (then calibration and the eval must be re-run), tests, stages, risk |
| `rca-review` | it is set as reviewer, or a merge request is marked ready | gate-aware review: can this change make the system answer something it used to refuse? |
| `rca-fix` | a pipeline fails (not a scheduled one) | reads the failing jobs, opens a fix merge request on `duo-fix/<pipeline>`; never touches a threshold to make a test pass |
| `rca-secure` | it is assigned or mentioned on an issue | triages SAST, secret and container findings by reachability in this code; dismisses nothing itself |
| `rca-release` | a pipeline on `main` passes or fails | after a deploy: commits, scan results, and its own check of the live service (when its sandbox allows it), posted to the Production log issue; a failed promote or monitor run becomes an incident issue |

The flows are code: [`.gitlab/duo/flows/`](.gitlab/duo/flows) holds the YAML, [`flows.json`](.gitlab/duo/flows.json)
their triggers and conditions, and [`deploy/duo_sync.py`](deploy/duo_sync.py) applies them through the GitLab API
(unchanged flows are skipped; a changed one becomes a new released version). Per-path review rules live in
[`.gitlab/duo/mr-review-instructions.yaml`](.gitlab/duo/mr-review-instructions.yaml). The flow sandbox may reach only the
two production hostnames ([`.gitlab/duo/agent-config.yml`](.gitlab/duo/agent-config.yml)).

What the first runs did: `rca-plan` turned issue #1 into a plan in about two minutes without being asked; `rca-release`
started one second after the v3 deploy passed, wrote the release summary, and reported that it could NOT reach production
from its sandbox (the proxy answered 403 to CONNECT: the sandbox blocks outbound traffic by default, and the allowlist above
was added after that run, because of it) instead of claiming it had. That second behaviour is the one this project is about.

## The corpus

Five documents on Romanian customs and EORI procedure, drawn from public
information published by Poșta Română and the Romanian Customs Authority, each
carrying its source URL and the date it was checked. They were assembled while
working an actual parcel stuck in customs at BSI București, which is why the
questions in the tests are the ones a real person actually needed answered.

Nothing here is legal advice. The corpus is a demonstration fixture, and the
`verificat` date on each document is the date it was last checked against the
source, not a guarantee it is current.

## eval/: the same questions with and without the gates (added 5 October 2026)

`eval/` is a second, harder test, built from the original text of Romanian Law 544/2001 on access to
public information (fetched from legislatie.just.ro; the 2001 original, not the consolidated law, so it
tests grounding in the given text, never legal truth).

It holds 12 question PAIRS, 24 items:

- **answerable**: the article that holds the answer is in the context; the model must answer.
- **abstain**: the same context with that one paragraph cut out; the only right reply is "NU REIESE DIN TEXT".

The idea of pairing an answerable item with its evidence-removed twin comes from Aleph Alpha's Kolibri
release (October 2026). `build_items.py` refuses to build a pair whose answer is missing from the
answerable context or still present in the abstain one; on the first build it caught three such leaks.

```bash
cd eval
python3 build_items.py                    # rebuild and check every pair
python3 run_eval.py gemma2:2b             # bare model, OpenAI-compatible API (Ollama by default)
python3 run_eval.py --gated gemma2:2b     # same items through gates B, C and D of ask.py
python3 run_eval.py --base http://host:8000/v1 SomeModel   # any vLLM / OpenAI-compatible server
```

Scoring is mechanical: an abstain item counts only if the reply says "NU REIESE DIN TEXT", anything else
is a hallucination; an answerable item counts if it matches the expected answer (`15 zile` never counts as
`5 zile`). A failed call is reported as ERROR and counted as neither. Results land in `eval/results/`, one
file per model and mode, and are published only after they have been read.

### First results, 5 October 2026 (gemma2:2b, local CPU, temperature 0)

| | bare model | through gates B, C, D |
|---|---|---|
| answer present: correct | 12 of 12 | 12 of 12 |
| answer removed: said "NU REIESE DIN TEXT" | 8 of 12 | 6 of 12 |
| answer removed: invented an answer | 4 | 6 |

Files: `eval/results/2026-10-05-bare-gemma2-2b.json`, `eval/results/2026-10-05-gated-gemma2-2b.json`, and
`eval/results/gated-audit.jsonl` (every gate decision).

### Hosted models, 15 October 2026 (bare, through a batch API, effort low)

The same 24 items, the same system prompt and the same mechanical scoring (`eval/run_claude_batch.py` imports them from
`run_eval.py`), sent in one batch to four hosted models. Bare only: the gates run on the local model and were not re-implemented
for these.

| model | answer present: correct | answer removed: said "NU REIESE DIN TEXT" | answer removed: invented |
|---|---|---|---|
| claude-haiku-5-5 | 11 of 12 | 12 of 12 | 0 |
| claude-sonnet-5-5 | 12 of 12 | 12 of 12 | 0 |
| claude-opus-5-5 | 12 of 12 | 12 of 12 | 0 |
| claude-fable-5-1 | 12 of 12 | 12 of 12 | 0 |

Files: `eval/results/2026-10-15-bare-claude-*.json`. On these twelve pairs the hosted models abstain every time the
evidence is removed; the 2B local model invented four answers. Twelve pairs is a small set, and the point of the project is
what runs on an institution's own machine, so this row is a reference line, not the result.

**The gates caught none of the invented answers.** Gates B, C and D refused 0 of 24 items; every refusal in the
gated run is the model's own "NU_STIU" (`eval/results/gated-audit.jsonl`: 18 accepted, 6 abstained, 0 refused by a
gate). This is the limitation named below as provenance, not relevance. The invented answers are built from real words and real numbers of the
remaining text: asked for a deadline whose paragraph was cut, the model answers with a deadline from the
neighbouring paragraph. Every number is in the source and every sentence overlaps it lexically, so gates that check
"is this in the source" pass it. They cannot see "does this answer the question that was asked".

Two caveats, stated so the numbers are not over-read. The gated mode also uses `ask.py`'s own prompt, which is
worded differently from the bare prompt, so the 4 vs 6 difference mixes prompt and gates; what is clean is that the
gates themselves fired on nothing. And 12 pairs on one model is a small sample.

The first gated run on 5 October refused everything, correct answers included: a harness bug handed the two
articles of each context to the gates as ONE fragment, so the model's honest "SURSE: 1, 2" read as an invented source.
Fixed in `run_eval.py` (each article is now its own fragment); the numbers above are from the corrected run.

### Who does what: the relations set, 15 October 2026 (gemma2:2b, local CPU)

The pairs above ask whether a model invents an answer when the evidence is gone. This set asks a narrower question:
when the deadline is right, is it attached to the right PARTY and the right ACTION? `eval/build_relations.py` builds 14
groups from Legea 544/2001, Legea 190/2018 and OSGG 600/2018, each on ONE fixed passage of the original text, with three
proposed answers:

- **valid**: a paraphrase that keeps who, what and the deadline;
- **wrong actor**: the same deadline and action, given to another party named in the law;
- **wrong action**: the same party and deadline, attached to another action.

Holding the passage fixed means retrieval plays no part: the only thing that changes inside a group is the relation.
The model sees the passage, the question and one proposed answer, and must reply `VERDICT: ACCEPT` or `VERDICT: RESPINS`.
Two rates, each over its own denominator, because one number would hide a checker that refuses everything:

| | wrong answers accepted | of which wrong actor | of which wrong action | correct answers refused |
|---|---|---|---|---|
| gates C and D alone, no model | 28 of 28 | 14 of 14 | 14 of 14 | 6 of 14 |
| gemma2:2b, bare | 8 of 28 | 6 of 14 | 2 of 14 | 10 of 14 |
| gemma2:2b + gates C and D | 8 of 28 | 6 of 14 | 2 of 14 | 10 of 14 |

Files: `eval/results/2026-10-15-relations-gates-only-gates-only.json`, `eval/results/2026-10-15-relations-bare-gemma2-2b.json`,
`eval/results/2026-10-15-relations-gated-gemma2-2b.json` (every reply in full). No reply was unparsable (0 errors).

What the numbers say, and no more:

- **The gates cannot see a relation.** Alone they accepted every one of the 28 wrong answers. A wrong-actor answer
  reuses the words and the number of its passage, so "is this in the source" is always yes.
- **Adding the gates changed no verdict.** All 42 decisions are identical with and without them. The six correct answers
  the gates refuse (a paraphrase that drifts lexically, gate D) are six the model had already refused.
- **The model is a strict checker, not a good one.** It accepted 8 of 28 wrong answers, more often when the party was
  wrong (6 of 14) than when the action was (2 of 14), and it refused 10 of the 14 correct ones. A low wrong-acceptance
  rate bought with a high refusal rate is mostly refusal.
- **Small and narrow.** 14 groups, one 2B model, one run. Three of the valid paraphrases were corrected before the run
  because they changed the meaning of the law text (the diff is in the same commit); every passage is checked verbatim
  against its source file on each build.

## Honest limitations

- **Slow locally.** CPU-only inference on 4 shared cores runs at roughly 2 tokens/second.
  Fine for a demonstration, not fine for production traffic. The live demo answers
  in about 10 seconds on a cold start and faster after.
- **Lexical grounding, not semantic.** Gate D compares content words by a
  fixed-length prefix, so it forgives Romanian inflection (`returnat` against
  `returnata`) but not synonymy. A correct paraphrase that shares little
  vocabulary with its source would be refused. The system fails toward refusing,
  which is the right direction here, but it is a real limitation and not a subtle
  one. Prefix matching is crude; it is deliberately the kind of crude that
  forgives morphology rather than meaning.
- **The same weights can answer differently on the same machine.** On 27 July 2026 `test_gates.py` passed
  4 of 4. On 5 October 2026 it passed 3 of 4, twice in a row (`test_run.log`). The failing case is the
  legitimate parcel question: the model now answers it correctly and then appends an off-topic sentence about
  EORI, and gate D refuses the whole answer. Nothing visible changed: same model file (gemma2:2b, digest
  8ccf136fdd52), same Ollama binary (0.17.0), and the untouched July `ask.py` gives the identical refusal. Our
  best guess, NOT proven: the CPU limits put on the Ollama service since July change how the arithmetic is
  split across cores, and a 2B model at temperature 0 can then pick a different token. The system failed in
  the safe direction (a refusal, not a wrong answer), and the test is left failing on purpose: editing the
  expectation until it passes would be exactly the kind of green result this repository argues against.
- **The gates check provenance, not relevance.** On the `eval/` test (5 October 2026) they let through every
  invented answer, because each one was assembled from true words of the source. Catching that needs a check that
  asks whether the sentence answers this question, not whether its words appear in the document.
- **Small corpus.** Five documents. The overlap finding in particular should be
  re-measured on a larger corpus before anyone treats it as a general result.
- **The refusal message is not an answer.** Refusing well is the point, but a
  system that refuses everything is also useless. The tests exist to hold both
  sides honest, which is why two of the four cases must be answered, not refused.

## Licence

MIT.
