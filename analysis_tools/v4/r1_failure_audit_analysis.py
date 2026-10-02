"""R1 failure audit analysis (ADDENDUM_V4_R1_FAILURE_AUDIT.md, rules fixed before execution). Read-only.

Non-reproduction rate of archived failures from the five high-failure configurations, overall and per configuration
(Clopper-Pearson 95%), and its propagation into the 16 final Defects4J comparisons: each population label returns to
unknown independently with the upper 95% limit of its configuration's rate (20,000 draws). Also reports, per
comparison, how many population labels in the worst places would have to be withdrawn to reopen it.
Writes results/v4/r1_failure_audit/analysis.json and FAILURE_AUDIT.md.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import beta

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import r1_review_checks as R  # noqa: E402
import refutation_limit as RL  # noqa: E402

OUT = ROOT / "results/v4/r1_failure_audit"
RUN = ROOT / "results/v4/r1_failure_audit_run_v1"
SEED = 20261002
REPRODUCED = {"controlled_trigger_failure", "compile_command_failed_twice"}
NOT_REPRODUCED = {"admissible_triggers_pass_semantics_unknown"}


def cp(k, n):
    lo = 0.0 if k == 0 else float(beta.ppf(0.025, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(0.975, k + 1, n - k))
    return [round(lo, 4), round(hi, 4)]


def main():
    RL.read_only_guards()
    status = {}
    for t in RUN.glob("*/terminal.json"):
        for f in json.loads(t.read_text())["findings"]:
            status[f["candidate_id"]] = f["evidence_status"]
    sel = json.loads((OUT / "selection.json").read_text())
    high = set(sel["high_rate_configs"])
    data, pools, evs, basis, comps = R.build_d4j()
    raw = R.raw_records()
    recs = defaultdict(list)
    for o in raw["occ"]:
        if o["bench"] == "defects4j":
            recs[o["cid"]].append(o)

    def cfg_of(m):
        fails = [o for o in recs.get(m, []) if R.fail_kind(o)]
        return sorted({o["cfg"] for o in fails})[0] if fails and all(o["cfg"] in high for o in fails) else None

    # outcome per sampled candidate
    by_cfg = defaultdict(Counter)
    for m, st in status.items():
        k = "reproduced" if st in REPRODUCED else "not_reproduced" if st in NOT_REPRODUCED else "unresolved"
        by_cfg[cfg_of(m)][k] += 1
        by_cfg["all"][k] += 1
    rates = {}
    for c, v in by_cfg.items():
        n = v["reproduced"] + v["not_reproduced"]
        rates[c] = {"reproduced": v["reproduced"], "not_reproduced": v["not_reproduced"], "unresolved": v["unresolved"],
                    "rate": round(v["not_reproduced"] / n, 4) if n else None, "cp95": cp(v["not_reproduced"], n) if n else None}
    # population (same rule as select_r1_failure_audit.py, over every comparison's relevant classes)
    copies = {r["cid"] for r in R.failing_copies()}
    c1 = {r["candidate_id"] for r in json.loads((ROOT / "results/v4/c1_fixrerun/candidates.json").read_text())}
    pop = {}
    for m, y in data.e0.items():
        if y != 0 or basis.get(m) != "exec" or evs["R"][m] != 0 or m in copies or m in c1 or m in data.witnesses:
            continue
        c = cfg_of(m)
        if c:
            pop[m] = c
    p_cfg = {c: rates[c]["cp95"][1] if c in rates and rates[c]["cp95"] else rates["all"]["cp95"][1] for c in high}
    n = len(data.bugs)
    classes_of = {b: cl for b, (_, cl) in pools.items()}
    rng = np.random.default_rng(SEED)
    N = 20000
    comp_res = {}
    for b in comps:
        rows, L, H, _ = R.interval(data, pools, evs["R"], b)
        # a population label only matters through its class: withdrawing it can make the class unknown
        # (if no other member keeps the 0) -- the bound then loses the class's gain
        loss, probs = [], []
        for r in rows:
            if r["y"] != 0 or r["d"] == 0:
                continue
            bug, i = r["key"]
            mem = classes_of[bug][i].members
            zeros = [m for m in mem if evs["R"][m] == 0]
            if not zeros or not all(m in pop for m in zeros):
                continue  # some 0 is not a population label, so the class stays incorrect
            p = 1.0
            for m in zeros:
                p *= p_cfg[pop[m]]  # every population 0 in the class must be withdrawn
            g = float(r["d"]) if r["d"] > 0 else 0.0  # class at 0 with d>0 lowers H only; with d<0 raises L when known
            # gain of a known-incorrect class towards the decision s=+1 is max(0, -d); withdrawing it removes that gain
            gain = max(0.0, -float(r["d"]))
            if gain > 0:
                loss.append(gain)
                probs.append(p)
        Lf = float(L)
        hold = N
        if loss:
            la, pa = np.array(loss), np.array(probs)
            tot = np.full(N, Lf)
            for s in range(0, len(la), 500):
                tot -= (rng.random((N, len(la[s:s + 500]))) < pa[s:s + 500]) @ la[s:s + 500]
            hold = int((tot > 0).sum())
        srt = sorted(loss, reverse=True)
        acc, k = 0.0, None
        for i, g in enumerate(srt, 1):
            acc += g
            if acc >= Lf:
                k = i
                break
        comp_res[b] = {"L_pp": RL.ppf(L, n), "population_classes_at_risk": len(loss),
                       "expected_withdrawals": round(float(sum(probs)), 2), "p_decided": round(hold / N, 4),
                       "withdrawals_to_reopen_worst_case": k}
    res = {"status": "analysis fixed in ADDENDUM_V4_R1_FAILURE_AUDIT.md before execution",
           "sampled": len(status), "outcomes": dict(Counter(status.values())), "rates": rates,
           "population": len(pop), "withdrawal_probability_by_config": p_cfg, "comparisons": comp_res,
           "decided_with_probability_ge_0_95": sum(v["p_decided"] >= 0.95 for v in comp_res.values())}
    (OUT / "analysis.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    md = ["# R1 failure audit", "", f"Sampled {len(status)}; outcomes {dict(Counter(status.values()))}.", "",
          "| Configuration | Reproduced | Not reproduced | Unresolved | Rate | 95% CI |", "|---|---|---|---|---|---|"]
    for c, v in sorted(rates.items(), key=lambda kv: kv[0] != "all"):
        md.append(f"| {c} | {v['reproduced']} | {v['not_reproduced']} | {v['unresolved']} | {v['rate']} | {v['cp95']} |")
    md += ["", f"Population {len(pop)} labels; each withdrawn with the upper CI of its configuration.", "",
           "| Comparison | L (pp) | Classes at risk | Expected withdrawals | P(decided) | Withdrawals to reopen (worst case) |",
           "|---|---|---|---|---|---|"]
    for b, v in comp_res.items():
        md.append(f"| {b} | {v['L_pp']:.2f} | {v['population_classes_at_risk']} | {v['expected_withdrawals']} | "
                  f"{v['p_decided']} | {v['withdrawals_to_reopen_worst_case']} |")
    (OUT / "FAILURE_AUDIT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
