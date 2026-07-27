#!/usr/bin/env python3
"""
The honest test. Each case declares what SHOULD happen, and the runner reports
pass/fail against that expectation rather than just printing output and letting
a human decide it looked fine.

The two impostor cases matter most. "Permis de conducere" outscores every real
question on pure similarity (0.773 vs a 0.697 floor), so it is the case that
proves the downstream gates are doing work that retrieval cannot.
"""
import sys, time
sys.path.insert(0, '/root/ro-cited-demo')
import ask

CASES = [
    # (question, must_be_accepted, why this case exists)
    ("Care este capitala Frantei si cati locuitori are?", False,
     "far out of corpus, the model KNOWS the answer from pretraining and must not use it"),
    ("Ce documente imi trebuie pentru un permis de conducere?", False,
     "near-domain impostor, outscores every real question on similarity (0.773)"),
    ("In cate zile se returneaza un colet daca nu depun documentele?", True,
     "legitimate, answer is verbatim in posta-returnare"),
    ("Ce inseamna EORI si cat costa obtinerea lui?", True,
     "legitimate, and the exact question the ungrounded model got WRONG"),
]


def main():
    passed = failed = 0
    for q, want_accept, why in CASES:
        print('=' * 78)
        print(f'Q: {q}')
        print(f'   ({why})')
        t0 = time.time()
        record, text = ask.ask(q, verbose=False)
        dt = time.time() - t0
        got_accept = record['verdict'] == 'ACCEPTAT'
        ok = got_accept == want_accept
        passed, failed = (passed + ok, failed + (not ok))
        print(f'   -> {record["verdict"]}'
              + (f' at gate {record["gate"]} ({record["reason"]})' if record.get('gate') else '')
              + f'  [{dt:.0f}s]')
        print(f'   -> expected {"ACCEPTAT" if want_accept else "REFUZAT"}: '
              f'{"PASS" if ok else "FAIL"}')
        if record.get('raw'):
            print(f'   raw: {record["raw"][:220]!r}')
        if record.get('cited_claimed'):
            print(f'   claimed sources : {record["cited_claimed"]}')
            print(f'   verified sources: {record.get("cited")}')
            if record.get('cited_dropped_as_padding'):
                print(f'   PADDING STRIPPED: {record["cited_dropped_as_padding"]}')
        if got_accept:
            print('   --- answer shown to the user ---')
            for line in text.splitlines():
                print(f'   {line}')
    print('=' * 78)
    print(f'{passed} passed, {failed} failed, out of {len(CASES)}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
