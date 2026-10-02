"""F6 summary (ADDENDUM_V4_F6_FALSE_REJECTION_PANEL.md): false rejections among randomly sampled accepted-correct,
test-passing candidates, with an exact Clopper-Pearson upper bound. Unresolved cases are reported by status and never
counted as passes."""
import glob
import json
from collections import Counter
from pathlib import Path

from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "results/v4/f6_panel_run_v1"


def main():
    status, witnesses = Counter(), []
    for t in sorted(glob.glob(str(RUN / "*" / "terminal.json"))):
        for f in json.loads(Path(t).read_text())["findings"]:
            status[f["evidence_status"]] += 1
            if f["evidence_status"] == "controlled_trigger_failure":
                witnesses.append(f["candidate_id"])
    k = len(witnesses)
    n = status["controlled_trigger_failure"] + status["admissible_triggers_pass_semantics_unknown"]
    res = {"sampled": sum(status.values()), "statuses": dict(status), "evaluable": n, "false_rejections": k,
           "false_rejection_ids": witnesses,
           "cp95_two_sided_upper": float(beta.ppf(0.975, k + 1, n - k)) if n else None,
           "cp95_one_sided_upper": float(beta.ppf(0.95, k + 1, n - k)) if n else None,
           "progress": json.loads((RUN / "full_progress.json").read_text())}
    out = ROOT / "results/v4/f6_panel"
    out.mkdir(parents=True, exist_ok=True)
    (out / "f6_summary.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k2: v for k2, v in res.items() if k2 != "progress"}, indent=1))


if __name__ == "__main__":
    main()
