"""E1 + C3: POD common split (169 patches; 79 released negatives lack a completed review -> unknown).

(a) balanced accuracy (BA) per detector on the 90 reviewed patches with a bug-cluster bootstrap 95% CI (10,000 draws);
(b) label-polarity check (BA of the inverted predictions; per-class recall);
(c) exact bounds of per-detector BA and of every pairwise BA difference over all completions of the 79 unknowns
    (for each number k of truly-correct unknowns the quantity is linear in the unknown labels, so sorting is exact;
    then min/max over k); verified against brute force on random small instances in test_pod.py;
(d) which released-label rankings stay identified.
"""
import csv
import json
import random
import sys
from collections import defaultdict
from fractions import Fraction
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "results/v2/practical_pod_common_split_candidates.csv"
DETS = ["yang_entropy_delta", "invalidator", "fixcheck", "llm4patchcorrect", "tian_dl4patchcorrectness"]


def load():
    return list(csv.DictReader(open(SRC, encoding="utf-8")))


def ba(rows, labels, det, invert=False):
    tp = tn = p = n = 0
    for r, y in zip(rows, labels):
        pred_correct = (r[f"prediction::{det}"] == "correct") != invert
        if y == 1:
            p += 1
            tp += pred_correct
        else:
            n += 1
            tn += not pred_correct
    return Fraction(tp, p) / 2 + Fraction(tn, n) / 2, (Fraction(tp, p), Fraction(tn, n))


def pred_vec(rows, det):
    return [1 if r[f"prediction::{det}"] == "correct" else 0 for r in rows]


def diff_bounds(known_y, known_a, known_b, unk_a, unk_b):
    """Exact [min,max] of BA(a)-BA(b) over labelings of the unknowns. Predictions are 1=correct, 0=overfitting.
    Use known_b = unk_b = zeros-vector-free call with b=None for single-detector BA bounds."""
    P0 = sum(known_y)
    N0 = len(known_y) - P0
    tp_a = sum(1 for y, a in zip(known_y, known_a) if y == 1 and a == 1)
    tn_a = sum(1 for y, a in zip(known_y, known_a) if y == 0 and a == 0)
    tp_b = sum(1 for y, b in zip(known_y, known_b) if y == 1 and b == 1) if known_b is not None else 0
    tn_b = sum(1 for y, b in zip(known_y, known_b) if y == 0 and b == 0) if known_b is not None else 0
    m = len(unk_a)
    lo = hi = None
    for k in range(m + 1):
        p, n = P0 + k, N0 + m - k
        if p == 0 or n == 0:
            continue
        # all unknowns incorrect contribute to TN; each unknown moved to 'correct' adds w_u
        tn_all_a = sum(1 for a in unk_a if a == 0)
        tn_all_b = sum(1 for b in unk_b if b == 0) if unk_b is not None else 0
        base = Fraction(tp_a - tp_b, p) / 2 + Fraction(tn_a + tn_all_a - tn_b - tn_all_b, n) / 2
        w = []
        for i in range(m):
            a, b = unk_a[i], (unk_b[i] if unk_b is not None else None)
            dtp = a - (b if b is not None else 0)
            dtn = (1 - a) - ((1 - b) if b is not None else 0)
            w.append(Fraction(dtp, p) / 2 - Fraction(dtn, n) / 2)
        w.sort()
        mn = base + sum(w[:k])
        mx = base + (sum(w[m - k:]) if k else 0)
        lo = mn if lo is None else min(lo, mn)
        hi = mx if hi is None else max(hi, mx)
    return lo, hi


def main():
    rows = load()
    known = [r for r in rows if r["provenance_label"] in ("correct", "incorrect")]
    unk = [r for r in rows if r["provenance_label"] == "unknown"]
    ky = [1 if r["provenance_label"] == "correct" else 0 for r in known]
    released = [1 if r["released_label"] == "correct" else 0 for r in rows]
    res = {"patches": len(rows), "reviewed": len(known), "reviewed_correct": sum(ky),
           "reviewed_incorrect": len(ky) - sum(ky), "unknown": len(unk), "detectors": {}, "pairs": []}
    # bug-cluster bootstrap over reviewed patches
    by_bug = defaultdict(list)
    for i, r in enumerate(known):
        by_bug[r["bug_id"]].append(i)
    bugs = sorted(by_bug)
    rng = random.Random(20260929)
    boot = {d: [] for d in DETS}
    draws = 0
    while draws < 10000:
        pick = [rng.choice(bugs) for _ in bugs]
        idx = [i for b in pick for i in by_bug[b]]
        ys = [ky[i] for i in idx]
        if 0 in (sum(ys), len(ys) - sum(ys)):
            continue
        rs = [known[i] for i in idx]
        for d in DETS:
            boot[d].append(float(ba(rs, ys, d)[0]))
        draws += 1
    for d in DETS:
        b_rev, (tpr, tnr) = ba(known, ky, d)
        b_inv, _ = ba(known, ky, d, invert=True)
        b_rel, _ = ba(rows, released, d)
        s = sorted(boot[d])
        lo, hi = diff_bounds(ky, pred_vec(known, d), None, pred_vec(unk, d), None)
        res["detectors"][d] = {
            "BA_released_labels": float(b_rel), "BA_reviewed_only": float(b_rev),
            "BA_reviewed_ci95": [s[249], s[9749]], "recall_correct": float(tpr), "recall_overfitting": float(tnr),
            "BA_inverted_predictions_reviewed": float(b_inv),
            "BA_exact_bounds_all_169": [float(lo), float(hi)],
            "predicted_correct_share": sum(pred_vec(rows, d)) / len(rows)}
    for a, b in combinations(DETS, 2):
        lo, hi = diff_bounds(ky, pred_vec(known, a), pred_vec(known, b), pred_vec(unk, a), pred_vec(unk, b))
        d_rel = ba(rows, released, a)[0] - ba(rows, released, b)[0]
        d_rev = ba(known, ky, a)[0] - ba(known, ky, b)[0]
        res["pairs"].append({"a": a, "b": b, "released_diff_pp": float(100 * d_rel), "reviewed_diff_pp": float(100 * d_rev),
                             "exact_bounds_pp": [float(100 * lo), float(100 * hi)],
                             "identified": bool(lo > 0 or hi < 0)})
    out = ROOT / "results/v4/pod"
    out.mkdir(parents=True, exist_ok=True)
    (out / "pod_analysis.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
