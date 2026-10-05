#!/usr/bin/env python3
"""
Demo: raspunsuri in limba romana, citate sau refuzate.

WHY THIS EXISTS
---------------
A sovereign model decides WHERE the weights sit. It says nothing about whether a
specific answer is TRUE. This demo enforces the second property with mechanism
rather than instruction: an answer that cannot be traced to a source document is
refused before it ever reaches the reader.

Everything runs locally: Ollama on this host, no external API, no data leaving
the machine. Model is pluggable (MODEL below) precisely because the model is NOT
the differentiator. The gates are.

THE GATES (all must pass, else the answer is refused)
  A. RETRIEVAL   the best-matching source must clear MIN_SIM, else the question
                 is out of corpus and no amount of fluency should hide that.
  B. CITATION    the model must point at its sources, by fragment number or by id,
                 and every one must resolve to something we actually retrieved.
                 Deliberately easy to satisfy, so it is a formatting check, NOT
                 the thing standing between you and a wrong answer.
  C. NUMBERS     every number in the answer must appear verbatim in the text of a
                 CITED source. This is what stops "45 de zile" when the source
                 says 30, the failure mode that actually costs money here.
  D. GROUNDING   ⭐the strong one, and the only gate the model cannot talk its way
                 past. Every substantive sentence is scored against each cited
                 document separately and attributed to its best match; it must
                 clear MIN_GROUND against ONE document. Nothing about it depends
                 on the model following an instruction, which is why it still
                 works on a 2B model that cannot reliably obey a citation format.
                 Gate D also REBUILDS the citation list from the documents that
                 actually carried a sentence, so a model that pads its sources
                 gains nothing: the padding is stripped and logged.

WHAT THE FIRST TEST RUN TAUGHT (kept because it is the point of the whole demo)
  Ungrounded, this model said EORI meant "European Union Chamber of Commerce and
  Industry Number". Grounded against the corpus it answered correctly, verbatim,
  including the free-of-charge and 5-day facts. Same weights, same machine. The
  sovereignty of the model decided nothing; the gates decided everything.

Every decision is appended to audit.jsonl, because a refusal you cannot
reconstruct later is just a different kind of unverifiable output.
"""
import json, os, re, sys, urllib.request, hashlib, datetime, unicodedata

BASE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(BASE, 'corpus')
CACHE = os.path.join(BASE, '.embeddings.json')
AUDIT = os.path.join(BASE, 'audit.jsonl')
OLLAMA = 'http://127.0.0.1:11434'

MODEL = os.environ.get('RO_MODEL', 'gemma2:2b')   # pluggable on purpose
EMBED = 'nomic-embed-text'
TOP_K = 3

# ⭐MEASURED, NOT GUESSED. The first value here was 0.55, picked by intuition, and
# the first live test walked straight through it: "Care este capitala Frantei?"
# scored 0.611 against a Romanian customs corpus. calibrate.py then measured both
# populations properly and found they OVERLAP. A question about driving licences
# scores 0.773, higher than EVERY legitimate question in the corpus (lowest 0.697).
#
# So no single similarity threshold can separate in-corpus from out-of-corpus here,
# and gate A must NOT be treated as the load-bearing gate. It is set just under the
# lowest legitimate question so it catches only the far-out cases (Netflix, oil
# changes) while never silencing a real one. Near-domain impostors are caught
# downstream by the citation and number gates, which check the ANSWER against the
# SOURCE TEXT rather than trusting a distance metric.
# Re-run calibrate.py whenever the corpus changes; this number is corpus-specific.
MIN_SIM = 0.68

# Gate D. A sentence must reuse this fraction of its content words from a cited
# source. Verbatim or near-verbatim answers score ~0.9-1.0; a sentence imported
# from pretraining scores ~0.0, so the two populations here separate cleanly,
# unlike the retrieval similarities above. Sentences shorter than
# MIN_SENTENCE_WORDS are skipped: connective filler ("Iata situatiile:") carries
# no claim, and refusing over it would just reintroduce false refusals.
MIN_GROUND = 0.50
MIN_SENTENCE_WORDS = 5
REFUSAL = ("Nu pot raspunde la aceasta intrebare pe baza documentelor pe care le am. "
           "Nu am o sursa care sa sustina un raspuns.")


def _post(path, payload, timeout=300):
    req = urllib.request.Request(OLLAMA + path,
                                 data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def embed(text):
    return _post('/api/embeddings', {'model': EMBED, 'prompt': text})['embedding']


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def load_docs():
    docs = []
    for fn in sorted(os.listdir(CORPUS)):
        if not fn.endswith('.md'):
            continue
        raw = open(os.path.join(CORPUS, fn), encoding='utf-8').read()
        meta, _, body = raw.partition('---\n')[2].partition('---\n')
        d = {'file': fn, 'body': body.strip()}
        for line in meta.strip().splitlines():
            k, _, v = line.partition(':')
            d[k.strip()] = v.strip()
        docs.append(d)
    return docs


def build_index(docs):
    """Cache keyed on corpus content, so editing a doc rebuilds only when needed."""
    sig = hashlib.sha256(''.join(d['body'] for d in docs).encode()).hexdigest()
    if os.path.exists(CACHE):
        cached = json.load(open(CACHE, encoding='utf-8'))
        if cached.get('sig') == sig:
            return cached['vectors']
    print('indexez corpusul local...', file=sys.stderr)
    vectors = {d['id']: embed(d['titlu'] + '\n' + d['body']) for d in docs}
    json.dump({'sig': sig, 'vectors': vectors}, open(CACHE, 'w'))
    return vectors


PROMPT = """Esti un asistent care raspunde STRICT pe baza fragmentelor de mai jos.

REGULI OBLIGATORII:
- Raspunde numai cu informatii care se afla in fragmente. Nu adauga nimic din memoria ta.
- Nu inventa cifre, termene sau denumiri. Daca o cifra nu apare in fragmente, nu o scrie.
- Daca fragmentele nu contin raspunsul, scrie exact: NU_STIU
- Raspunde scurt, in limba romana, maximum 4 propozitii.
- Pe ultima linie scrie NUMERELE fragmentelor folosite, exact asa: SURSE: 1, 2

FRAGMENTE:
{context}

INTREBARE: {question}
"""

# Words too common to prove anything. If a sentence overlaps a source only on
# these, it is not grounded, it just speaks Romanian.
STOPWORDS = set("""
este sunt care sau daca deci fost fie fara catre dupa peste intre acest acesta
aceasta aceste acestea acel acea acele cele cel cea celor unui unei unor pentru
prin dintre asupra numai doar mult mai foarte poate pot trebuie avea are aiba
data zile zi luni ani anul cand unde cum ceea ceva toate toata tot toti orice
""".split())


def _norm(text):
    """Fold diacritics and case so 'Numarul' and 'Numărul' compare equal.

    The corpus is typed without diacritics but the model emits them (it wrote
    'Numărul EORI'), so a naive comparison would call a verbatim quote unsupported.
    """
    text = unicodedata.normalize('NFKD', text.lower())
    return ''.join(c for c in text if not unicodedata.combining(c))


def _content_words(text):
    return [w for w in re.findall(r'[a-z]{4,}', _norm(text)) if w not in STOPWORDS]


# ⭐Romanian is heavily inflected, and exact word matching punishes grammar rather
# than ungroundedness. The source says "trimitere ... extracomunitara este
# returnata"; the model wrote "extracomunitar ... returnat". Same words, different
# agreement, and exact matching scored that sentence at exactly 0.5000 against a
# 0.50 threshold. It passed only because the comparison is < and not <=, which is
# luck, not a margin. Comparing a fixed-length prefix instead treats an inflection
# as the match it obviously is, and lifts that same sentence to 0.83.
# Crude, but it is the right kind of crude: it forgives morphology, not meaning.
STEM = 6


def _stems(words):
    return {w[:STEM] for w in words}


def ask(question, verbose=True):
    docs = load_docs()
    vectors = build_index(docs)
    by_id = {d['id']: d for d in docs}

    qv = embed(question)
    scored = sorted(((cosine(qv, vectors[d['id']]), d) for d in docs),
                    key=lambda t: t[0], reverse=True)
    top = scored[:TOP_K]

    record = {'ts': datetime.datetime.now(datetime.UTC).isoformat(),
              'question': question, 'model': MODEL,
              'retrieved': [{'id': d['id'], 'sim': round(s, 3)} for s, d in top]}

    # GATE A: does the corpus even cover this?
    if not top or top[0][0] < MIN_SIM:
        record.update(verdict='REFUZAT', gate='A_RETRIEVAL',
                      reason=f'cea mai buna potrivire {top[0][0]:.2f} < {MIN_SIM}')
        return _finish(record, REFUSAL, verbose)

    return gated_answer(question, top, record, verbose)


def gated_answer(question, top, record, verbose=True):
    """Generation plus gates B, C, D on fragments that are already chosen.
    ask() chooses them by retrieval (gate A); eval/ hands them over directly, so the
    same gates can be measured on a fixed text (05.10.2026)."""
    by_id = {d['id']: d for _, d in top}
    # ⭐Fragments are NUMBERED, not labelled with their string id. The 2B model
    # simply will not echo an id like "posta-returnare"; both legitimate test cases
    # produced a correct grounded answer and then signed it "SURSE: 1, 2", so a
    # gate demanding ids threw away good answers. Meet the model where it is and
    # map the number back to the real document here, where it cannot be got wrong.
    context = '\n\n'.join(f"[{i}] {d['titlu']}\n{d['body']}"
                          for i, (_, d) in enumerate(top, 1))
    out = _post('/api/generate', {
        'model': MODEL,
        'prompt': PROMPT.format(context=context, question=question),
        'stream': False,
        'options': {'temperature': 0, 'num_predict': 220},
    })['response'].strip()
    record['raw'] = out

    # Split the sources line off BEFORE judging abstention, because the abstention
    # marker and the citations both live in the tail of the output.
    m = re.search(r'SURSE\s*:\s*(.+)', out, re.I)
    answer = re.sub(r'SURSE\s*:.*', '', out, flags=re.I | re.S).strip()

    # ABSTENTION, and it took two passes to get right.
    #   v1 matched "NU_STIU" exactly and missed the model's "Nu_stiu".
    #   v2 matched case-insensitively ANYWHERE in the output, and then threw away a
    #      perfectly good grounded answer because the model appended a stray
    #      "NU_STIU" line after it, cargo-culting the instruction.
    # So: strip the marker out, and abstain only if nothing substantive is LEFT.
    # Safe to be lenient here precisely because gate D still has to pass on
    # whatever remains, so treating a trailing NU_STIU as noise cannot smuggle an
    # ungrounded answer through.
    answer = re.sub(r'\bnu[_ ]?stiu\b\.?', ' ', answer, flags=re.I).strip()
    if len(_content_words(answer)) < MIN_SENTENCE_WORDS:
        record.update(verdict='REFUZAT', gate='MODEL_ABSTAINED',
                      reason='modelul a declarat ca nu stie')
        return _finish(record, REFUSAL, verbose)

    # GATE B: citations must exist and must resolve to something we actually retrieved
    tokens = [c.strip(' .[]') for c in m.group(1).split(',')] if m else []
    # The model sometimes signs off "SURSE: NU_STIU". That is the same instruction
    # cargo-culting as above, not a claim about a document, so drop it rather than
    # report it as a fabricated source id.
    tokens = [c for c in tokens if c and not re.fullmatch(r'nu[_ ]?stiu', c, re.I)]
    retrieved_ids = [d['id'] for _, d in top]
    record['cited_raw'] = tokens

    # Accept either the fragment NUMBER (what small models emit) or the literal id
    # (what a larger model plugged in via RO_MODEL tends to emit). An out-of-range
    # number is still an invented source, so the gate keeps its teeth: with 3
    # fragments on the table, "SURSE: 7" is a fabrication and is refused.
    cited, invented = [], []
    for t in tokens:
        if t.isdigit():
            i = int(t)
            (cited.append(retrieved_ids[i - 1]) if 1 <= i <= len(retrieved_ids)
             else invented.append(t))
        elif t in retrieved_ids:
            cited.append(t)
        else:
            invented.append(t)
    cited = list(dict.fromkeys(cited))          # dedupe, keep order
    # What the model CLAIMS it used. Gate D decides what it actually used.
    record['cited_claimed'] = cited

    if not tokens:
        record.update(verdict='REFUZAT', gate='B_CITATION',
                      reason='raspunsul nu indica nicio sursa')
        return _finish(record, REFUSAL, verbose)

    if invented:
        record.update(verdict='REFUZAT', gate='B_CITATION',
                      reason=f'surse inexistente: {invented}')
        return _finish(record, REFUSAL, verbose)

    # GATE C: every number in the answer must appear in a cited source
    cited_text = ' '.join(by_id[c]['body'] for c in cited)
    src_nums = set(re.findall(r'\d+', cited_text))
    ans_nums = set(re.findall(r'\d+', answer))
    unsupported = sorted(n for n in ans_nums - src_nums)
    if unsupported:
        record.update(verdict='REFUZAT', gate='C_NUMBERS',
                      reason=f'cifre nesustinute de sursele citate: {unsupported}')
        return _finish(record, REFUSAL, verbose)

    # GATE D + ATTRIBUTION: ⭐the one that does not ask the model to cooperate,
    # and the one that decides which citations are REAL.
    #
    # Numbering the fragments made gate B cheap to satisfy: any digit in range
    # passes, so the model can pad its citation list for free. The first all-green
    # run did exactly that. It answered a parcel-return question correctly out of
    # posta-returnare and then also cited eori-art18, which has nothing to do with
    # the question. The ANSWER was trustworthy and the CITATION LIST was noise,
    # which is precisely backwards for a system whose selling point is traceability.
    #
    # So citations are no longer taken on the model's word. Each substantive
    # sentence is scored against each cited document SEPARATELY and attributed to
    # its best match, and it must clear MIN_GROUND against ONE document rather than
    # against a mosaic of words pooled from three (pooling was the earlier version
    # and it is strictly weaker: it lets three loosely-related sources launder a
    # sentence none of them actually supports). The printed source list is then
    # rebuilt from the documents that actually carried a sentence. Anything the
    # model named but never used is dropped and logged as padding.
    sentences = [s.strip() for s in re.split(r'(?<=[.!?;:])\s+|\n+', answer) if s.strip()]
    per_doc_words = {c: _stems(_content_words(by_id[c]['body'])) for c in cited}
    attribution, ungrounded, used = [], [], []
    for s in sentences:
        words = _content_words(s)
        if len(words) < MIN_SENTENCE_WORDS:
            continue                     # too short to judge, and too short to smuggle a claim
        best, score = None, 0.0
        for c in cited:
            ov = sum(w[:STEM] in per_doc_words[c] for w in words) / len(words)
            if ov > score:
                best, score = c, ov
        attribution.append({'sentence': s, 'source': best, 'overlap': round(score, 2)})
        if score < MIN_GROUND:
            ungrounded.append(f'{score:.0%} "{s[:70]}"')
        elif best not in used:
            used.append(best)
    record['attribution'] = attribution

    if ungrounded:
        record.update(verdict='REFUZAT', gate='D_GROUNDING',
                      reason=f'propozitii nesustinute de sursele citate: {ungrounded}')
        return _finish(record, REFUSAL, verbose)
    if not used:
        record.update(verdict='REFUZAT', gate='D_GROUNDING',
                      reason='nicio propozitie nu a putut fi atribuita unei surse')
        return _finish(record, REFUSAL, verbose)

    padding = [c for c in cited if c not in used]
    record['cited_dropped_as_padding'] = padding
    record['cited'] = used

    record.update(verdict='ACCEPTAT', gate=None, reason=None)
    sources = '\n'.join(f"  [{c}] {by_id[c]['titlu']}\n      {by_id[c]['sursa']} "
                        f"(verificat {by_id[c]['verificat']})" for c in used)
    # Per-sentence attribution is printed, not just a source list, because "here
    # are three links, one of these supports it somewhere" is the weak form of
    # citation that this whole demo exists to argue against.
    detail = '\n'.join(f'  {a["overlap"]:>4.0%} [{a["source"]}]  {a["sentence"]}'
                       for a in attribution)
    text = f'{answer}\n\nSURSE:\n{sources}\n\nATRIBUIRE (fiecare propozitie, sursa care o sustine):\n{detail}'
    if padding:
        text += ('\n\nIGNORAT (surse pe care modelul le-a invocat dar nu le-a folosit): '
                 + ', '.join(padding))
    return _finish(record, text, verbose)


def _finish(record, text, verbose):
    with open(AUDIT, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    if verbose:
        v = record['verdict']
        mark = '✅' if v == 'ACCEPTAT' else '⛔'
        print(f"\n{mark} {v}" + (f"  (poarta {record['gate']}: {record['reason']})"
                                 if record.get('gate') else ''))
        print(text)
    return record, text


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('folosire: python3 ask.py "intrebarea ta"')
    ask(' '.join(sys.argv[1:]))
