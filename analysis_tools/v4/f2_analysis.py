"""F2 analysis (ADDENDUM_V4_F2_CENSUS_TOPUP.md): evidence view E2 = E1 + F2 witnesses. A representative with status
controlled_trigger_failure labels its class incorrect (via known-wins); every other status leaves the class unknown.
Reports every pre-registered comparison (challenger vs each baseline; primary spec) under E0, E1 and E2, and the
share of representatives in each status. Writes results/v4/f2_topup/f2_analysis.json."""
import glob
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import baselines as B  # noqa: E402
from select_f2_topup import BASELINES  # noqa: E402


def main():
    status = {}
    for t in glob.glob(str(ROOT / "results/v4/f2_topup_run_v1/*/terminal.json")):
        for f in json.loads(Path(t).read_text())["findings"]:
            status[f["candidate_id"]] = f["evidence_status"]
    selected = {r["candidate_id"] for r in json.loads((ROOT / "results/v4/f2_topup/f2_candidates.json").read_text())}
    data = V.load()
    B.register(data)
    pools = V.build_pools(data, "bug", "ast")
    e1 = data.evidence("E1")
    e2 = dict(e1)
    wit = [k for k, s in status.items() if s == "controlled_trigger_failure"]
    for k in wit:
        if e2[k] is None:
            e2[k] = 0
    rows = []
    for b in BASELINES:
        if b not in V.POLICIES:
            continue
        row = {"a": "challenger", "b": b}
        for name, ev in (("E0", data.evidence("E0")), ("E1", e1), ("E2", e2)):
            units, _ = V.evaluate_pair(data, pools, ev, "challenger", b)
            agg = V.aggregate(units, "bug", len(data.bugs))
            row[name] = [V.pp(agg["lo"]), V.pp(agg["hi"])]
            row[name + "_relevant_unknowns"] = V.relevant_unknowns(units)
        row["decided_E1"] = row["E1"][0] > 0 or row["E1"][1] < 0
        row["decided_E2"] = row["E2"][0] > 0 or row["E2"][1] < 0
        rows.append(row)
    res = {"selected": len(selected), "with_result": len(set(status) & selected),
           "statuses": dict(Counter(status[k] for k in selected if k in status)), "new_witnesses": len(wit),
           "comparisons": rows}
    (ROOT / "results/v4/f2_topup/f2_analysis.json").write_text(json.dumps(res, indent=1))
    print({k: res[k] for k in ("selected", "with_result", "new_witnesses", "statuses")})
    for r in rows:
        flag = "NEWLY DECIDED" if r["decided_E2"] and not r["decided_E1"] else ""
        print(f"challenger vs {r['b']:20s} E1 {r['E1']} (unk {r['E1_relevant_unknowns']})  ->  E2 {r['E2']} (unk {r['E2_relevant_unknowns']}) {flag}")


if __name__ == "__main__":
    main()
