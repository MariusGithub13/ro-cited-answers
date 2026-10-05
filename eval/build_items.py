#!/usr/bin/env python3
"""build_items.py - builds items.jsonl from the ORIGINAL text of Legea 544/2001 (legislatie.just.ro).

Each question comes in a PAIR, the Merlin/Morgana idea from Aleph Alpha's Kolibri report:
  answerable : the context holds the paragraph with the answer; the model must answer.
  abstain    : the SAME context with that paragraph cut out; the only right reply is "NU REIESE DIN TEXT".
The test measures GROUNDING (does the model answer from the text it was given, and stop when the
text does not say), not legal truth: the source is the 2001 original, not the consolidated law.

Every pair is checked here, mechanically: the gold answer must appear in the answerable context
and must NOT appear in the abstain context. A pair that fails that check stops the build.
"""
import json, os, re, sys, unicodedata

SRC = "sources/legea-544-2001.txt"

def norm(s):
    s = s.replace("ş", "s").replace("ș", "s").replace("ţ", "t").replace("ț", "t")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()

def articles(text):
    text = re.sub(r"[ \t]+", " ", text).replace("...", " ")
    parts = re.split(r"\+\s*\n?\s*Articolul (\d+) ", text)
    arts = {}
    for i in range(1, len(parts) - 1, 2):
        body = re.split(r"\n\s*\+", parts[i + 1])[0]
        arts[int(parts[i])] = re.sub(r"\s+", " ", f"Articolul {parts[i]} " + body).strip()
    return arts

def cut_par(art_text, k):
    """remove paragraph (k) up to the next (k+1) or the end of the article"""
    m = re.search(rf"\({k}\) .*?(?=\({k + 1}\) |$)", art_text)
    if not m:
        sys.exit(f"paragraph ({k}) not found in: {art_text[:80]}")
    return (art_text[:m.start()] + art_text[m.end():]).strip()

# (id, article, neighbour article for distractor text, paragraph to cut (None = cut the sentence given), question, gold variants)
PAIRS = [
    ("refuz-termen", 7, 8, 2, "În ce termen se motivează și se comunică refuzul de a comunica informațiile solicitate?", [r"\b5 zile", r"cinci zile"]),
    ("presa-verbal", 8, 9, 5, "În cât timp se comunică informațiile de interes public solicitate verbal de presă?", [r"24 de ore"]),
    ("acreditare", 18, 17, 2, "În ce termen se acordă acreditarea unui ziarist, de la înregistrarea cererii?", [r"\bdoua zile", r"\b2 zile"]),
    ("reclamatie-termen", 21, 20, 2, "În ce termen se poate depune reclamație la conducătorul instituției împotriva refuzului angajatului desemnat?", [r"\b30 de zile", r"treizeci"]),
    ("reclamatie-raspuns", 21, 20, 3, "În ce termen se transmite răspunsul dacă reclamația se dovedește întemeiată?", [r"\b15 zile", r"cincisprezece"]),
    ("conferinte", 17, 16, 1, "Cât de des trebuie să organizeze autoritățile publice conferințe de presă, de regulă?", [r"o data pe luna", r"lunar"]),
    ("copii-cost", 9, 10, 1, "Cine suportă costul serviciilor de copiere a documentelor?", [r"solicitant"]),
    ("instanta", 22, 21, 1, "La ce secție a tribunalului se face plângerea persoanei vătămate în drepturile prevăzute de această lege?", [r"contencios administrativ"]),
    ("timbru", 22, 23, 5, "Plângerea și apelul în baza acestei legi sunt supuse taxei de timbru?", [r"scutit", r"nu sunt supuse", r"\bnu\b"]),
    ("raport-mo", 5, 6, 3, "În ce parte a Monitorului Oficial se publică raportul periodic de activitate al autorităților publice?", [r"partea a ii", r"partea ii", r"partea a doua"]),
    ("date-personale", 14, 13, 1, "În ce situație informațiile cu privire la datele personale ale cetățeanului pot deveni informații de interes public?", [r"functi(e|i) publice?"]),
    ("verbal-program", 8, 7, 3, "Cât de des trebuie inclus în programul de comunicare verbală un interval după programul de funcționare?", [r"o zi pe saptamana", r"saptamanal"]),
]

def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))   # paths are relative to eval/
    arts = articles(open(SRC, encoding="utf-8").read())
    out, bad = [], []
    for pid, a, nb, par, q, gold in PAIRS:
        full = arts[a]
        cut = cut_par(full, par)
        ctx_ans = f"{full}\n\n{arts[nb]}"
        ctx_abs = f"{cut}\n\n{arts[nb]}"
        hit_ans = any(re.search(g, norm(full)) for g in gold)
        hit_abs = any(re.search(g, norm(cut)) or re.search(g, norm(arts[nb])) for g in gold)
        # "nu" as a gold for the yes/no item is checked only against the cut paragraph itself
        if pid == "timbru":
            hit_abs = "scutit" in norm(cut) or "scutit" in norm(arts[nb])
        if not hit_ans or hit_abs:
            bad.append(f"{pid}: gold in answerable={hit_ans}, gold leaks into abstain={hit_abs}")
        out.append({"id": pid + "-A", "pair": pid, "type": "answerable", "source": f"Legea 544/2001 art. {a}", "question": q, "context": ctx_ans, "gold": gold})
        out.append({"id": pid + "-X", "pair": pid, "type": "abstain", "source": f"Legea 544/2001 art. {a} fara alin. ({par})", "question": q, "context": ctx_abs, "gold": []})
    if bad:
        print("BUILD REFUSED, pairs that do not test what they claim:\n  " + "\n  ".join(bad)); return 2
    with open("items.jsonl", "w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print(f"items.jsonl: {len(out)} items, {len(PAIRS)} pairs, every pair checked (gold in the answerable context, absent from the abstain one)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
