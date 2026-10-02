"""H1: bug-cluster resampling that REFITS the three-stage challenger inside every replicate (PROTOCOL_V4 section 8).

A replicate is a bug-multiplicity vector m (m_b = how often bug b is drawn). Every training row of bug b is repeated
m_b times (rows of undrawn bugs are dropped) and the unchanged pilot_step2 procedure is rerun: five rotations, the C
grid tuned on the tuning folds by log loss, refit on training+tuning, stage product. Row duplication is exactly the
data-space bootstrap and, with m = 1, reproduces the paper's fit bit-for-bit (checked by --mode gate). Held-out
challenger scores are recomputed for every bug; primary per-bug bounds (bug unit, AST identity, known-wins, N-a, E1,
challenger vs MRA, uniform ties) are recomputed with those scores; the replicate estimate is the m-weighted mean.

Modes: gate (m = 1: must reproduce [+5.571, +11.513] and the archived scores), boot (2,000 replicates, seed
20260929 + r), loo (leave-one-bug-out with retraining: m_b = 0 for one bug, 1 otherwise; 488 refits).
Output is resumable JSONL under results/v4/inference/.
"""
import argparse
import json
import sys
from fractions import Fraction
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
OUT = ROOT / "results/v4/inference"

G = {}


def init():
    from threadpoolctl import threadpool_limits
    G["tp"] = threadpool_limits(limits=1)
    import run_evidence_pilot_step2 as S
    import v4core as V
    views, _, _, training, _ = S.load_inputs()
    data = V.load(hash_inputs=False)
    pools = V.build_pools(data, "bug", "ast")
    ev = data.evidence("E1")
    bug_classes = {}
    for bug, classes in pools.values():
        labels, mra = [], []
        for kl in classes:
            y, _ = V.class_label(kl.members, ev, "known_wins")
            if y is None and any(data.occ[m].noop for m in kl.members):
                y = 0  # N-a
            labels.append(y)
            mra.append(V.pol_mra(data, kl))
        bug_classes[bug] = ([kl.members for kl in classes], labels, mra)
    G.update(S=S, V=V, data=data, views=views, training=training, bugs=data.bugs, bug_classes=bug_classes,
             index={v.candidate_id: i for i, v in enumerate(views)},
             bug_of_row=[r["bug_id"] for r in training])


def refit_scores(mb):
    """Held-out joint scores for every candidate after refitting on the multiplicity-expanded data."""
    S, views, training = G["S"], G["views"], G["training"]
    rep = np.array([mb[b] for b in G["bug_of_row"]], dtype=np.int64)
    scores = np.zeros(len(views))
    for j in range(5):
        roles = S.role_folds(j)
        refit_folds = roles["training"] | roles["tuning"]
        sub = {role: [i for i, row in enumerate(training) if row["fold"] in folds for _ in range(rep[i])]
               for role, folds in {**roles, "refit": refit_folds}.items()}
        test_all = [i for i, row in enumerate(training) if row["fold"] in roles["test"]]
        design = S.ProvenanceFeatures([views[i] for i in sub["training"]])
        refit = S.ProvenanceFeatures([views[i] for i in sub["refit"]])
        xd, xr = design.transform(views), refit.transform(views)
        joint = np.ones(len(views))
        for stage in S.STAGES:
            el = {role: [i for i in idx if training[i][stage] is not None] for role, idx in sub.items()}
            yy = {role: np.array([training[i][stage] for i in idx], dtype=np.int8) for role, idx in el.items()}
            trials = []
            for c in S.C_GRID:
                model = S.fit_logistic(xd[el["training"]], yy["training"], c)
                prob = model.predict_proba(xd[el["tuning"]])[:, 1]
                trials.append((S.safe_log_loss(yy["tuning"], prob), c))
            best = min(trials)[1]
            model = S.fit_logistic(xr[el["refit"]], yy["refit"], best)
            joint = joint * model.predict_proba(xr)[:, 1]
        scores[test_all] = joint[test_all]
    return scores


def per_bug_bounds(scores):
    """Exact (Fraction) per-bug [L_b, H_b] for challenger vs MRA with the given scores."""
    idx = G["index"]
    out = {}
    for b in G["bugs"]:
        members, labels, mra = G["bug_classes"][b]
        if not members:
            out[b] = (Fraction(0), Fraction(0))
            continue
        ch = [max(scores[idx[m]] for m in mem) for mem in members]
        tc = [i for i, v in enumerate(ch) if v == max(ch)]
        tm = [i for i, v in enumerate(mra) if v == max(mra)]
        pa = {i: Fraction(1, len(tc)) for i in tc}
        pb = {i: Fraction(1, len(tm)) for i in tm}
        lo = hi = Fraction(0)
        for i in set(pa) | set(pb):
            d = pa.get(i, Fraction(0)) - pb.get(i, Fraction(0))
            y = labels[i]
            if y is None:
                lo += min(Fraction(0), d)
                hi += max(Fraction(0), d)
            else:
                lo += d * y
                hi += d * y
        out[b] = (lo, hi)
    return out


def estimate(mb, scores):
    per = per_bug_bounds(scores)
    n = sum(mb.values())
    lo = sum(mb[b] * per[b][0] for b in G["bugs"]) / n
    hi = sum(mb[b] * per[b][1] for b in G["bugs"]) / n
    return float(100 * lo), float(100 * hi)


def job(spec):
    kind, r = spec
    bugs = G["bugs"]
    if kind == "boot":
        rng = np.random.default_rng(20260929 + r)
        mult = np.bincount(rng.integers(0, len(bugs), len(bugs)), minlength=len(bugs))
        mb = {b: int(mult[i]) for i, b in enumerate(bugs)}
    elif kind == "loo":
        mb = {b: int(i != r) for i, b in enumerate(bugs)}
    else:
        mb = {b: 1 for b in bugs}
    scores = refit_scores(mb)
    lo, hi = estimate(mb, scores)
    res = {"kind": kind, "replicate": r, "L_pp": lo, "H_pp": hi}
    if kind == "loo":
        res["left_out"] = bugs[r]
    if kind == "gate":
        archived = np.array([G["data"].occ[v.candidate_id].score for v in G["views"]])
        res["max_abs_score_diff"] = float(np.max(np.abs(archived - scores)))
        res["archived_scores_L_H_pp"] = estimate(mb, archived)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("gate", "boot", "loo"), required=True)
    ap.add_argument("--replicates", type=int, default=2000)
    ap.add_argument("--procs", type=int, default=6)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.mode == "gate":
        init()
        res = job(("gate", 0))
        print(json.dumps(res, indent=1))
        (OUT / "refit_gate.json").write_text(json.dumps(res, indent=1))
        return
    path = OUT / f"refit_{args.mode}.jsonl"
    done = set()
    if path.exists():
        done = {json.loads(line)["replicate"] for line in open(path, encoding="utf-8") if line.strip()}
    total = args.replicates if args.mode == "boot" else 488
    todo = [(args.mode, r) for r in range(total) if r not in done]
    print(f"{len(done)} done, {len(todo)} to run", flush=True)
    with Pool(args.procs, initializer=init) as pool, open(path, "a", encoding="utf-8") as f:
        for k, res in enumerate(pool.imap_unordered(job, todo), 1):
            f.write(json.dumps(res) + "\n")
            f.flush()
            if k % 10 == 0:
                print(f"{k}/{len(todo)}", flush=True)


if __name__ == "__main__":
    main()
