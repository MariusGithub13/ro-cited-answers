#!/usr/bin/env python3
"""
Measure the ACTUAL similarity distribution before picking MIN_SIM.

WHY: the first live test refused correctly but for the wrong reason. A question
about the capital of France scored 0.611 against a Romanian customs corpus and
sailed straight through Gate A, which was set to 0.55 on nothing but a guess.
nomic-embed-text does not use the full 0..1 range, so an absolute threshold
picked by intuition is meaningless. This measures where the two populations
actually sit, so the threshold is derived from data instead of vibes.

Embedding only, no generation, so it costs seconds rather than minutes.
"""
import sys, statistics
sys.path.insert(0, '/root/ro-cited-demo')
import ask

IN_CORPUS = [
    "In cate zile se returneaza un colet daca nu depun documentele?",
    "De la ce moment incepe sa curga termenul de returnare?",
    "Cand am nevoie de cod EORI pentru un colet?",
    "Cat costa obtinerea numarului EORI?",
    "Ce structura are numarul EORI pentru o firma din Romania?",
    "Poate un comisionar vamal sa depuna cererea in numele meu?",
    "Cum verific daca un numar EORI este valid?",
]

OUT_OF_CORPUS = [
    "Care este capitala Frantei si cati locuitori are?",
    "Cum imi schimb uleiul la masina?",
    "Ce cota de TVA se aplica la cazare in Romania?",
    "Cat costa un abonament Netflix?",
    "Care sunt termenele de prescriptie in dreptul penal roman?",
    "Ce documente imi trebuie pentru un permis de conducere?",
    "Cine a castigat Cupa Romaniei anul trecut?",
]


def main():
    docs = ask.load_docs()
    vectors = ask.build_index(docs)

    def top_sim(q):
        qv = ask.embed(q)
        return max(ask.cosine(qv, vectors[d['id']]) for d in docs)

    hits = [(q, top_sim(q)) for q in IN_CORPUS]
    miss = [(q, top_sim(q)) for q in OUT_OF_CORPUS]

    print('IN CORPUS (should be ACCEPTED by gate A)')
    for q, s in sorted(hits, key=lambda t: t[1]):
        print(f'  {s:.3f}  {q}')
    print('\nOUT OF CORPUS (should be REFUSED by gate A)')
    for q, s in sorted(miss, key=lambda t: t[1], reverse=True):
        print(f'  {s:.3f}  {q}')

    lo_hit = min(s for _, s in hits)
    hi_miss = max(s for _, s in miss)
    print(f'\nlowest legitimate question : {lo_hit:.3f}')
    print(f'highest impostor question  : {hi_miss:.3f}')
    print(f'separation margin          : {lo_hit - hi_miss:+.3f}')

    if lo_hit > hi_miss:
        rec = (lo_hit + hi_miss) / 2
        print(f'\nCLEAN SEPARATION. Recommended MIN_SIM = {rec:.2f}')
    else:
        print('\nNO CLEAN SEPARATION on similarity alone.')
        print('A single threshold cannot split these two populations, so gate A')
        print('cannot be the load-bearing gate. Set MIN_SIM below the lowest')
        print(f'legitimate question ({lo_hit:.3f}) so it only catches the truly')
        print('far-out cases, and let gates B and C carry the real weight.')
        print(f'Suggested MIN_SIM = {lo_hit - 0.02:.2f} (keeps every real question alive)')
    print(f'\n(mean hit {statistics.mean(s for _, s in hits):.3f}, '
          f'mean miss {statistics.mean(s for _, s in miss):.3f})')


if __name__ == '__main__':
    main()
