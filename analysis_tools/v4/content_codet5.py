"""D1 content-aware baseline: CodeT5+ (110M embedding) cosine similarity between each patch and its buggy method.

Higher similarity = more conservative edit (the 'minimal change' prior used as a zero-shot selector).
Model: locally cached Salesforce/codet5p-110m-embedding (no download). Writes results/v4/content_scores/.
"""
import hashlib
import json
import sys
from pathlib import Path

import torch
from transformers import AutoModel, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/v4/content_scores"
MODEL = "Salesforce/codet5p-110m-embedding"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ctx = {}
    with open(ROOT / "results/contract_step1/contexts.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            ctx[r["context_id"]] = r.get("anchor") or ""
    cands = []
    with open(ROOT / "results/contract_step1/decision_candidates.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            cands.append((r["candidate_id"], r["context_id"], r["patch"]))
    texts = sorted({t for _, c, p in cands for t in (p, ctx[c])})
    tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True, local_files_only=True)
    model = AutoModel.from_pretrained(MODEL, trust_remote_code=True, local_files_only=True).cuda().eval()
    emb = {}
    bs = 64
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            batch = texts[i:i + bs]
            enc = tok(batch, padding=True, truncation=True, max_length=512, return_tensors="pt").to("cuda")
            vec = model(**enc)
            vec = torch.nn.functional.normalize(vec, dim=-1).float().cpu()
            for t, v in zip(batch, vec):
                emb[t] = v
            if i % (bs * 100) == 0:
                print(f"{i}/{len(texts)}", flush=True)
    with open(OUT / "codet5_similarity.jsonl", "w", encoding="utf-8") as f:
        for cid, c, p in cands:
            s = float(torch.dot(emb[p], emb[ctx[c]]))
            f.write(json.dumps({"candidate_id": cid, "score": s}) + "\n")
    meta = {"model": MODEL, "texts": len(texts), "candidates": len(cands), "max_length": 512,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "torch": torch.__version__, "device": torch.cuda.get_device_name(0)}
    (OUT / "codet5_similarity.meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
