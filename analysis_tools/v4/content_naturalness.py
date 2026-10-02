"""D1: naturalness and entropy-delta baselines (ADDENDUM_V4_D1_NATURALNESS.md) with Qwen2.5-Coder-1.5B on GPU.

Writes results/v4/content_scores/{naturalness,entropy_delta}.jsonl and a metadata file. Per-text line-level
surprisal sums are cached in results/v4/content_scores/surprisal_lines.jsonl (resumable).
"""
import bisect
import difflib
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["HF_HOME"] = str(ROOT / "models" / "hf_cache")
os.environ["HF_HUB_CACHE"] = str(ROOT / "models" / "hf_cache" / "hub")
os.environ["HF_HUB_OFFLINE"] = "1"
import torch  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

OUT = ROOT / "results/v4/content_scores"
MODEL = "Qwen/Qwen2.5-Coder-1.5B"
MAXLEN = 2048
CACHE = OUT / "surprisal_lines.jsonl"


def tid(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def line_of_offsets(text):
    starts, pos = [], 0
    for line in text.split("\n"):
        starts.append(pos)
        pos += len(line) + 1
    return starts


def score_texts(texts, tok, model):
    """Returns {text_id: {"lines": {line_no: [sum_surprisal, n_tokens]}, "truncated": bool}}."""
    done = {}
    if CACHE.exists():
        for x in open(CACHE, encoding="utf-8"):
            if x.strip():
                r = json.loads(x)
                done[r["id"]] = r
    todo = [t for t in texts if tid(t) not in done]
    ntok = {t: min(len(tok(t, add_special_tokens=False)["input_ids"]), MAXLEN) for t in todo}
    todo.sort(key=lambda t: ntok[t])
    print(f"{len(done)} cached, {len(todo)} to score", flush=True)
    budget = 3072  # padded tokens per batch (fp32 logits over a 152k vocabulary must fit in 12 GB)
    with open(CACHE, "a", encoding="utf-8") as f, torch.no_grad():
        i = 0
        while i < len(todo):
            bs = 1
            while i + bs < len(todo) and (bs + 1) * max(ntok[todo[i + bs]], 1) <= budget:
                bs += 1  # todo is sorted by length, so the last item is the longest in the batch
            batch = todo[i:i + bs]
            enc = tok(batch, add_special_tokens=False, truncation=True, max_length=MAXLEN, padding=True,
                      return_offsets_mapping=True, return_tensors="pt")
            ids = enc["input_ids"].cuda()
            att = enc["attention_mask"].cuda()
            if i < 2000:
                print("batch", i, tuple(ids.shape), f"{torch.cuda.memory_allocated() / 2**30:.2f} GiB", flush=True)
            logits = model(input_ids=ids, attention_mask=att).logits.float()
            logp = torch.log_softmax(logits[:, :-1], dim=-1)
            s = -logp.gather(-1, ids[:, 1:].unsqueeze(-1)).squeeze(-1).cpu()
            for b, text in enumerate(batch):
                starts = line_of_offsets(text)
                offs = enc["offset_mapping"][b].tolist()
                mask = enc["attention_mask"][b].tolist()
                full = len(tok(text, add_special_tokens=False)["input_ids"])
                lines = {}
                for k in range(1, len(offs)):
                    if not mask[k]:
                        continue
                    ln = bisect.bisect_right(starts, offs[k][0]) - 1
                    acc = lines.setdefault(ln, [0.0, 0])
                    acc[0] += float(s[b, k - 1])
                    acc[1] += 1
                rec = {"id": tid(text), "lines": lines, "truncated": full > MAXLEN}
                done[rec["id"]] = rec
                f.write(json.dumps(rec) + "\n")
            f.flush()
            i += len(batch)
            if len(done) % 2000 < len(batch):
                print(f"{i}/{len(todo)}", flush=True)
    return done


def mean_over(rec, line_set=None):
    tot = n = 0
    for ln, (sm, c) in rec["lines"].items():
        if line_set is None or int(ln) in line_set:
            tot += sm
            n += c
    return (tot / n) if n else None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ctx = {}
    for line in open(ROOT / "results/contract_step1/contexts.jsonl", encoding="utf-8"):
        r = json.loads(line)
        ctx[r["context_id"]] = r.get("anchor") or ""
    cands = []
    for line in open(ROOT / "results/contract_step1/decision_candidates.jsonl", encoding="utf-8"):
        r = json.loads(line)
        cands.append((r["candidate_id"], r["context_id"], r["patch"]))
    texts = sorted({t for _, c, p in cands for t in (p, ctx[c])})
    path = next((ROOT / "models/hf_cache/hub/models--Qwen--Qwen2.5-Coder-1.5B/snapshots").iterdir())
    revision = path.name
    tok = AutoTokenizer.from_pretrained(path)
    tok.padding_side = "right"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(path, torch_dtype=torch.float16).cuda().eval()
    rec = score_texts(texts, tok, model)
    nat, ed = [], []
    for cid, c, p in cands:
        rp, ra = rec[tid(p)], rec[tid(ctx[c])]
        m_p = mean_over(rp)
        nat.append({"candidate_id": cid, "score": -m_p if m_p is not None else 0.0})
        a_lines = [x.rstrip() for x in ctx[c].split("\n")]
        p_lines = [x.rstrip() for x in p.split("\n")]
        removed, added = set(), set()
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a_lines, p_lines, autojunk=False).get_opcodes():
            if op in ("replace", "delete"):
                removed.update(range(i1, i2))
            if op in ("replace", "insert"):
                added.update(range(j1, j2))
        if not removed and not added:
            delta = 0.0
        else:
            R = mean_over(ra, removed) if removed else mean_over(ra)
            A = mean_over(rp, added) if added else mean_over(rp)
            if R is None and A is None:
                delta = 0.0
            else:
                R = R if R is not None else mean_over(ra)
                A = A if A is not None else mean_over(rp)
                delta = (R or 0.0) - (A or 0.0)
        ed.append({"candidate_id": cid, "score": delta})
    for name, rows in (("naturalness", nat), ("entropy_delta", ed)):
        with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    meta = {"model": MODEL, "revision": revision, "max_tokens": MAXLEN,
            "texts": len(texts), "truncated_texts": sum(1 for t in texts if rec[tid(t)]["truncated"]),
            "candidates": len(cands), "addendum_sha256": hashlib.sha256((ROOT / "ADDENDUM_V4_D1_NATURALNESS.md").read_bytes()).hexdigest(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "torch": torch.__version__, "device": torch.cuda.get_device_name(0)}
    (OUT / "naturalness.meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
