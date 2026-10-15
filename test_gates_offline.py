#!/usr/bin/env python3
"""Gates B, C and D with the model replaced by a canned reply, so the rules can run without Ollama.

This is not test_gates.py. That one asks the real model and is the honest test of the whole system; it needs
Ollama and gemma2:2b and is run by hand (3 of 4 on 5 October 2026, see test_run.log). This file only checks
that the CODE refuses what it says it refuses, on fixed text, so CI can run it on every push.
"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ask

DOC = {'id': 'eori-structura', 'titlu': 'Structura si costul numarului EORI',
       'body': ('Numarul EORI este atribuit gratuit si termenul mediu de solutionare este de 5 zile, '
                'iar termenul maxim este de 30 de zile. Cererea se depune la biroul vamal.'),
       'sursa': 'https://www.customs.ro/e-customs/eori', 'verificat': '2026-07-23'}
TOP = [(0.9, DOC)]

CASES = [
    # (canned model output, expected verdict, expected gate)
    ('Numarul EORI este atribuit gratuit si termenul mediu de solutionare este de 5 zile.\nSURSE: 1',
     'ACCEPTAT', None),
    ('NU_STIU\nSURSE: 1', 'REFUZAT', 'MODEL_ABSTAINED'),
    ('Numarul EORI este atribuit gratuit si termenul mediu de solutionare este de 5 zile.\nSURSE: 7',
     'REFUZAT', 'B_CITATION'),
    ('Numarul EORI este atribuit gratuit si termenul mediu de solutionare este de 5 zile.',
     'REFUZAT', 'B_CITATION'),
    ('Numarul EORI este atribuit gratuit si termenul mediu de solutionare este de 45 zile.\nSURSE: 1',
     'REFUZAT', 'C_NUMBERS'),
    ('Capitala Frantei este Paris si are multi locuitori frumosi.\nSURSE: 1',
     'REFUZAT', 'D_GROUNDING'),
]


def main():
    ask.AUDIT = os.path.join(tempfile.mkdtemp(), 'audit.jsonl')   # never the demo's own audit log
    failed = 0
    for out, want, gate in CASES:
        ask._post = lambda path, payload, timeout=0, _o=out: {'response': _o}
        record, _ = ask.gated_answer('intrebare de test', TOP, {'retrieved': []}, verbose=False)
        ok = record['verdict'] == want and record.get('gate') == gate
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  want {want}/{gate}  got {record['verdict']}/{record.get('gate')}  {out.splitlines()[0][:60]!r}")
    print(f"{len(CASES) - failed} passed, {failed} failed, out of {len(CASES)}")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
