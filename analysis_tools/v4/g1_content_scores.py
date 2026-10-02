"""G1 content scores for the secondary comparisons S3/S4 (PROTOCOL_G1_FRESH_CAMPAIGN.md s.4): CodeT5+ similarity (as in
content_codet5.py) and naturalness (as in ADDENDUM_V4_D1_NATURALNESS.md), computed on the G1 candidates only.
Writes results/g1/{codet5_similarity,naturalness}.jsonl keyed by G1 candidate id. The naturalness cache is separate
from the Defects4J one (results/g1/surprisal_lines.jsonl), so no frozen D4J output changes.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["HF_HOME"] = str(ROOT / "models" / "hf_cache")
import torch  # noqa: E402
import content_naturalness as CN  # noqa: E402
import g1_pools as G  # noqa: E402

OUT = ROOT / "results/g1"


def main():
    rows = G.load_generations()
    data, _ = G.build(rows)
    cands = [(o.cid, data.ctx_anchor[o.ctx], o.patch) for o in data.occ.values()]
    # naturalness: mean token log-probability of the candidate method (Qwen2.5-Coder-1.5B, same code path as D1)
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer
    CN.CACHE = OUT / "surprisal_lines.jsonl"
    path = next((ROOT / "models/hf_cache/hub/models--Qwen--Qwen2.5-Coder-1.5B/snapshots").iterdir())
    tok = AutoTokenizer.from_pretrained(path)
    tok.padding_side = "right"
    model = AutoModelForCausalLM.from_pretrained(path, torch_dtype=torch.float16).cuda().eval()
    texts = sorted({p for _, _, p in cands if p})
    rec = CN.score_texts(texts, tok, model)
    with open(OUT / "naturalness.jsonl", "w", encoding="utf-8") as f:
        for cid, _, p in cands:
            m = CN.mean_over(rec[CN.tid(p)]) if p else None
            f.write(json.dumps({"candidate_id": cid, "score": -m if m is not None else -1e9}) + "\n")
    del model
    torch.cuda.empty_cache()
    # CodeT5+ 110M embedding cosine similarity between the candidate and its buggy method (same model as D1)
    # the same locally cached snapshot D1 used (default HF cache on C:; loaded by path, no download)
    name = next((Path.home() / ".cache/huggingface/hub/models--Salesforce--codet5p-110m-embedding/snapshots").iterdir())
    tok5 = AutoTokenizer.from_pretrained(name, trust_remote_code=True, local_files_only=True)
    m5 = AutoModel.from_pretrained(name, trust_remote_code=True, local_files_only=True).cuda().eval()
    emb = {}
    allt = sorted({t for _, a, p in cands for t in (a, p) if t})
    with torch.no_grad():
        for i in range(0, len(allt), 64):
            b = allt[i:i + 64]
            enc = tok5(b, padding=True, truncation=True, max_length=512, return_tensors="pt").to("cuda")
            v = torch.nn.functional.normalize(m5(**enc), dim=-1).float().cpu()
            emb.update(zip(b, v))
    with open(OUT / "codet5_similarity.jsonl", "w", encoding="utf-8") as f:
        for cid, a, p in cands:
            s = float(torch.dot(emb[p], emb[a])) if p else -1.0
            f.write(json.dumps({"candidate_id": cid, "score": s}) + "\n")
    print(f"G1 content scores written for {len(cands)} candidates", flush=True)


if __name__ == "__main__":
    main()
