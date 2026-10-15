#!/usr/bin/env python3
"""run_relations.py - scores the relations set (items_relations.jsonl) with TWO separate rates.

  python3 run_relations.py --selftest                 no model, no network: proves the arithmetic
  python3 run_relations.py --gates-only               no model: ask.py gates C (numbers) and D (grounding) on the proposed answer
  python3 run_relations.py MODEL [--base URL]         bare: the model is asked to verify the proposed answer against the span
  python3 run_relations.py --gated MODEL [--base URL] the model's verdict AND the gates: accepted only if both accept

The model is shown the span, the question and a PROPOSED answer, and must open with "VERDICT: ACCEPT" or
"VERDICT: RESPINS". A gate refusal counts as RESPINS. A reply with no parsable verdict is ERROR and is counted in
neither denominator (reported separately, never as a pass or a fail).

Rates, each over its own denominator:
  wrong_accepted   : wrong variants (wrong_actor + wrong_action) ACCEPTED / all wrong variants; also split by variant
  valid_refused    : valid variants REFUSED / all valid variants   (a gate that refuses everything scores 100% here)
The single score of run_eval.py / items.jsonl is untouched; this file only reads items_relations.jsonl.
Heavy: run through /opt/devaland/shared/bin/heavy-job.sh when a model is involved.
"""
import datetime as dt, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM = ("Ești un verificator pentru o instituție publică din România. Judeci DOAR pe baza textului primit. "
          "Ți se dă un TEXT, o ÎNTREBARE și un RĂSPUNS PROPUS. Verifici dacă răspunsul propus spune corect CINE face CE și în ce TERMEN, "
          "așa cum rezultă din text. Dacă termenul sau obligația sunt atribuite altei părți decât cea din text, sau altei acțiuni, răspunsul este greșit. "
          "Prima linie a răspunsului tău este exact una dintre: VERDICT: ACCEPT sau VERDICT: RESPINS. A doua linie: o propoziție cu varianta corectă din text.")

def load(path=None):
    path = path or os.path.join(HERE, "items_relations.jsonl")
    return [json.loads(l) for l in open(path, encoding="utf-8")]

def parse_verdict(reply):
    m = re.search(r"VERDICT\s*:\s*(ACCEPT|RESPINS)", reply, re.I)
    return None if not m else ("accept" if m.group(1).upper() == "ACCEPT" else "reject")

def relation_rates(rows):
    """rows: dicts with variant and decision in {accept, reject, ERROR}. ERROR is in no denominator."""
    def part(variants, decision):
        sel = [r for r in rows if r["variant"] in variants and r["decision"] != "ERROR"]
        n = sum(r["decision"] == decision for r in sel)
        return {"count": n, "of": len(sel), "text": f"{n} of {len(sel)}",
                "rate": round(n / len(sel), 4) if sel else None}
    return {"wrong_accepted_combined": part(("wrong_actor", "wrong_action"), "accept"),
            "wrong_accepted_wrong_actor": part(("wrong_actor",), "accept"),
            "wrong_accepted_wrong_action": part(("wrong_action",), "accept"),
            "valid_refused": part(("valid",), "reject"),
            "errors": sum(r["decision"] == "ERROR" for r in rows)}

def gate_cd(answer, span):
    """ask.py gates C and D applied to a PROPOSED answer against its span (deterministic, no model). Returns None if both pass, else the gate."""
    sys.path.insert(0, os.path.join(HERE, ".."))
    import ask as g
    if set(re.findall(r"\d+", answer)) - set(re.findall(r"\d+", span)):
        return "C_NUMBERS"
    span_stems = g._stems(g._content_words(span))
    for s in [x.strip() for x in re.split(r"(?<=[.!?;:])\s+|\n+", answer) if x.strip()]:
        words = g._content_words(s)
        if len(words) < g.MIN_SENTENCE_WORDS:
            continue
        if sum(w[:g.STEM] in span_stems for w in words) / len(words) < g.MIN_GROUND:
            return "D_GROUNDING"
    return None

def ask_model(base, model, item):
    import urllib.request
    body = {"model": model, "temperature": 0, "max_tokens": 160, "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"TEXT:\n{item['context']}\n\nÎNTREBARE: {item['question']}\n\nRĂSPUNS PROPUS: {item['proposed_answer']}"}]}
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer local"})
    return json.load(urllib.request.urlopen(req, timeout=600))["choices"][0]["message"]["content"]

def summarise(model, mode, base, rows, t0):
    s = {"model": model, "mode": mode, "base": base, "set": "items_relations.jsonl",
         "run_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "items": len(rows), "groups": len({r["group"] for r in rows}), "secs": round(time.time() - t0)}
    s.update(relation_rates(rows))
    return s

def selftest():
    items = load()
    for name, fn in (("refuse-everything", lambda it: "reject"), ("accept-everything", lambda it: "accept"),
                     ("oracle", lambda it: it["expected"])):
        rows = [{"variant": it["variant"], "decision": fn(it)} for it in items]
        r = relation_rates(rows)
        print(f"{name:<18} wrong accepted {r['wrong_accepted_combined']['text']} "
              f"(actor {r['wrong_accepted_wrong_actor']['text']}, action {r['wrong_accepted_wrong_action']['text']}); "
              f"valid refused {r['valid_refused']['text']}")
    rows = [{"variant": it["variant"], "decision": "reject"} for it in items]
    r = relation_rates(rows)
    ok = r["valid_refused"]["rate"] == 1.0 and r["wrong_accepted_combined"]["rate"] == 0.0
    print("refuse-everything shows 100% valid refused:", ok)
    return 0 if ok else 2

def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        return selftest()
    base = "http://localhost:11434/v1"
    if "--base" in args:
        i = args.index("--base"); base = args[i + 1]; del args[i:i + 2]
    gated, gates_only = "--gated" in args, "--gates-only" in args
    args = [a for a in args if a not in ("--gated", "--gates-only")]
    if not args and not gates_only:
        print(__doc__); return 2
    models = ["gates-only"] if gates_only else args
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    items = load()
    for model in models:
        rows, t0 = [], time.time()
        mode = "gates-only" if gates_only else ("gated" if gated else "bare")
        for it in items:
            reply, dec = "", "ERROR"
            try:
                if gates_only:
                    gate = gate_cd(it["proposed_answer"], it["span"])
                    reply, dec = (f"REFUZAT {gate}" if gate else "ACCEPTAT"), ("reject" if gate else "accept")
                else:
                    reply = ask_model(base, model, it); v = parse_verdict(reply)
                    if v is None:
                        dec = "ERROR"
                    else:
                        dec = v
                        if gated and v == "accept":
                            gate = gate_cd(it["proposed_answer"], it["span"])
                            if gate:
                                dec, reply = "reject", f"{reply} || REFUZAT {gate}"
            except Exception as e:
                reply, dec = f"{type(e).__name__}: {e}"[:200], "ERROR"
            rows.append({"id": it["id"], "group": it["group"], "variant": it["variant"], "expected": it["expected"],
                         "decision": dec, "correct": (dec == it["expected"]) if dec != "ERROR" else None, "reply": reply[:400]})
            print(f"{model:<18} {mode:<10} {it['id']:<44} {dec}", flush=True)
        s = summarise(model, mode, base, rows, t0)
        fn = os.path.join(HERE, "results", f"{s['run_at'][:10]}-relations-{mode}-{re.sub(r'[^a-z0-9.]+', '-', model.lower())}.json")
        json.dump({"summary": s, "rows": rows}, open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("SUMMARY", json.dumps(s, ensure_ascii=False), flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
