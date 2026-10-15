# README proof, 15 October 2026

Every command in the README, run in order on a clean clone of `main` (commit `4b25727`), in a cloud
container: Ubuntu 24.04, Python 3.13.16, 4 CPU cores, no GPU, no Ollama installed, outbound network
limited to a short allow-list (PyPI reachable; `ollama.com` refused by the egress proxy with HTTP 403).

Legend: **passed** means the command exited as the README says and the output matched. **not run here**
means the container lacks something the command needs, with the reason. Every line of output below was
produced in this session; nothing is inferred.

## `ollama pull gemma2:2b`, `ollama pull nomic-embed-text`

**Not run here.** Ollama is not installed and cannot be installed: the egress proxy refuses
`https://ollama.com/install.sh` (`CONNECT tunnel failed, response 403`). `127.0.0.1:11434` refuses connections.

## `python3 ask.py "Ce inseamna EORI si cat costa obtinerea lui?"`

**Not run here** (needs Ollama). Started so the failure is on record; it stops at the first embedding call:

```
$ python3 ask.py "Ce inseamna EORI si cat costa obtinerea lui?"
indexez corpusul local...
urllib.error.URLError: <urlopen error [Errno 111] Connection refused>
[exit 1]
```

With no argument the usage line prints, as the code says:

```
$ python3 ask.py
folosire: python3 ask.py "intrebarea ta"
[exit 1]
```

`RO_MODEL` is read by `ask.py` as the README says. `audit.jsonl` is appended on every decision (`_finish`).

## `python3 calibrate.py` and `python3 test_gates.py`

**Not run here** (both need Ollama). Both stop with the same `Connection refused` traceback; `test_gates.py`
prints the first case header and dies on its embedding call. Two things seen in the code, not changed:

- Both scripts begin with `sys.path.insert(0, '/root/ro-cited-demo')`, the author's server path. It is
  harmless on a clone because `import ask` also resolves from the script's own directory, so the README
  commands work from any checkout. Left as it is.
- `test_run.log` (committed) shows the 3 of 4 result the README describes, with the failing case being
  the legitimate parcel question refused at gate D. The README's account matches the log.

## `python3 test_gates_offline.py` (new in this branch)

**Passed.** The model is replaced by canned replies; only the code's gates are under test:

```
$ python3 test_gates_offline.py
PASS  want ACCEPTAT/None  got ACCEPTAT/None
PASS  want REFUZAT/MODEL_ABSTAINED  got REFUZAT/MODEL_ABSTAINED
PASS  want REFUZAT/B_CITATION  got REFUZAT/B_CITATION      (SURSE: 7 with one fragment on the table)
PASS  want REFUZAT/B_CITATION  got REFUZAT/B_CITATION      (no SURSE line at all)
PASS  want REFUZAT/C_NUMBERS  got REFUZAT/C_NUMBERS        (45 zile, source says 5 and 30)
PASS  want REFUZAT/D_GROUNDING  got REFUZAT/D_GROUNDING    (a fluent sentence with no source word)
6 passed, 0 failed, out of 6
[exit 0]
```

It writes its audit records to a temporary file, never to the repository's `audit.jsonl`.

## `eval/`: `python3 build_items.py`

**Passed.** The rebuilt `items.jsonl` is byte-identical to the committed one (`git status` clean afterwards).

```
$ cd eval && python3 build_items.py
items.jsonl: 24 items, 12 pairs, every pair checked (gold in the answerable context, absent from the abstain one)
[exit 0]
```

## `eval/`: `python3 run_eval.py gemma2:2b`, `--gated`, `--base`

**Not run here** (needs a model server). Run so the failure mode is on record: every item is reported as
`ERROR` and counted as neither correct nor wrong, which is what the harness docstring promises:

```
$ python3 run_eval.py gemma2:2b
gemma2:2b          bare   refuz-termen-A         ERROR
... (24 lines)
SUMMARY {"model": "gemma2:2b", "mode": "bare", ..., "items": 24, "errors": 24, "answerable_correct": "0 of 0", "abstain_correct": "0 of 0", "hallucinations": 0}
[exit 0]
```

The result file this produced in `eval/results/` was deleted; it is also covered by `.gitignore`.
With no argument `run_eval.py` prints its docstring and exits 2.

## The results table and the "0 of 24" claim, checked against the committed files

Read with a six-line Python script from the three committed result files:

| | bare | gated | README says |
|---|---|---|---|
| answerable correct | 12 of 12 | 12 of 12 | 12 of 12, 12 of 12 |
| abstain said "NU REIESE DIN TEXT" | 8 of 12 | 6 of 12 | 8 of 12, 6 of 12 |
| invented an answer | 4 | 6 | 4, 6 |
| wall time | 1236 s | 2212 s | not stated |

`eval/results/gated-audit.jsonl`: 24 records. Verdicts: 18 `ACCEPTAT`, 6 `REFUZAT` at `MODEL_ABSTAINED`.
Records refused at `B_CITATION`, `C_NUMBERS` or `D_GROUNDING`: **0**. The README sentence "Gates B, C and D
refused 0 of 24 items; every refusal in the gated run is the model's own NU_STIU" is true of the file.

The README already states the provenance-not-relevance limitation twice, once under the table and once under
"Honest limitations". This branch adds one clause under the table that names it with the same words as the
limitations list, so a reader of the table does not have to find the second passage.

## Other README claims checked without a model

| Claim | Checked how | Result |
|---|---|---|
| Five corpus documents with source URL and `verificat` date | `ls corpus/`, front matter of each | true, 5 files |
| `test_gates.py` has 4 cases, 2 refused, 2 answered | the `CASES` list | true |
| `--base URL` plugs in any OpenAI-compatible server | `run_eval.py` argument parsing | true |
| MIT licence | `LICENSE` | true |
| 27 July 4 of 4, 5 October 3 of 4 | `test_run.log` for 5 October | the log shows 3 of 4; July is the author's record |
| "roughly 2 tokens/second" | needs the model | not measured here, left as the author's number |

## What changed in the README, and why

1. The Python version is stated (`ask.py` uses `datetime.UTC`, which needs 3.11 or newer; 3.13 used here).
   The README named none.
2. A line for `test_gates_offline.py` in the command block, marked as the CI test, so nobody mistakes it
   for the real `test_gates.py`.
3. One sentence on what every script does when Ollama is not running (a `Connection refused` traceback).
4. One clause under the results table naming the limitation with the words used in "Honest limitations".
5. A pointer to this document.

Nothing else was changed. All measured numbers in the README are the author's and were left alone.
