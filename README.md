# Răspunsuri citate sau refuzate

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
- **Small corpus.** Five documents. The overlap finding in particular should be
  re-measured on a larger corpus before anyone treats it as a general result.
- **The refusal message is not an answer.** Refusing well is the point, but a
  system that refuses everything is also useless. The tests exist to hold both
  sides honest, which is why two of the four cases must be answered, not refused.

## Licence

MIT.
