"""Rubric sensitivity of the final Defects4J decisions (V8 submission review, finding V8-02; post hoc, read-only).

The F4 annotators judged against the developer fix and counted a different but valid repair as incorrect, so an F4
"incorrect" verdict establishes non-conformance to the reference, not necessarily a specification violation. This
view makes no new judgement: every candidate that F4 set to incorrect is returned to its pre-F4 label (the
E1+F2+F3 value) in the final evidence (E1+F2+F3+F4+R), and all 16 comparisons are recomputed. F4 "correct" verdicts,
archived human labels and every other source are unchanged. Writes only results/v4/f4_rubric_sensitivity_v1/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import refutation_limit as RL  # noqa: E402
import v4core as V  # noqa: E402

OUT = ROOT / "results/v4/f4_rubric_sensitivity_v1"


def main():
    RL.read_only_guards()
    import base64
    import hashlib
    import c1_equivalence as C

    def run_tool_ro(cmd, texts, name):
        out, stamp = C.OUT / f"{name}_output.tsv", C.OUT / f"{name}_input.sha256"
        body = "".join(k + "\t" + base64.b64encode(t.encode()).decode() + "\n" for k, t in sorted(texts.items()))
        if not (out.exists() and stamp.exists() and stamp.read_text() == hashlib.sha256(body.encode()).hexdigest()):
            raise RuntimeError(f"cached javac output {name} is stale; refusing to call java")
        return {line.split("\t")[0]: line.split("\t")[1:] for line in out.read_text(encoding="utf-8").splitlines()}

    C.run_tool = run_tool_ro
    import final_evidence as FE
    import c1_fixrerun_analysis as CF
    from select_f2_topup import BASELINES

    built = CF.build()
    data, pools = built["data"], built["ast_pools"]
    views, _ = FE.build(data, pools)
    n = len(data.bugs)
    pre, post, final = views["E1+F2+F3"], views["E1+F2+F3+F4"], built["R"]
    f4_neg = [m for m in post if post[m] == 0 and pre[m] != 0]
    f4_pos = [m for m in post if post[m] == 1 and pre[m] != 1]
    sens = dict(final)
    reverted = 0
    for m in f4_neg:
        if sens[m] == 0:
            sens[m] = pre[m]
            reverted += 1
    kof = {m: (bug, i) for _, (bug, classes) in pools.items() for i, kl in enumerate(classes) for m in kl.members}
    comps = [b for b in BASELINES if b in V.POLICIES]
    rows = {}
    for b in comps:
        _, r0 = RL.rows_for(data, pools, final, "challenger", b)
        _, r1 = RL.rows_for(data, pools, sens, "challenger", b)
        L0, H0, *_ = RL.bounds(r0)
        L1, H1, *_ = RL.bounds(r1)
        rows[b] = {"final": [RL.ppf(L0, n), RL.ppf(H0, n)], "final_decided": L0 > 0 or H0 < 0,
                   "f4_incorrect_unknown": [RL.ppf(L1, n), RL.ppf(H1, n)],
                   "f4_incorrect_unknown_decided": L1 > 0 or H1 < 0}
    res = {"status": "post hoc, read-only; V8 review finding V8-02",
           "f4_incorrect_candidates": len(f4_neg), "f4_incorrect_classes": len({kof[m] for m in f4_neg if m in kof}),
           "f4_correct_candidates": len(f4_pos), "reverted_in_final_view": reverted,
           "decided_final": sum(r["final_decided"] for r in rows.values()),
           "decided_with_f4_incorrect_unknown": sum(r["f4_incorrect_unknown_decided"] for r in rows.values()),
           "comparisons": rows}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "f4_rubric_sensitivity.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    lines = ["# F4 rubric sensitivity (post hoc, read-only)", "",
             f"F4 incorrect: {res['f4_incorrect_candidates']} candidates in {res['f4_incorrect_classes']} classes "
             f"({reverted} reverted in the final view); F4 correct: {len(f4_pos)} candidates.",
             f"Decided: final {res['decided_final']}/16; with F4 incorrect verdicts unknown "
             f"{res['decided_with_f4_incorrect_unknown']}/16.", "",
             "| Comparison | Final [L, H] | F4 incorrect -> unknown [L, H] | decided |", "|---|---|---|---|"]
    for b, r in rows.items():
        lines.append(f"| {b} | [{r['final'][0]:+.2f}, {r['final'][1]:+.2f}] | "
                     f"[{r['f4_incorrect_unknown'][0]:+.2f}, {r['f4_incorrect_unknown'][1]:+.2f}] | "
                     f"{'yes' if r['f4_incorrect_unknown_decided'] else 'NO'} |")
    (OUT / "F4_RUBRIC_SENSITIVITY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
