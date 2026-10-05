#!/usr/bin/env python3
"""run_eval.py MODEL [MODEL...] [--base URL] - runs items.jsonl against any OpenAI-compatible endpoint.

Default endpoint: the local Ollama on this server (free, CPU). Kolibri, Qwen or any vLLM server
plugs in with --base, unchanged. Temperature 0. One JSON result file per model in results/.

Scoring is mechanical, never by eye:
  answerable item : CORRECT if the reply matches a gold pattern and does not abstain
  abstain item    : CORRECT if the reply contains "NU REIESE DIN TEXT"; anything else is a HALLUCINATION
Three states per item: correct / wrong / ERROR (the call failed). An ERROR is never counted as either.

--gated : the same items go through ../ask.py gates B, C and D (citation, numbers, per-sentence grounding)
          on the same local model, instead of a bare call. A gate refusal counts as an abstention.
          Bare vs gated on identical items is the point: same weights, same machine, what do the gates stop?
"""
import datetime as dt, json, os, re, sys, time, unicodedata, urllib.request

SYSTEM = ("Ești un asistent pentru o instituție publică din România. Răspunzi DOAR pe baza textului primit. "
          "Dacă textul nu conține răspunsul, răspunzi exact: NU REIESE DIN TEXT. "
          "Nu folosești cunoștințe din afara textului. Răspunzi scurt, într-o singură propoziție, în limba română.")
ABSTAIN = "nu reiese din text"

def norm(s):
    s = s.replace("ş", "s").replace("ș", "s").replace("ţ", "t").replace("ț", "t")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()

def ask(base, model, item):
    body = {"model": model, "temperature": 0, "max_tokens": 120, "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"TEXT:\n{item['context']}\n\nÎNTREBARE: {item['question']}"}]}
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer local"})
    return json.load(urllib.request.urlopen(req, timeout=600))["choices"][0]["message"]["content"]

def ask_gated(model, item):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import ask as gates
    gates.MODEL = model
    gates.AUDIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "gated-audit.jsonl")  # never the demo's own audit log
    # The context holds TWO articles (the one asked about + a neighbour). Each goes in as its own fragment:
    # handing both over as one fragment made the model's honest "SURSE: 1, 2" look like an invented source
    # to gate B, and every answer was refused (harness bug found 05.10.2026, not a gate bug).
    parts = [p for p in item["context"].split("\n\n") if p.strip()]
    top = [(1.0, {"id": str(i), "titlu": p.split(" ", 2)[0] + " " + p.split(" ", 2)[1], "body": p,
                  "sursa": "legislatie.just.ro, Legea 544/2001 (text original)", "verificat": "05.10.2026"})
           for i, p in enumerate(parts, 1)]
    record = {"question": item["question"], "model": model, "retrieved": [{"id": d["id"], "sim": 1.0} for _, d in top],
              "eval_item": item["id"]}
    record, text = gates.gated_answer(item["question"], top, record, verbose=False)
    if record["verdict"] != "ACCEPTAT":
        return "NU REIESE DIN TEXT (" + str(record.get("gate")) + ")"
    return text.split("\n\nSURSE:")[0]

def score(item, reply):
    r = norm(reply)
    abstained = ABSTAIN in r
    if item["type"] == "abstain":
        return "correct" if abstained else "hallucination"
    if abstained:
        return "wrong_abstained"
    return "correct" if any(re.search(g, r) for g in item["gold"]) else "wrong"

def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))   # paths are relative to eval/
    args = sys.argv[1:]
    base = "http://localhost:11434/v1"
    if "--base" in args:
        i = args.index("--base"); base = args[i + 1]; del args[i:i + 2]
    gated = "--gated" in args
    args = [a for a in args if a != "--gated"]
    if not args:
        print(__doc__); return 2
    items = [json.loads(l) for l in open("items.jsonl", encoding="utf-8")]
    os.makedirs("results", exist_ok=True)
    for model in args:
        rows, t0 = [], time.time()
        for it in items:
            try:
                rep = ask_gated(model, it) if gated else ask(base, model, it); st = score(it, rep)
            except Exception as e:
                rep, st = f"{type(e).__name__}: {e}"[:200], "ERROR"
            rows.append({"id": it["id"], "type": it["type"], "state": st, "reply": rep[:400]})
            print(f"{model:<18} {'gated' if gated else 'bare':<6} {it['id']:<22} {st}", flush=True)
        ans = [r for r in rows if r["type"] == "answerable" and r["state"] != "ERROR"]
        abs_ = [r for r in rows if r["type"] == "abstain" and r["state"] != "ERROR"]
        summary = {
            "model": model, "mode": "gated" if gated else "bare", "base": base, "run_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "items": len(rows), "errors": sum(r["state"] == "ERROR" for r in rows), "secs": round(time.time() - t0),
            "answerable_correct": f"{sum(r['state'] == 'correct' for r in ans)} of {len(ans)}",
            "abstain_correct": f"{sum(r['state'] == 'correct' for r in abs_)} of {len(abs_)}",
            "hallucinations": sum(r["state"] == "hallucination" for r in abs_),
        }
        fn = f"results/{summary['run_at'][:10]}-{summary['mode']}-{re.sub(r'[^a-z0-9.]+', '-', model.lower())}.json"
        json.dump({"summary": summary, "rows": rows}, open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
