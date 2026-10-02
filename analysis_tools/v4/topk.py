"""C2: exact shared-label bounds for success within k attempts and capped expected attempts to the first correct patch.

Each policy orders eligible classes into score tie blocks; within a block the order is uniformly random. For a labelling
y, success@k(policy) = 1 - P(no correct class among the first k), and E[min(T, K)] = sum_{j<K} P(no correct among first j).
Both depend on y only through the number of correct classes in each block intersecting the first K positions, and are
monotone in those counts. Bounds of f(p) - f(q) over all completions of unknown labels are therefore exact when:
classes relevant to only one policy are set to their extreme (all 0 / all 1), and the shared cells (a class in a block of
p AND a block of q within the first K positions) are enumerated over their correct counts.
"""
import itertools
import json
import sys
from fractions import Fraction
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402

K_MAX = 5


def blocks(data, classes, score_fn, eligible):
    """Ordered tie blocks (lists of class indices) covering at least the first K_MAX positions."""
    elig = sorted(eligible)
    vals = {i: score_fn(data, classes[i]) for i in elig}
    out, covered = [], 0
    for v in sorted(set(vals.values()), reverse=True):
        blk = [i for i in elig if vals[i] == v]
        out.append(blk)
        covered += len(blk)
        if covered >= K_MAX:
            break
    return out


def p_none(block_sizes, counts, j):
    """P(no correct among first j positions) given block sizes and correct counts."""
    remaining, prob = j, Fraction(1)
    for n, c in zip(block_sizes, counts):
        if remaining <= 0:
            break
        take = min(n, remaining)
        if take == n:
            if c > 0:
                return Fraction(0)
        else:
            prob *= Fraction(comb(n - c, take), comb(n, take))
        remaining -= take
    return prob


def metrics(block_sizes, counts):
    none = [p_none(block_sizes, counts, j) for j in range(K_MAX + 1)]
    return {"s1": 1 - none[1], "s3": 1 - none[3], "s5": 1 - none[5], "e5": sum(none[:K_MAX])}


def bug_bounds(bp, bq, labels):
    """Exact [min, max] of metric(p) - metric(q) per metric over completions of unknown labels."""
    loc_p = {i: bi for bi, blk in enumerate(bp) for i in blk}
    loc_q = {i: bi for bi, blk in enumerate(bq) for i in blk}
    shared = sorted(set(loc_p) & set(loc_q))
    cells = {}
    for i in shared:
        cells.setdefault((loc_p[i], loc_q[i]), []).append(i)
    cell_keys = sorted(cells)
    cell_known = {c: sum(1 for i in cells[c] if labels[i] == 1) for c in cell_keys}
    cell_unk = {c: sum(1 for i in cells[c] if labels[i] is None) for c in cell_keys}
    size_p, size_q = [len(b) for b in bp], [len(b) for b in bq]
    res = {}
    grid = [range(cell_unk[c] + 1) for c in cell_keys]
    if 1:
        n_states = 1
        for g in grid:
            n_states *= len(g)
        if n_states > 5_000_000:
            raise RuntimeError(f"shared-cell enumeration too large ({n_states})")
    for direction in ("min", "max"):
        # only-p classes: extreme that favours p (max) or disfavours p (min); only-q the reverse
        base_p = [0] * len(bp)
        base_q = [0] * len(bq)
        for i, bi in loc_p.items():
            if i in loc_q:
                continue
            y = labels[i]
            base_p[bi] += (y if y is not None else (1 if direction == "max" else 0))
        for i, bi in loc_q.items():
            if i in loc_p:
                continue
            y = labels[i]
            base_q[bi] += (y if y is not None else (0 if direction == "max" else 1))
        best = None
        for combo in itertools.product(*grid):
            cp, cq = list(base_p), list(base_q)
            for c, extra in zip(cell_keys, combo):
                cnt = cell_known[c] + extra
                cp[c[0]] += cnt
                cq[c[1]] += cnt
            mp, mq = metrics(size_p, cp), metrics(size_q, cq)
            diff = {k: mp[k] - mq[k] for k in mp}
            if best is None:
                best = dict(diff)
            else:
                for k, v in diff.items():
                    if k == "e5":  # for expected attempts, 'max' favours p means the most negative difference
                        best[k] = (min if direction == "max" else max)(best[k], v)
                    else:
                        best[k] = (max if direction == "max" else min)(best[k], v)
        res[direction] = best
    # the per-direction extremes above fix non-shared classes favourably/unfavourably for p; for e5 (lower is
    # better) 'max' is the p-favourable direction, so reorder into numeric [lo, hi] per metric
    out = {}
    for k in ("s1", "s3", "s5"):
        out[k] = (res["min"][k], res["max"][k])
    out["e5"] = (res["max"]["e5"], res["min"]["e5"])
    return out


def run(data, pools, ev, a, b, noop="N-a"):
    fa, fb = V.POLICIES[a], V.POLICIES[b]
    ea, eb = V.POLICY_ELIG.get(a), V.POLICY_ELIG.get(b)
    noop_fn = V.noop_variant(data, "base")
    tot = {k: [Fraction(0), Fraction(0)] for k in ("s1", "s3", "s5", "e5")}
    for bug, classes in pools.values():
        labels = []
        for kl in classes:
            y, _ = V.class_label(kl.members, ev, "known_wins")
            if noop == "N-a" and noop_fn(kl) and y is None:
                y = 0
            labels.append(y)
        idx = set(range(len(classes)))
        bp = blocks(data, classes, fa, {i for i in idx if ea is None or ea(data, classes[i])})
        bq = blocks(data, classes, fb, {i for i in idx if eb is None or eb(data, classes[i])})
        r = bug_bounds(bp, bq, labels)
        for k in tot:
            tot[k][0] += r[k][0]
            tot[k][1] += r[k][1]
    n = len(data.bugs)
    return {k: (V.pp(v[0] / n) if k != "e5" else float(v[0] / n), V.pp(v[1] / n) if k != "e5" else float(v[1] / n))
            for k, v in tot.items()}


def main():
    import baselines as B
    data = V.load()
    B.register(data)
    pools = V.build_pools(data, "bug", "ast")
    rows = []
    for ev_name in ("E0", "E1"):
        ev = data.evidence(ev_name)
        for a, b in [("challenger", x) for x in ("mra", "best_config_top1", "first_global", "borda", "occurrence",
                                                  "mra_then_occurrence", "testability", "one_stage", "source_agnostic",
                                                  "codet5_similarity", "uniform")] + [("mra", "best_config_top1")]:
            if b not in V.POLICIES:
                continue
            r = run(data, pools, ev, a, b)
            rows.append({"evidence": ev_name, "a": a, "b": b, **{k: list(v) for k, v in r.items()}})
            print(ev_name, a, b, r, flush=True)
    out = V.RES / "v4" / "topk"
    out.mkdir(parents=True, exist_ok=True)
    (out / "topk_bounds.json").write_text(json.dumps({"protocol_sha256": data.input_hashes["protocol"],
                                                      "note": "s_k in pp (difference a-b); e5 = capped expected attempts difference (lower is better for a)",
                                                      "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
