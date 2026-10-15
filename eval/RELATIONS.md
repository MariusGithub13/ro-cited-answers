# Relations set: who must do what, by when

The first set (`items.jsonl`) tests abstention. This set tests a different failure: an answer made of words that ARE in the
text, attached to the wrong party or the wrong action. A provenance check passes such an answer.

14 groups, 42 items, in `items_relations.jsonl` (built by `build_relations.py`). Each group is ONE source span copied verbatim
from `sources/` (Legea 544/2001, Legea 190/2018, OSGG 600/2018, original texts) and exactly three adjacent variants that share
the group id, the span and the question:

| variant | what it is | a gate should |
|---|---|---|
| `valid` | low-overlap paraphrase, correct actor, action and deadline | accept |
| `wrong_actor` | same number or obligation, given to the other party | reject |
| `wrong_action` | right actor, right number, obligation attached to a different action | reject |

The case that started the set is group `reclamatie-15-zile` (Legea 544/2001 art. 21 alin. (2)-(3)): the 15 days are the
authority's deadline to send the answer, and the wrong-actor variant gives them to the person as the deadline to complain.

Some wrong answers describe an action that exists elsewhere in the same law. They are wrong only against the given span.
The wrong answers are test material written by us, not legal statements. The test measures grounding, not legal truth.

Two rates, each over its own denominator (`run_relations.py`):
1. wrong answers ACCEPTED out of all wrong variants (28), reported for `wrong_actor` (14), `wrong_action` (14) and combined;
2. valid paraphrases REFUSED out of all valid variants (14). A gate that refuses everything shows 100% here.

```
python3 build_relations.py                  # rebuild + check every span against its source file
python3 run_relations.py --selftest         # arithmetic only, no model
python3 run_relations.py --gates-only       # ask.py gates C and D on the proposed answers, no model
/opt/devaland/shared/bin/heavy-job.sh ro-eval python3 run_relations.py MODEL        # bare verifier
/opt/devaland/shared/bin/heavy-job.sh ro-eval python3 run_relations.py --gated MODEL # verifier AND gates
```
