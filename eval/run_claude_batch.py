#!/usr/bin/env python3
"""run_claude_batch.py MODEL [MODEL...] - the same 24 items as run_eval.py, BARE, through the Anthropic Message Batches API.

Same system prompt, same user message, same mechanical scoring as run_eval.py (imported, never copied), so a Claude row is
comparable with the gemma2:2b rows of 5 October. Bare only: the gates of ask.py (B citation, C numbers, D grounding) run on
the local Ollama model and are not re-implemented for Claude here. One result file per model in results/, the same shape as
run_eval.py writes. Three states per item: correct / wrong / ERROR; an ERROR is never counted as either.

Why a batch: it is asynchronous (50 percent of the standard price), nothing here is latency-sensitive, and the run is one
request per item per model, so cost is cents. Thinking stays at the models' defaults with effort low: the task is one
sentence from a given text, and the point of the measurement is the answer, not the reasoning.

Key: ANTHROPIC_API_KEY from the environment, or read in-process from the vault file given in --key-file (never printed).
"""
import argparse, datetime as dt, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_eval  # noqa: E402  (SYSTEM, score, norm: one definition, shared)

import anthropic  # noqa: E402


def load_key(path):
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    if not path:
        sys.exit("no ANTHROPIC_API_KEY in the environment and no --key-file")
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(f"no ANTHROPIC_API_KEY line in {path}")


def request_for(model, item):
    return {
        "custom_id": re.sub(r"[^a-zA-Z0-9_-]", "-", f"{model}__{item['id']}")[:64],
        "params": {
            "model": model,
            "max_tokens": 4000,
            "system": run_eval.SYSTEM,
            "output_config": {"effort": "low"},
            "messages": [{"role": "user", "content": f"TEXT:\n{item['context']}\n\nÎNTREBARE: {item['question']}"}],
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="+")
    ap.add_argument("--key-file", default=None)
    ap.add_argument("--poll", type=int, default=60, help="seconds between status polls")
    ap.add_argument("--dry-run", action="store_true", help="build the requests, count them, send nothing")
    a = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)
    items = [json.loads(l) for l in open("items.jsonl", encoding="utf-8")]
    reqs = [request_for(m, it) for m in a.models for it in items]
    print(f"{len(reqs)} requests: {len(a.models)} model(s) x {len(items)} items")
    if a.dry_run:
        print(json.dumps(reqs[0], ensure_ascii=False)[:600]); return 0
    client = anthropic.Anthropic(api_key=load_key(a.key_file))
    t0 = time.time()
    batch = client.messages.batches.create(requests=reqs)
    print(f"batch {batch.id} created, status {batch.processing_status}", flush=True)
    while True:
        b = client.messages.batches.retrieve(batch.id)
        c = b.request_counts
        print(f"[{time.strftime('%H:%M:%S')}] {b.processing_status} processing={c.processing} succeeded={c.succeeded} "
              f"errored={c.errored} expired={c.expired} canceled={c.canceled}", flush=True)
        if b.processing_status == "ended":
            break
        time.sleep(a.poll)
    replies = {}
    for res in client.messages.batches.results(batch.id):
        if res.result.type == "succeeded":
            msg = res.result.message
            if msg.stop_reason == "refusal":
                replies[res.custom_id] = ("ERROR", f"refusal: {getattr(msg.stop_details, 'category', None)}")
            else:
                text = "".join(b.text for b in msg.content if b.type == "text")
                replies[res.custom_id] = ("ok", text)
        else:
            err = getattr(res.result, "error", None)
            replies[res.custom_id] = ("ERROR", f"{res.result.type}: {str(err)[:150]}")
    os.makedirs("results", exist_ok=True)
    run_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for model in a.models:
        rows = []
        for it in items:
            kind, text = replies.get(re.sub(r"[^a-zA-Z0-9_-]", "-", f"{model}__{it['id']}")[:64], ("ERROR", "missing from batch results"))
            st = "ERROR" if kind == "ERROR" else run_eval.score(it, text)
            rows.append({"id": it["id"], "type": it["type"], "state": st, "reply": text[:400]})
        ans = [r for r in rows if r["type"] == "answerable" and r["state"] != "ERROR"]
        abs_ = [r for r in rows if r["type"] == "abstain" and r["state"] != "ERROR"]
        summary = {
            "model": model, "mode": "bare", "base": f"anthropic message batches api, batch {batch.id}", "run_at": run_at,
            "items": len(rows), "errors": sum(r["state"] == "ERROR" for r in rows), "secs": round(time.time() - t0),
            "answerable_correct": f"{sum(r['state'] == 'correct' for r in ans)} of {len(ans)}",
            "abstain_correct": f"{sum(r['state'] == 'correct' for r in abs_)} of {len(abs_)}",
            "hallucinations": sum(r["state"] == "hallucination" for r in abs_),
        }
        fn = f"results/{run_at[:10]}-bare-{re.sub(r'[^a-z0-9.]+', '-', model.lower())}.json"
        json.dump({"summary": summary, "rows": rows}, open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)
    print("=== BATCH EVAL COMPLETE ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
