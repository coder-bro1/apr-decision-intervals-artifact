"""K1 latency: wall-clock time per candidate for each selector, measured on this machine (RTX 3060 12 GB, 16 GB RAM)
on a fixed random sample of 1,000 Defects4J candidates (seed 20260929). Writes results/v4/cost/latency.json, which
k1_cost.py reads. Challenger = feature extraction + the three logistic stages (CPU). CodeT5+, naturalness and APPT =
model inference on GPU (model loading excluded and reported separately)."""
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["HF_HOME"] = str(ROOT / "models" / "hf_cache")
import numpy as np  # noqa: E402
import torch  # noqa: E402

OUT = ROOT / "results/v4/cost"


def main():
    import run_evidence_pilot_step2 as S
    views, _, _, training, _ = S.load_inputs()
    rng = random.Random(20260929)
    idx = rng.sample(range(len(views)), 1000)
    sample = [views[i] for i in idx]
    res = {"sample": len(sample), "device": torch.cuda.get_device_name(0)}
    # challenger: features + 3 logistic stages (fit once on training folds, time only the scoring)
    feats = S.ProvenanceFeatures(views)
    x = feats.transform(views)
    models = []
    for stage in S.STAGES:
        rows = [i for i, r in enumerate(training) if r[stage] is not None]
        models.append(S.fit_logistic(x[rows], np.array([training[i][stage] for i in rows], dtype=np.int8), 1.0))
    t0 = time.perf_counter()
    xs = feats.transform(sample)
    p = np.ones(len(sample))
    for m in models:
        p = p * m.predict_proba(xs)[:, 1]
    res["challenger_ms_per_candidate"] = 1000 * (time.perf_counter() - t0) / len(sample)
    ctx = {}
    for line in open(ROOT / "results/contract_step1/contexts.jsonl", encoding="utf-8"):
        r = json.loads(line)
        ctx[r["context_id"]] = r.get("anchor") or ""
    pairs = [(ctx[v.context_id], v.patch) for v in sample]
    # CodeT5+ similarity (default HF cache, as in D1)
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer
    c5 = str(Path.home() / ".cache/huggingface/hub")  # CodeT5+ lives in the default cache (as in D1)
    t0 = time.perf_counter()
    tok5 = AutoTokenizer.from_pretrained("Salesforce/codet5p-110m-embedding", trust_remote_code=True, local_files_only=True, cache_dir=c5)
    m5 = AutoModel.from_pretrained("Salesforce/codet5p-110m-embedding", trust_remote_code=True, local_files_only=True, cache_dir=c5).cuda().eval()
    res["codet5_load_s"] = time.perf_counter() - t0
    torch.cuda.synchronize(); t0 = time.perf_counter()
    with torch.no_grad():
        for i in range(0, len(pairs), 64):
            b = [t for a, c in pairs[i:i + 64] for t in (a, c)]
            enc = tok5(b, padding=True, truncation=True, max_length=512, return_tensors="pt").to("cuda")
            m5(**enc)
    torch.cuda.synchronize()
    res["codet5_ms_per_candidate"] = 1000 * (time.perf_counter() - t0) / len(pairs)
    del m5; torch.cuda.empty_cache()
    # naturalness (Qwen2.5-Coder-1.5B, fp16), one candidate at a time as a deployed selector would
    snap = next((ROOT / "models/hf_cache/hub/models--Qwen--Qwen2.5-Coder-1.5B/snapshots").iterdir())
    t0 = time.perf_counter()
    tq = AutoTokenizer.from_pretrained(snap)
    mq = AutoModelForCausalLM.from_pretrained(snap, torch_dtype=torch.float16).cuda().eval()
    res["naturalness_load_s"] = time.perf_counter() - t0
    torch.cuda.synchronize(); t0 = time.perf_counter()
    with torch.no_grad():
        for _, c in pairs[:300]:
            ids = tq(c, return_tensors="pt", truncation=True, max_length=2048)["input_ids"].cuda()
            mq(input_ids=ids)
    torch.cuda.synchronize()
    res["naturalness_ms_per_candidate"] = 1000 * (time.perf_counter() - t0) / 300
    del mq; torch.cuda.empty_cache()
    # APPT (released checkpoint), batch 32 as in appt_scores.py
    import appt_scores as A
    t0 = time.perf_counter()
    model, tok = A.load_model()
    res["appt_load_s"] = time.perf_counter() - t0
    ap = [tuple(map(A.lex, A.regions(a, c))) for a, c in pairs]
    torch.cuda.synchronize(); t0 = time.perf_counter()
    A.p_overfit(model, tok, ap)
    torch.cuda.synchronize()
    res["appt_ms_per_candidate"] = 1000 * (time.perf_counter() - t0) / len(ap)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latency.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
