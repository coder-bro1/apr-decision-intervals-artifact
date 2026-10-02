"""E2 analysis (ADDENDUM_V4_E2_PREVARANK.md): distribution of PrevaRank's measured utility over input orders.

Labels: v4 identity-class labels (bug unit, AST identity, known-wins, N-a) under E0 and E1, joined to the PrevaRank
ledgers through each v4 candidate's legacy ids. Per run: success@1 interval (unknown top -> [0, 1]) with equal-bug
weighting over the 465 mixed pools; paired shared-label bounds of success@1(run) - success@1(canonical); check T
(ties in historical value and category follow input order).
"""
import json
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402

REF = {"canonical_v4": ROOT / "results/v2/prevarank_llm_mixed_evaluation_ledger.jsonl",
       "stable_hash_v1": ROOT / "results/v2/prevarank_llm_stable_hash_evaluation_ledger.jsonl"}
PERM = ROOT / "results/v4/prevarank"


def class_labels(data, ev):
    """legacy candidate id -> (class key, label) via v4 bug/AST classes."""
    legacy = {}
    for r in V.jsonl(V.INPUTS["evaluation_evidence"]):
        for lk in r["legacy_candidate_ids"]:
            legacy[lk] = r["candidate_id"]
    out = {}
    for bug, classes in V.build_pools(data, "bug", "ast").values():
        for kl in classes:
            y, _ = V.class_label(kl.members, ev, "known_wins")
            if y is None and any(data.occ[m].noop for m in kl.members):
                y = 0
            for m in kl.members:
                out[m] = (bug + "|" + kl.key, y)
    return {lk: out[ob] for lk, ob in legacy.items() if ob in out}


def load(path):
    pools = defaultdict(list)
    for r in V.jsonl(path):
        pools[(r["bug_id"], r["pool_id"])].append(r)
    return pools


def tops(pools, lab):
    """pool -> set of class keys at the top rank (identical programs share a rank)."""
    res = {}
    for k, rows in pools.items():
        best = min(r["prevarank_rank"] for r in rows)
        res[k] = {lab[r["candidate_id"]][0] for r in rows if r["prevarank_rank"] == best and r["candidate_id"] in lab}
    return res


def success_interval(pools, lab, labels_of):
    per_bug = defaultdict(list)
    for k, cls in tops(pools, lab).items():
        ys = [labels_of[c] for c in cls]
        p = Fraction(1, len(ys)) if ys else Fraction(0)
        lo = sum(p for y in ys if y == 1)
        hi = sum(p for y in ys if y != 0)
        per_bug[k[0]].append((lo, hi))
    n = len(per_bug)
    lo = sum(sum(a for a, _ in v) / len(v) for v in per_bug.values()) / n
    hi = sum(sum(b for _, b in v) / len(v) for v in per_bug.values()) / n
    return float(100 * lo), float(100 * hi)


def paired(pa, pb, lab, labels_of):
    ta, tb = tops(pa, lab), tops(pb, lab)
    per_bug = defaultdict(list)
    for k in ta:
        coef = defaultdict(Fraction)
        for c in ta[k]:
            coef[c] += Fraction(1, len(ta[k]))
        for c in tb.get(k, ()):
            coef[c] -= Fraction(1, len(tb[k]))
        lo = hi = Fraction(0)
        for c, d in coef.items():
            y = labels_of[c]
            if y is None:
                lo += min(0, d)
                hi += max(0, d)
            else:
                lo += d * y
                hi += d * y
        per_bug[k[0]].append((lo, hi))
    n = len(per_bug)
    return (float(100 * sum(sum(a for a, _ in v) / len(v) for v in per_bug.values()) / n),
            float(100 * sum(sum(b for _, b in v) / len(v) for v in per_bug.values()) / n))


def eligible(pools, lab, labels_of):
    """Addendum: only pools with at least one known-correct or unknown candidate. The set depends on labels only, so it
    is identical for every permutation and for both sides of a paired comparison."""
    return {k: rows for k, rows in pools.items()
            if any(r["candidate_id"] in lab and labels_of[lab[r["candidate_id"]][0]] != 0 for r in rows)}


def first_correct_rank(pools, lab, labels_of):
    """Equal-bug mean rank of the first correct patch as [optimistic, pessimistic]: optimistic = first patch that is
    known-correct or unknown; pessimistic = first known-correct patch (pool size + 1 if the pool has none)."""
    per_bug = defaultdict(list)
    for (bug, _), rows in pools.items():
        order = sorted(rows, key=lambda r: r["prevarank_rank"])
        ys = [labels_of[lab[r["candidate_id"]][0]] if r["candidate_id"] in lab else None for r in order]
        opt = next((r["prevarank_rank"] for r, y in zip(order, ys) if y != 0), len(rows) + 1)
        pes = next((r["prevarank_rank"] for r, y in zip(order, ys) if y == 1), len(rows) + 1)
        per_bug[bug].append((opt, pes))
    n = len(per_bug)
    return (sum(sum(a for a, _ in v) / len(v) for v in per_bug.values()) / n,
            sum(sum(b for _, b in v) / len(v) for v in per_bug.values()) / n)


def check_t(pools):
    """Addendum check T: within groups of equal historical value and equal category, the share of GROUPS whose output
    order equals their input order (ties in rank, i.e. identical programs, are ignored); pairwise agreement also given."""
    groups_same = groups_total = agree = total = 0
    for rows in pools.values():
        groups = defaultdict(list)
        for r in rows:
            groups[(r["prevarank_historical_value"], r["prevarank_category"])].append(r)
        for g in groups.values():
            if len(g) < 2:
                continue
            by_in = [r["candidate_id"] for r in sorted(g, key=lambda r: r["input_position"])]
            by_out = [r["candidate_id"] for r in sorted(g, key=lambda r: (r["prevarank_rank"], r["input_position"]))]
            groups_total += 1
            groups_same += by_in == by_out
            for i in range(len(g)):
                for j in range(i + 1, len(g)):
                    a, b = g[i], g[j]
                    if a["prevarank_rank"] == b["prevarank_rank"]:
                        continue
                    total += 1
                    agree += (a["input_position"] < b["input_position"]) == (a["prevarank_rank"] < b["prevarank_rank"])
    return {"share_groups_output_equals_input_order": groups_same / groups_total if groups_total else None,
            "tie_groups": groups_total, "pairwise_agreement": agree / total if total else None, "tied_pairs": total}


def main():
    data = V.load()
    runs = dict(REF)
    for p in sorted(PERM.glob("perm_*_evaluation_ledger.jsonl")):
        label = p.name.split("_evaluation")[0]
        if (PERM / f"{label}.done").exists():  # only permutations whose run finished completely
            runs[label] = p
    loaded = {k: load(p) for k, p in runs.items()}
    res = {"runs": len(runs), "permutations": sum(k.startswith("perm_") for k in runs), "views": {}}
    for ev_name in ("E0", "E1"):
        lab = class_labels(data, data.evidence(ev_name))
        labels_of = {c: y for c, y in lab.values()}
        canon = eligible(loaded["canonical_v4"], lab, labels_of)
        per_run = {}
        for k, v in loaded.items():
            e = eligible(v, lab, labels_of)
            per_run[k] = {"eligible_pools": len(e), "eligible_bugs": len({b for b, _ in e}),
                          "success1_pp": success_interval(e, lab, labels_of),
                          "first_correct_rank_opt_pes": first_correct_rank(e, lab, labels_of),
                          "vs_canonical_pp": paired(e, canon, lab, labels_of) if k != "canonical_v4" else None}
        c_lo, c_hi = per_run["canonical_v4"]["success1_pp"]
        perms = [v for k, v in per_run.items() if k.startswith("perm_")]
        summary = {}
        if perms:
            for side, idx in (("lower", 0), ("upper", 1)):
                xs = [p["success1_pp"][idx] for p in perms]
                summary[f"success1_{side}_min_median_max"] = [min(xs), median(xs), max(xs)]
            summary["share_intervals_entirely_above_canonical"] = sum(p["success1_pp"][0] > c_hi for p in perms) / len(perms)
            summary["share_intervals_entirely_below_canonical"] = sum(p["success1_pp"][1] < c_lo for p in perms) / len(perms)
            fr = [p["first_correct_rank_opt_pes"] for p in perms]
            summary["first_correct_rank_opt_min_max"] = [min(a for a, _ in fr), max(a for a, _ in fr)]
            summary["first_correct_rank_pes_min_max"] = [min(b for _, b in fr), max(b for _, b in fr)]
            d = [p["vs_canonical_pp"] for p in perms]
            summary["paired_vs_canonical"] = {"identified_positive": sum(a > 0 for a, _ in d),
                                              "identified_negative": sum(b < 0 for _, b in d),
                                              "open": sum(a <= 0 <= b for a, b in d),
                                              "lower_min": min(a for a, _ in d), "upper_max": max(b for _, b in d)}
        res["views"][ev_name] = {"per_run": per_run, "summary": summary}
    res["check_T"] = {k: check_t(v) for k, v in loaded.items()}
    out = ROOT / "results/v4/prevarank"
    out.mkdir(parents=True, exist_ok=True)
    (out / "e2_analysis.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({v: res["views"][v]["summary"] for v in res["views"]}, indent=1))
    print(json.dumps({k: res["check_T"][k] for k in list(res["check_T"])[:4]}, indent=1))


if __name__ == "__main__":
    main()
