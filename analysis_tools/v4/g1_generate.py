"""G1 generation (PROTOCOL_G1_FRESH_CAMPAIGN.md s.2-3): Qwen2.5-Coder-7B-Instruct, 4-bit NF4, 10 samples per bug.

Resumable: one JSON line per bug in results/g1/generations.jsonl; bugs already present are skipped. No labels,
tests or developer fixes are read here.
"""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["HF_HOME"] = str(ROOT / "models" / "hf_cache")
os.environ["HF_HUB_OFFLINE"] = "1"
import torch  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # noqa: E402

OUT = ROOT / "results/g1"
SNAP = ROOT / "models/hf_cache/hub/models--Qwen--Qwen2.5-Coder-7B-Instruct/snapshots"
SYSTEM = "You are an expert Java developer."
USER = ("The following Java method contains a bug. Fix the bug and return the complete fixed method only, "
        "in one ```java code block, with no explanation.\n\n```java\n{method}\n```")
N, TEMP, TOP_P = 10, 0.8, 0.95
FENCE_JAVA = re.compile(r"```java[ \t]*\n(.*?)```", re.S)
FENCE_ANY = re.compile(r"```[^\n]*\n(.*?)```", re.S)


def extract(text):
    m = FENCE_JAVA.search(text) or FENCE_ANY.search(text)
    return (m.group(1) if m else text).strip()


def contexts():
    rows = [json.loads(line) for line in open(ROOT / "results/contract_step1/contexts.jsonl", encoding="utf-8")]
    best = {}
    for r in rows:
        key = (len("".join(r["anchor"].split())), r["context_id"])
        if r["bug_id"] not in best or key < best[r["bug_id"]][0]:
            best[r["bug_id"]] = (key, r)
    return [best[b][1] for b in sorted(best)]


def load_done(path):
    """bug_ids of complete records. A torn or NUL-filled tail left by a hard crash is cut off (the file is truncated
    back to the last complete line) so appending continues cleanly."""
    done = set()
    if not path.exists():
        return done
    data = path.read_bytes()
    pos = keep = 0
    while True:
        nl = data.find(b"\n", pos)
        if nl < 0:
            break  # bytes after the last newline = an incomplete record
        line = data[pos:nl].strip()
        if line:
            try:
                done.add(json.loads(line.decode("utf-8"))["bug_id"])
            except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                break  # damaged record: keep everything before it, redo from here
        pos = keep = nl + 1
    if keep < len(data):
        with open(path, "r+b") as fh:
            fh.truncate(keep)
        print(f"G1 resume: cut {len(data) - keep} bytes of an incomplete record from the end of {path.name}", flush=True)
    return done


def split_for(n_prompt):
    """Samples per generate() call, fixed by prompt length so a relaunch uses the same split (the prefill of
    num_return_sequences x prompt tokens dominates peak memory on the 12 GB card)."""
    if n_prompt <= 2500:
        return (5, 5)
    if n_prompt <= 6000:
        return (2, 2, 2, 2, 2)
    return (1,) * N


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "generations.jsonl"
    done = load_done(path)
    snap = next(SNAP.iterdir())
    tok = AutoTokenizer.from_pretrained(snap)
    q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(snap, quantization_config=q, device_map="cuda:0").eval()
    # The snapshot's generation_config.json adds top_k=20 and repetition_penalty=1.1. The protocol (s.3) samples with
    # temperature 0.8 and top-p 0.95 only, so both extras are switched off here and passed explicitly on every call.
    model.generation_config.top_k = 0
    model.generation_config.temperature = TEMP
    model.generation_config.top_p = TOP_P
    model.generation_config.repetition_penalty = 1.0
    gen_kw = dict(do_sample=True, temperature=TEMP, top_p=TOP_P, top_k=0, repetition_penalty=1.0,
                  pad_token_id=tok.eos_token_id)
    ctxs = contexts()
    meta = {"model": "Qwen/Qwen2.5-Coder-7B-Instruct", "revision": snap.name, "quantization": "nf4/bf16",
            "samples": N, "temperature": TEMP, "top_p": TOP_P, "top_k": "disabled (0)", "repetition_penalty": 1.0,
            "effective_generation_config": model.generation_config.to_dict(), "bugs": len(ctxs),
            "protocol_sha256": hashlib.sha256((ROOT / "PROTOCOL_G1_FRESH_CAMPAIGN.md").read_bytes()).hexdigest(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "torch": torch.__version__}
    (OUT / "generation_meta.json").write_text(json.dumps(meta, indent=1, default=str))
    print(f"G1: {len(done)} bugs already generated, {len(ctxs) - len(done)} to go", flush=True)
    with open(path, "a", encoding="utf-8") as f:
        for idx, c in enumerate(ctxs):
            if c["bug_id"] in done:
                continue
            anchor = c["anchor"].strip()
            msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER.format(method=anchor)}]
            prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            enc = tok(prompt, return_tensors="pt").to("cuda:0")
            n_prompt = enc["input_ids"].shape[1]
            n_anchor = len(tok(anchor)["input_ids"])
            max_new = min(2048, 2 * n_anchor + 128)
            split, oom = split_for(n_prompt), False
            t0 = time.time()
            while True:
                torch.manual_seed(20260930 + idx)
                torch.cuda.empty_cache()
                outs = []
                try:
                    with torch.no_grad():
                        for part in split:
                            g = model.generate(**enc, max_new_tokens=max_new, num_return_sequences=part, **gen_kw)
                            outs += [tok.decode(s[n_prompt:], skip_special_tokens=True) for s in g]
                    break
                except torch.cuda.OutOfMemoryError:
                    if split == (1,) * N:
                        raise
                    split, oom = (1,) * N, True  # same seed, one sample per call; recorded in the record
                    print(f"  {c['bug_id']}: GPU out of memory, retrying one sample per call", flush=True)
            rec = {"bug_id": c["bug_id"], "context_id": c["context_id"], "bug_index": idx, "anchor": anchor,
                   "prompt_tokens": n_prompt, "max_new_tokens": max_new, "split": list(split), "oom_retry": oom,
                   "seconds": round(time.time() - t0, 1),
                   "samples": [{"index": i, "raw": o, "patch": extract(o)} for i, o in enumerate(outs)]}
            f.write(json.dumps(rec) + "\n")
            f.flush()
            os.fsync(f.fileno())
            done.add(c["bug_id"])
            print(f"G1 {len(done)}/{len(ctxs)} ({100 * len(done) / len(ctxs):.1f}%)  {c['bug_id']}  "
                  f"{rec['seconds']}s  prompt {n_prompt} tok", flush=True)


if __name__ == "__main__":
    main()
