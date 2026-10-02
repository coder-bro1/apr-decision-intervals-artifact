"""H1: Imbens-Manski (2004) confidence interval for the primary bug-level Delta + coverage validation (PROTOCOL_V4 s.8).

CI_{1-a} = [L - c*sL, H + c*sH], where c solves Phi(c + (H - L) / max(sL, sH)) - Phi(-c) = 1 - a (a = 0.05).
Standard errors sL, sH:
  - refit: SD of the 2,000 refit-bootstrap replicates (results/v4/inference/refit_boot.jsonl, h1_bootstrap.py);
  - fixed: SD from a bug-cluster bootstrap of the per-bug bounds with the archived scores held fixed.
The headline uses max(refit, fixed) per endpoint (conservative).

Coverage simulation (1,000 replicates per scenario, seed 20260929). Each scenario is a finite population of bugs with
per-bug bounds (L_b, H_b); its identified set is [mean L_b, mean H_b]. A simulated study samples n bugs with
replacement (the bug is the cluster, so every within-bug dependence of the pool is carried along), builds the
IM interval from an inner cluster bootstrap (500 draws), and we record whether the interval contains the true lower
endpoint, the true upper endpoint, the midpoint, and the whole set. Validation passes if the minimum point coverage
over {L, mid, H} is >= 0.94 in every scenario (Monte Carlo SE of 0.95 with 1,000 draws is ~0.007).
Scenarios: S1 observed (n = 488); S2 point-identified (H_b := L_b); S3 half width (H_b := (L_b + H_b)/2);
S4 small study (n = 100); S5 heavy tail (the 5% of bugs with the largest |L_b| + |H_b| have their bounds tripled).
Also: fixed-score IM intervals for every pre-registered comparison of the baseline matrix (supplementary; refitting
is done for the primary comparison only, and the refit/fixed SE ratio is reported so the reader can scale).
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import baselines as B  # noqa: E402

OUT = ROOT / "results/v4/inference"
ALPHA = 0.05


def im_c(width, s):
    if s == 0:
        return norm.ppf(1 - ALPHA / 2)
    f = lambda c: norm.cdf(c + width / s) - norm.cdf(-c) - (1 - ALPHA)
    return brentq(f, 0.0, 10.0)


def im_ci(lo, hi, sl, sh):
    c = im_c(max(hi - lo, 0.0), max(sl, sh))
    return lo - c * sl, hi + c * sh, c


def per_bug_arrays(units):
    lo = np.array([float(100 * u.lo) for u in units])
    hi = np.array([float(100 * u.hi) for u in units])
    return lo, hi


def cluster_sd(lo, hi, rng, draws):
    n = len(lo)
    idx = rng.integers(0, n, (draws, n))
    return float(lo[idx].mean(1).std(ddof=1)), float(hi[idx].mean(1).std(ddof=1))


def coverage(lo_pop, hi_pop, n, rng, reps=1000, inner=500):
    tl, th = lo_pop.mean(), hi_pop.mean()
    targets = {"L": tl, "mid": (tl + th) / 2, "H": th}
    hits = {k: 0 for k in targets}
    hits["set"] = 0
    widths = []
    N = len(lo_pop)
    for _ in range(reps):
        s = rng.integers(0, N, n)
        lo, hi = lo_pop[s], hi_pop[s]
        sl, sh = cluster_sd(lo, hi, rng, inner)
        a, b, _ = im_ci(lo.mean(), hi.mean(), sl, sh)
        for k, t in targets.items():
            hits[k] += a <= t <= b
        hits["set"] += a <= tl and th <= b
        widths.append(b - a)
    cov = {k: v / reps for k, v in hits.items()}
    return {"n": n, "true_L": tl, "true_H": th, "coverage": cov, "min_point_coverage": min(cov[k] for k in targets),
            "mean_ci_width_pp": float(np.mean(widths))}


def main():
    data = V.load()
    B.register(data)
    pools = V.build_pools(data, "bug", "ast")
    ev = data.evidence("E1")
    units, _ = V.evaluate_pair(data, pools, ev, "challenger", "mra")
    lo_b, hi_b = per_bug_arrays(units)
    L, H = lo_b.mean(), hi_b.mean()
    rng = np.random.default_rng(20260929)
    fixed_sl, fixed_sh = cluster_sd(lo_b, hi_b, rng, 10000)
    boot = [json.loads(x) for x in open(OUT / "refit_boot.jsonl", encoding="utf-8") if x.strip()]
    rl = np.array([r["L_pp"] for r in boot])
    rh = np.array([r["H_pp"] for r in boot])
    refit_sl, refit_sh = float(rl.std(ddof=1)), float(rh.std(ddof=1))
    sl, sh = max(refit_sl, fixed_sl), max(refit_sh, fixed_sh)
    a, b, c = im_ci(L, H, sl, sh)
    res = {"primary": {"comparison": "challenger vs MRA, bug unit, AST identity, known-wins, N-a, E1",
                       "identified_set_pp": [L, H], "refit_replicates": len(boot),
                       "se_refit_pp": [refit_sl, refit_sh], "se_fixed_scores_pp": [fixed_sl, fixed_sh],
                       "se_used_pp": [sl, sh], "im_critical_value": c, "im_ci95_pp": [a, b],
                       "refit_percentile_2.5_97.5": [float(np.percentile(rl, 2.5)), float(np.percentile(rh, 97.5))],
                       "refit_share_L_positive": float((rl > 0).mean())}}
    loo_path = OUT / "refit_loo.jsonl"
    if loo_path.exists():
        loo = [json.loads(x) for x in open(loo_path, encoding="utf-8") if x.strip()]
        ll = [r["L_pp"] for r in loo]
        hh = [r["H_pp"] for r in loo]
        res["loo_retrained"] = {"refits": len(loo), "L_range_pp": [min(ll), max(ll)], "H_range_pp": [min(hh), max(hh)],
                                "argmin_L": min(loo, key=lambda r: r["L_pp"])["left_out"]}
    # coverage validation
    scen = {}
    big = np.argsort(-(np.abs(lo_b) + np.abs(hi_b)))[: max(1, len(lo_b) // 20)]
    lo_t, hi_t = lo_b.copy(), hi_b.copy()
    lo_t[big] *= 3
    hi_t[big] *= 3
    specs = {"S1_observed": (lo_b, hi_b, 488), "S2_point_identified": (lo_b, lo_b.copy(), 488),
             "S3_half_width": (lo_b, (lo_b + hi_b) / 2, 488), "S4_small_n100": (lo_b, hi_b, 100),
             "S5_heavy_tail": (lo_t, hi_t, 488)}
    for name, (lp, hp, n) in specs.items():
        scen[name] = coverage(lp, hp, n, rng)
        print(name, scen[name]["coverage"], flush=True)
    res["coverage_simulation"] = scen
    res["validation_passed"] = all(s["min_point_coverage"] >= 0.94 for s in scen.values())
    # supplementary fixed-score IM intervals for the pre-registered baseline comparisons
    sup = []
    for other in ("mra", "best_config_top1", "first_global", "borda", "rrf", "mean_norm_position", "occurrence",
                  "mra_then_occurrence", "testability", "one_stage", "source_agnostic", "token_similarity",
                  "codet5_similarity", "naturalness", "entropy_delta", "uniform"):
        if other not in V.POLICIES:
            continue
        us, _ = V.evaluate_pair(data, pools, ev, "challenger", other)
        lo, hi = per_bug_arrays(us)
        fsl, fsh = cluster_sd(lo, hi, rng, 10000)
        a2, b2, _ = im_ci(lo.mean(), hi.mean(), fsl, fsh)
        sup.append({"b": other, "identified_set_pp": [float(lo.mean()), float(hi.mean())],
                    "se_fixed_pp": [fsl, fsh], "im_ci95_fixed_pp": [a2, b2],
                    "im_ci95_scaled_by_primary_refit_ratio_pp": [
                        lo.mean() - (lo.mean() - a2) * max(1.0, refit_sl / fixed_sl),
                        hi.mean() + (b2 - hi.mean()) * max(1.0, refit_sh / fixed_sh)]})
    res["supplementary_fixed_score"] = sup
    (OUT / "h1_inference.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["primary"], indent=1))
    print("validation_passed:", res["validation_passed"])


if __name__ == "__main__":
    main()
