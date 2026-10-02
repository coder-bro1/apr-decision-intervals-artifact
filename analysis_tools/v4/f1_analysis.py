"""F1 analysis (ADDENDUM_V4_F1_CONCORDANCE.md): Defects4J v3/Java 11 census (results/conflict_census/run_v1) versus the
unchanged harness rerun in Defects4J v2/Java 8 (results/v4/f1_concordance_run_v1).

Reports, as fixed in the addendum:
 1. per-candidate concordance table (v3 status x v2 status) by group: the 185 witnesses, the 67 trigger-passers,
    the 10 compile-command failures, other census statuses, and each control stratum;
 2. witness reproduction rate with an exact (Clopper-Pearson) 95% interval;
 3. headline bounds under E1-both (a witness counts only if it reproduces in v2) next to E1;
 4. v2-only new witnesses, used only in the labelled sensitivity E1-union;
 5. false rejections among the correct-labelled controls in v2 (rule of three + exact bound). The addendum text says
    "63"; that number came from an earlier 29 + 34 panel. This package holds 30 correct-labelled controls, reported
    as they are. Incorrect-labelled test-passing controls are reported separately, never as false-rejection evidence;
 6. compile-command failures reproduced in both environments (input to the compile-asymmetry sensitivity), with the
    primary bounds if those are counted incorrect.
No archived label is changed and nothing in the v1 outputs is modified.
"""
import glob
import json
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import baselines as B  # noqa: E402
from select_f2_topup import BASELINES  # noqa: E402

V3 = ROOT / "results/conflict_census/run_v1"
V2 = ROOT / "results/v4/f1_concordance_run_v1"
WORK = ROOT / "results/conflict_census/execution_v1/worklist.json"
CTF = "controlled_trigger_failure"
PASS = "admissible_triggers_pass_semantics_unknown"
CFAIL = "compile_command_failed_twice"


def statuses(run, skip_smoke=True):
    out = {}
    for t in glob.glob(str(run / "*" / "terminal.json")):
        if skip_smoke and Path(t).parent.name.startswith("smoke_"):
            continue
        for f in json.loads(Path(t).read_text())["findings"]:
            out[f["candidate_id"]] = f["evidence_status"]
    return out


def cp(k, n):
    if n == 0:
        return [None, None]
    lo = 0.0 if k == 0 else float(beta.ppf(0.025, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(0.975, k + 1, n - k))
    return [lo, hi]


def bounds(data, pools, ev, pairs):
    res = {}
    for a, b in pairs:
        units, _ = V.evaluate_pair(data, pools, ev, a, b)
        agg = V.aggregate(units, "bug", len(data.bugs))
        res[f"{a}-{b}"] = [V.pp(agg["lo"]), V.pp(agg["hi"])]
    return res


def main():
    work = {r["candidate_id"]: r for r in json.loads(WORK.read_text())}
    s3, s2 = statuses(V3), statuses(V2)
    progress = json.loads((V2 / "full_progress.json").read_text()) if (V2 / "full_progress.json").exists() else {}

    def group(k):
        r = work[k]
        if r["role"] == "compatibility_control":
            return "control:" + r["stratum"]
        st = s3.get(k)
        return {CTF: "census:witness (v3)", PASS: "census:trigger-passer (v3)", CFAIL: "census:compile-fail (v3)"}.get(
            st, "census:other (v3)")

    table = defaultdict(Counter)
    for k in work:
        table[group(k)][(s3.get(k, "missing"), s2.get(k, "not run yet"))] += 1
    conc = {g: {f"{a} -> {b}": n for (a, b), n in sorted(c.items())} for g, c in sorted(table.items())}

    wit = [k for k in work if work[k]["role"] == "census" and s3.get(k) == CTF]
    wit_run = [k for k in wit if k in s2]
    wit_rep = [k for k in wit_run if s2[k] == CTF]
    new_v2 = [k for k in work if work[k]["role"] == "census" and s3.get(k) != CTF and s2.get(k) == CTF]
    ctl = [k for k in work if work[k]["role"] == "compatibility_control" and work[k]["stratum"] == "correct_test_pass"]
    ctl_eval = [k for k in ctl if s2.get(k) in (CTF, PASS)]
    ctl_fr = [k for k in ctl_eval if s2[k] == CTF]
    itp = [k for k in work if work[k]["role"] == "compatibility_control" and work[k]["stratum"] == "incorrect_test_pass"]
    cf_both = [k for k in work if s3.get(k) == CFAIL and s2.get(k) == CFAIL]

    data = V.load()
    B.register(data)
    pools = V.build_pools(data, "bug", "ast")
    pairs = [("challenger", b) for b in BASELINES if b in V.POLICIES]
    e1 = data.evidence("E1")
    e1_both = dict(e1)
    for k in wit:
        if not (k in s2 and s2[k] == CTF):
            e1_both[k] = None  # non-reproducing (or not yet rerun) witnesses revert to unknown
    e1_union = dict(e1)
    for k in new_v2:
        if e1_union.get(k) is None:
            e1_union[k] = 0
    e1_cf = dict(e1)
    for k in cf_both:
        if e1_cf.get(k) is None:
            e1_cf[k] = 0
    res = {
        "v2_progress": progress,
        "1_concordance": conc,
        "2_witness_reproduction": {"witnesses_v3": len(wit), "rerun_in_v2": len(wit_run), "reproduced": len(wit_rep),
                                   "rate": len(wit_rep) / len(wit_run) if wit_run else None,
                                   "cp95": cp(len(wit_rep), len(wit_run)),
                                   "not_reproduced": {k: s2[k] for k in wit_run if s2[k] != CTF}},
        "3_bounds_pp": {"E1": bounds(data, pools, e1, pairs), "E1_both": bounds(data, pools, e1_both, pairs)},
        "4_v2_only_witnesses": {"count": len(new_v2), "ids": new_v2,
                                "E1_union_bounds_pp": bounds(data, pools, e1_union, pairs)},
        "5_false_rejections_correct_controls": {"correct_labelled_controls": len(ctl), "evaluable_in_v2": len(ctl_eval),
                                                "false_rejections": len(ctl_fr), "ids": ctl_fr,
                                                "rule_of_three_upper": 3 / len(ctl_eval) if ctl_eval else None,
                                                "cp95": cp(len(ctl_fr), len(ctl_eval)),
                                                "note": "addendum text says 63 (an earlier 29+34 panel); this package has these"},
        "5b_incorrect_test_pass_controls_v2": dict(Counter(s2.get(k, "not run yet") for k in itp)),
        "6_compile_failures_both": {"count": len(cf_both), "ids": cf_both,
                                    "primary_bounds_if_incorrect_pp": bounds(data, pools, e1_cf, [("challenger", "mra")])},
    }
    out = ROOT / "results/v4/concordance"
    out.mkdir(parents=True, exist_ok=True)
    (out / "f1_concordance.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k not in ("1_concordance", "3_bounds_pp", "v2_progress")}, indent=1)[:4000])
    print("primary challenger-mra: E1", res["3_bounds_pp"]["E1"]["challenger-mra"], "E1-both",
          res["3_bounds_pp"]["E1_both"]["challenger-mra"], "E1-union",
          res["4_v2_only_witnesses"]["E1_union_bounds_pp"]["challenger-mra"])


if __name__ == "__main__":
    main()
