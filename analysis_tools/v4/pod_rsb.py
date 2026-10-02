"""E1 (part 2): re-examine the Practical-POD headline "random sampling (RSB) matches or beats the tool in X% of bugs"
on the RepairLLaMA common split, when the 79 skipped-review negatives are treated as unknown.

Definitions copied from the POD replication scripts (figure_replication/scripts/produce_csvs_or_latex_tables.py and
produce_rsb_metrics.py at the pinned commit): per bug, tool effort = FP + 1 among predicted-correct patches if at
least one true positive is predicted, else N/A; RSB-c = smallest n with P(at least one correct in n random draws
without replacement) >= c; RSB wins a bug if tool effort is N/A or RSB <= effort. Only bugs with >= 1 correct patch count.

Worlds: released labels (as POD), verified-only (unknowns dropped), and exact [min, max] over every completion of the
unknowns (bugs are independent, so per-bug enumeration + a DP over the number of positive bugs is exact).
"""
import csv
import itertools
import json
import math
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "results/v2/practical_pod_common_split_candidates.csv"
DETS = ["yang_entropy_delta", "invalidator", "fixcheck", "llm4patchcorrect", "tian_dl4patchcorrectness"]
CONF = (85, 95)


def rsb(k, n, conf):
    if k <= 0:
        return None
    for m in range(1, n + 1):
        if 1 - Fraction(math.comb(n - k, m), math.comb(n, m)) >= Fraction(conf, 100):
            return m
    return n


def effort(labels, preds):
    tp = sum(1 for y, p in zip(labels, preds) if y == 1 and p == 1)
    fp = sum(1 for y, p in zip(labels, preds) if y == 0 and p == 1)
    return fp + 1 if tp else None


def rs_wins(labels, preds, conf):
    """None if the bug has no correct patch (excluded); else True/False."""
    r = rsb(sum(labels), len(labels), conf)
    if r is None:
        return None
    e = effort(labels, preds)
    return e is None or r <= e


def outcomes(rows, det, conf):
    """Set of (positive, win) outcomes for one bug over all completions of its unknowns."""
    known = [(1 if r["provenance_label"] == "correct" else 0) for r in rows if r["provenance_label"] != "unknown"]
    kp = [int(r[f"prediction::{det}"] == "correct") for r in rows if r["provenance_label"] != "unknown"]
    up = [int(r[f"prediction::{det}"] == "correct") for r in rows if r["provenance_label"] == "unknown"]
    out = set()
    for comp in itertools.product([0, 1], repeat=len(up)):
        w = rs_wins(known + list(comp), kp + up, conf)
        out.add((w is not None, bool(w)))
    return out


def ratio_bounds(per_bug):
    """Exact min/max of wins/positives: DP over bugs keyed by positives -> (min wins, max wins)."""
    dp = {0: (0, 0)}
    for opts in per_bug:
        nxt = {}
        for pos, (lo, hi) in dp.items():
            for p, w in opts:
                key = pos + p
                a, b = lo + (w and p), hi + (w and p)
                if key in nxt:
                    nxt[key] = (min(nxt[key][0], a), max(nxt[key][1], b))
                else:
                    nxt[key] = (a, b)
        dp = nxt
    vals = [(Fraction(lo, pos), Fraction(hi, pos), pos) for pos, (lo, hi) in dp.items() if pos]
    return float(min(v[0] for v in vals)), float(max(v[1] for v in vals)), sorted(dp)


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    by_bug = defaultdict(list)
    for r in rows:
        by_bug[r["bug_id"]].append(r)
    res = {"source": "Practical POD RepairLLaMA common split (169 patches, 50 bugs)",
           "max_unknowns_in_one_bug": max(sum(r["provenance_label"] == "unknown" for r in v) for v in by_bug.values()),
           "rows": []}
    for conf in CONF:
        for det in DETS:
            row = {"confidence": conf, "detector": det}
            for world in ("released", "verified_only"):
                wins = pos = 0
                for rs in by_bug.values():
                    if world == "released":
                        lab = [int(r["released_label"] == "correct") for r in rs]
                        pr = [int(r[f"prediction::{det}"] == "correct") for r in rs]
                    else:
                        keep = [r for r in rs if r["provenance_label"] != "unknown"]
                        lab = [int(r["provenance_label"] == "correct") for r in keep]
                        pr = [int(r[f"prediction::{det}"] == "correct") for r in keep]
                    if not lab:
                        continue
                    w = rs_wins(lab, pr, conf)
                    if w is None:
                        continue
                    pos += 1
                    wins += w
                row[world] = {"rsb_wins": wins, "positive_bugs": pos, "share": wins / pos}
            lo, hi, pos_set = ratio_bounds([outcomes(rs, det, conf) for rs in by_bug.values()])
            row["all_completions"] = {"share_min": lo, "share_max": hi, "positive_bug_counts_possible": pos_set[-3:]}
            res["rows"].append(row)
            print(conf, det, row["released"]["share"], row["verified_only"]["share"], [lo, hi], flush=True)
    out = ROOT / "results/v4/pod"
    out.mkdir(parents=True, exist_ok=True)
    (out / "pod_rsb_reexamination.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
