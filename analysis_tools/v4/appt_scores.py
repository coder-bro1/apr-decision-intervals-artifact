"""D2/D3: APPT (Zhang et al., TSE 2024) with the authors' released checkpoint, run as is on our candidates.

Released checkpoint: output/bert_small_cat_headTail_0/checkpoint (BERT-base-uncased + BiLSTM, 'cat' splicing,
head+tail truncation to 512 tokens, trained on fold 0 of the authors' Small Defects4J dataset).
Polarity: the authors' train.py and test.py map is_correct 1 -> 0 and 0 -> 1 before BCE, so sigmoid(output) is
P(overfitting). Our score (higher is better) = 1 - P(overfitting).
Input format (inferred from the released pickles): the buggy and patched code regions of the diff hunks with 3 lines
of context, lower-cased, lexical tokens separated by single spaces. A text-identical patch uses the whole method.
Gate: the checkpoint must reproduce a sensible AUC on the authors' own Small test fold 0 before our scores are used.
Caveat to report: APPT was trained on classic-APR patches for Defects4J bugs that overlap ours.
"""
import difflib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["HF_HOME"] = str(ROOT / "models" / "hf_cache")
os.environ["HF_HUB_CACHE"] = str(ROOT / "models" / "hf_cache" / "hub")
APPT = ROOT / "external_artifacts/sota/APPT"
CKPT = ROOT / "external_artifacts/sota/APPT_model/output/bert_small_cat_headTail_0/checkpoint"
sys.path.insert(0, str(APPT / "code"))
import pickle  # noqa: E402

import torch  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

OUT = ROOT / "results/v4/content_scores"
TOKEN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*|\d+(?:\.\d+)?[A-Za-z]?|\S")


def lex(text):
    return " ".join(TOKEN.findall(text))


def regions(buggy, patched, ctx=3):
    a, b = buggy.split("\n"), patched.split("\n")
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ra, rb = [], []
    for group in sm.get_grouped_opcodes(ctx):
        i1, i2 = group[0][1], group[-1][2]
        j1, j2 = group[0][3], group[-1][4]
        ra.extend(a[i1:i2])
        rb.extend(b[j1:j2])
    if not ra and not rb:
        return buggy, patched
    return "\n".join(ra), "\n".join(rb)


def head_tail(tok, text, max_length=512):
    enc = tok(text)
    ids, att = enc["input_ids"], enc["attention_mask"]
    if len(ids) > max_length:
        h = max_length // 2
        ids, att = ids[:h] + ids[-h:], att[:h] + att[-h:]
    else:
        ids = ids + [0] * (max_length - len(ids))
        att = att + [0] * (max_length - len(att))
    return ids, att


def load_model():
    from configs import Config
    from Model import Model
    cfg = Config()
    cfg.model_path = "bert-base-uncased"
    cfg.splicingMethod = "cat"
    cfg.cutMethod = "headTail"
    model = Model(cfg)
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    state = ck["model_state_dict"] if "model_state_dict" in ck else ck
    # A constant buffer that older transformers versions saved in checkpoints; newer BertModel no longer registers it.
    state = {k: v for k, v in state.items() if k != "bert.embeddings.position_ids"}
    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing or unexpected:
        raise ValueError(f"checkpoint mismatch: missing={missing[:5]} unexpected={unexpected[:5]}")
    return model.cuda().eval(), AutoTokenizer.from_pretrained("bert-base-uncased")


def p_overfit(model, tok, pairs, bs=32):
    out = []
    with torch.no_grad():
        for i in range(0, len(pairs), bs):
            chunk = pairs[i:i + bs]
            e1 = [head_tail(tok, a.lower()) for a, _ in chunk]
            e2 = [head_tail(tok, b.lower()) for _, b in chunk]
            t = lambda xs, k: torch.tensor([x[k] for x in xs]).cuda()
            logits = model(t(e1, 0), t(e1, 1), t(e2, 0), t(e2, 1))
            out.extend(torch.sigmoid(logits.float()).cpu().tolist())
    return out


def main():
    model, tok = load_model()
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "appt.gate.json").exists():
        gate = json.loads((OUT / "appt.gate.json").read_text())
    else:
        b, f, y = pickle.load(open(APPT / "dataset/Small/data_code_test_0.pkl", "rb"))
        po = p_overfit(model, tok, list(zip(map(str, b), map(str, f))))
        gate = {"fold0_test_patches": len(y),
                "auc_correct_vs_1_minus_p_overfit": float(roc_auc_score(list(y), [1 - p for p in po]))}
        (OUT / "appt.gate.json").write_text(json.dumps(gate, indent=1))
    print("gate", gate, flush=True)
    if gate["auc_correct_vs_1_minus_p_overfit"] < 0.6:
        raise SystemExit("APPT gate failed: the released checkpoint does not reproduce on its own test fold")
    ctx = {}
    for line in open(ROOT / "results/contract_step1/contexts.jsonl", encoding="utf-8"):
        r = json.loads(line)
        ctx[r["context_id"]] = r.get("anchor") or ""
    cands = []
    for line in open(ROOT / "results/contract_step1/decision_candidates.jsonl", encoding="utf-8"):
        r = json.loads(line)
        cands.append((r["candidate_id"], r["context_id"], r["patch"]))
    # Resumable: scores are appended to appt.partial.jsonl in chunks; a restart skips candidates already scored.
    partial = OUT / "appt.partial.jsonl"
    done = {}
    if partial.exists():
        for line in open(partial, encoding="utf-8"):
            if line.strip():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a line cut off by a crash; that candidate is simply rescored
                done[r["candidate_id"]] = r["p_overfitting"]
    todo = [(cid, c, p) for cid, c, p in cands if cid not in done]
    print(f"APPT scoring: {len(done)} already scored, {len(todo)} to go", flush=True)
    chunk = 2048
    with open(partial, "a", encoding="utf-8") as fh:
        for s in range(0, len(todo), chunk):
            part = todo[s:s + chunk]
            pairs = [tuple(map(lex, regions(ctx[c], p))) for _, c, p in part]
            for (cid, _, _), p in zip(part, p_overfit(model, tok, pairs)):
                fh.write(json.dumps({"candidate_id": cid, "p_overfitting": p}) + "\n")
                done[cid] = p
            fh.flush()
            print(f"APPT {len(done)}/{len(cands)} ({100 * len(done) / len(cands):.1f}%)", flush=True)
    with open(OUT / "appt.jsonl", "w", encoding="utf-8") as fh:
        for cid, _, _ in cands:
            p = done[cid]
            fh.write(json.dumps({"candidate_id": cid, "score": 1 - p, "p_overfitting": p}) + "\n")
    (OUT / "appt.meta.json").write_text(json.dumps({"checkpoint": str(CKPT.relative_to(ROOT)), "gate": gate,
                                                    "candidates": len(cands)}, indent=1))


if __name__ == "__main__":
    main()
