# Contributing

Two test files, two purposes. `python3 test_gates_offline.py` runs the gates on canned model output and
needs nothing installed; CI runs it on every push. `python3 test_gates.py` asks the real model through
Ollama and is the honest test of the whole system; run it by hand and paste the result in your pull request.
If you change `eval/build_items.py`, run it and commit the rebuilt `eval/items.jsonl`.

To report a wrong answer, open an issue with the exact question, the model (`RO_MODEL` or the default),
the raw output, and the matching line from `audit.jsonl`, which holds the retrieval scores, the gate that
fired and the per-sentence attribution. An answer that was accepted and should not have been is the report
that matters most; say which sentence is wrong and which source should have refused it.

Do not edit a test's expectation to make it pass; see the 3 of 4 note in the README for why.
