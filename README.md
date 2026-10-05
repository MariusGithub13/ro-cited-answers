# Cited or refused

*(Romanian: „Răspunsuri citate sau refuzate". The prose here is English; the corpus,
the questions and the quoted model output stay in Romanian, because a Romanian-language
grounding demo is the whole point and the quotes are verbatim evidence.)*

A small, self-hosted Romanian question-answering demo that will not give you an
answer it cannot trace to a source document.

Everything runs locally: an open-weight model on Ollama, on a 4-core VPS in the
EU, no external API, no key, no data leaving the machine.

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

Requires [Ollama](https://ollama.com) with a chat model and an embedding model.

```bash
ollama pull gemma2:2b
ollama pull nomic-embed-text

python3 ask.py "Ce inseamna EORI si cat costa obtinerea lui?"
python3 ask.py "Care este capitala Frantei?"      # refused, gate A

python3 calibrate.py     # reproduce the overlap measurement
python3 test_gates.py    # 4 cases: 2 must be refused, 2 must be answered
                         # 27 Jul 2026: 4 of 4. 5 Oct 2026: 3 of 4, see 'Honest limitations'
```

The model is pluggable on purpose, because the model is not the differentiator:

```bash
RO_MODEL=llama3.2 python3 ask.py "..."
```

Every decision, accepted or refused, is appended to `audit.jsonl` with the
retrieval scores, the gate that fired, and the per-sentence attribution. A
refusal you cannot reconstruct later is just a different kind of unverifiable
output.

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

**The gates caught none of the invented answers.** Gates B, C and D refused 0 of 24 items; every refusal in the
gated run is the model's own "NU_STIU". The invented answers are built from real words and real numbers of the
remaining text: asked for a deadline whose paragraph was cut, the model answers with a deadline from the
neighbouring paragraph. Every number is in the source and every sentence overlaps it lexically, so gates that check
"is this in the source" pass it. They cannot see "does this answer the question that was asked".

Two caveats, stated so the numbers are not over-read. The gated mode also uses `ask.py`'s own prompt, which is
worded differently from the bare prompt, so the 4 vs 6 difference mixes prompt and gates; what is clean is that the
gates themselves fired on nothing. And 12 pairs on one model is a small sample.

The first gated run on 5 October refused everything, correct answers included: a harness bug handed the two
articles of each context to the gates as ONE fragment, so the model's honest "SURSE: 1, 2" read as an invented source.
Fixed in `run_eval.py` (each article is now its own fragment); the numbers above are from the corrected run.

## Honest limitations

- **Slow.** CPU-only inference on 4 shared cores runs at roughly 2 tokens/second.
  Fine for a demonstration, not fine for production traffic.
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
