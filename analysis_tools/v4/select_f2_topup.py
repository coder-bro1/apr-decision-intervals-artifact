"""F2: select the census top-up (ADDENDUM_V4_F2_CENSUS_TOPUP.md).

For every pre-registered comparison (challenger vs each baseline of Protocol v4 s.4, bug unit, AST identity,
known-wins, N-a, E1), take the decision-relevant unknown identity classes. Exclude classes with any member already in
the census (they were executed) and classes whose every member passed the archived tests unanimously (execution cannot
reject those; they go to F3/F4). From each remaining class run one representative occurrence (smallest candidate id)
through the unchanged witness protocol, full phase, v3 image. Writes the candidate list for prepare_v4_rerun_package.py.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_evidence_pilot_step2 as S  # noqa: E402
import v4core as V  # noqa: E402
import baselines as B  # noqa: E402

OUT = ROOT / "results/v4/f2_topup"
BASELINES = ("mra", "best_config_top1", "first_global", "borda", "rrf", "mean_norm_position", "occurrence",
             "mra_then_occurrence", "testability", "one_stage", "source_agnostic", "token_similarity",
             "codet5_similarity", "naturalness", "entropy_delta", "uniform")


def main():
    data = V.load()
    B.register(data)
    _, _, _, training, _ = S.load_inputs()
    tpass = {r["candidate_id"]: (r["compile"] == 1 and r["test_given_compile"] == 1) for r in training}
    pools = V.build_pools(data, "bug", "ast")
    ev = data.evidence("E1")
    chosen = {}
    per_cmp = {}
    reasons = defaultdict(int)
    for other in BASELINES:
        if other not in V.POLICIES:
            per_cmp[other] = "not registered (score file missing)"
            continue
        units, _ = V.evaluate_pair(data, pools, ev, "challenger", other)
        rel = sel = 0
        for u, (bug, classes) in zip(units, pools.values()):
            for d, y, i in u.coeffs:
                if y is not None:
                    continue
                rel += 1
                kl = classes[i]
                if any(m in data.census for m in kl.members):
                    reasons["already_in_census"] += 1
                    continue
                if all(tpass[m] for m in kl.members):
                    reasons["all_test_pass(F3/F4)"] += 1
                    continue
                sel += 1
                rep = min(kl.members)
                chosen.setdefault(rep, {"candidate_id": rep, "compile_only": False, "bug": bug,
                                        "class_size": len(kl.members), "comparisons": []})["comparisons"].append(other)
        per_cmp[other] = {"relevant_unknown_classes": rel, "selected": sel}
    OUT.mkdir(parents=True, exist_ok=True)
    rows = sorted(chosen.values(), key=lambda r: r["candidate_id"])
    (OUT / "f2_candidates.json").write_text(json.dumps([{"candidate_id": r["candidate_id"], "compile_only": False}
                                                        for r in rows], indent=1))
    (OUT / "f2_selection_detail.json").write_text(json.dumps({"per_comparison": per_cmp, "exclusion_counts": reasons,
                                                              "selected": rows}, indent=1))
    print(json.dumps({"per_comparison": per_cmp, "exclusions": reasons, "unique_candidates": len(rows),
                      "bugs": len({r["bug"] for r in rows})}, indent=1))


if __name__ == "__main__":
    main()
