"""G1 CodeT5+ similarity (secondary comparison S3), computed exactly as the Defects4J D1 baseline (content_codet5.py):
Salesforce/codet5p-110m-embedding loaded by name from the default local Hugging Face cache (no download), cosine
similarity between each G1 candidate and its buggy method. (g1_content_scores.py loaded it by folder path, which
transformers misidentified as another model type; naturalness from that script is unaffected.)
Writes results/g1/codet5_similarity.jsonl.
"""
import json
import sys
from pathlib import Path

import torch
from transformers import AutoModel, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import g1_pools as G  # noqa: E402  (does not change the Hugging Face cache location)

MODEL = "Salesforce/codet5p-110m-embedding"


def main():
    data, _ = G.build(G.load_generations())
    cands = [(o.cid, data.ctx_anchor[o.ctx], o.patch) for o in data.occ.values()]
    tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True, local_files_only=True)
    model = AutoModel.from_pretrained(MODEL, trust_remote_code=True, local_files_only=True).cuda().eval()
    texts = sorted({t for _, a, p in cands for t in (a, p) if t})
    emb = {}
    with torch.no_grad():
        for i in range(0, len(texts), 64):
            b = texts[i:i + 64]
            enc = tok(b, padding=True, truncation=True, max_length=512, return_tensors="pt").to("cuda")
            emb.update(zip(b, torch.nn.functional.normalize(model(**enc), dim=-1).float().cpu()))
    with open(G.G1 / "codet5_similarity.jsonl", "w", encoding="utf-8") as f:
        for cid, a, p in cands:
            f.write(json.dumps({"candidate_id": cid, "score": float(torch.dot(emb[p], emb[a])) if p else -1.0}) + "\n")
    print(f"G1 CodeT5+ similarity written for {len(cands)} candidates ({len(texts)} texts)")


if __name__ == "__main__":
    main()
