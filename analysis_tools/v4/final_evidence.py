"""Final Defects4J evidence views, built in one place for the decidability table and every later analysis.

  E1            frozen contract labels + census witnesses (v4core)
  E1+F2         + F2 census top-up witnesses (controlled trigger failure; ADDENDUM_V4_F2_CENSUS_TOPUP.md)
  E1+F2+F3      + F3 generated-test witnesses (relevance-reviewed; ADDENDUM_V4_F3_DIFFTEST.md): every member of the
                  witnessed candidate's class -> 0
  E1+F2+F3+F4   + two-annotator class verdicts (score_annotations.py frozen rule): every class member -> verdict
  E1+F2+F3+F4c  as above, but only 'correct' verdicts (the packet's rubric is stricter than the archive's)

F3/F4 set whole classes. The only classes whose known member labels they overwrite are classes that were unknown
because their identical members carry contradictory archived labels; any other overwrite raises. Every overwrite is
returned in the log."""
import glob
import json
from pathlib import Path

import v4core as V

ROOT = Path(__file__).resolve().parents[2]
F2_RUNS = ROOT / "results/v4/f2_topup_run_v1"
F3_REVIEW = ROOT / "results/v4/f3_difftest/relevance_review.json"
F4_LABELS = ROOT / "results/v4/annotation_results/f4_resolved_labels.json"


def f2_witnesses():
    out = set()
    for t in glob.glob(str(F2_RUNS / "*/terminal.json")):
        for f in json.loads(Path(t).read_text())["findings"]:
            if f["evidence_status"] == "controlled_trigger_failure":
                out.add(f["candidate_id"])
    return out


def f3_witnesses():
    items = json.loads(F3_REVIEW.read_text())
    if any(i["verdict"] is None for i in items):
        raise ValueError("F3 relevance review incomplete")
    return {i["candidate_id"] for i in items if i["verdict"] == "witness"}


def _set_class(ev, members, val, log, source, rep):
    known = {ev[m] for m in members if ev[m] is not None}
    if known and known != {0, 1} and known != {val}:
        raise ValueError(f"{source} contradicts a consistent known class label ({rep})")
    if known == {0, 1}:
        log.append({"source": source, "representative": rep, "value": val,
                    "archived_member_labels": [ev[m] for m in members]})
    for m in members:
        ev[m] = val


def build(data, pools=None):
    """Returns (views, log). pools: the AST bug-unit pools used to find each candidate's class."""
    pools = pools or V.build_pools(data, "bug", "ast")
    klass_of = {m: kl.members for _, (_, classes) in pools.items() for kl in classes for m in kl.members}
    log = {"f2_witnesses_applied": 0, "overwrites": []}
    e1 = dict(data.evidence("E1"))
    e2 = dict(e1)
    for k in f2_witnesses():
        if e2[k] is None:
            e2[k] = 0
            log["f2_witnesses_applied"] += 1
    e3 = dict(e2)
    w3 = f3_witnesses()
    for k in sorted(w3):
        _set_class(e3, klass_of[k], 0, log["overwrites"], "F3", k)
    log["f3_witness_candidates"] = len(w3)
    f4 = json.loads(F4_LABELS.read_text())
    e4, e4c = dict(e3), dict(e3)
    for rep, row in sorted(f4.items()):
        val = {"correct": 1, "incorrect": 0}[row["label"]]
        members = sorted(set(row["class_members"]) | set(klass_of.get(rep, [])))
        _set_class(e4, members, val, log["overwrites"], "F4", rep)
        if val == 1:
            _set_class(e4c, members, 1, [], "F4c", rep)
    log["f4_classes"] = len(f4)
    views = {"E1": e1, "E1+F2": e2, "E1+F2+F3": e3, "E1+F2+F3+F4": e4, "E1+F2+F3+F4c": e4c}
    return views, log
