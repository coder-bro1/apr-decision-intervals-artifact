"""B2: provenance basis of every accepted label (occurrence level) from the archived candidate records."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402

ARCHIVE = [V.ROOT / f"llm_apr_dataset/llm_apr_defects4j_candidates_v2_candidates_{x}.jsonl" for x in ("all", "excluded")]
REF = {"correct_exact", "correct_ast"}
EXEC = {"incorrect_test_failure"}
HUMAN_CORRECT = {"correct_semantic"}
HUMAN_INCORRECT = {"incorrect_manual_semantic"}


def load_archive():
    arch = {}
    for p in ARCHIVE:
        for r in V.jsonl(p):
            arch[r["candidate_id"]] = r
    return arch


def basis_map(data, arch=None):
    """Occurrence id -> basis of its accepted E0 label: 'ref', 'exec', 'human', or None (unknown label).

    A label is supported by the archived records that carry it. Correct: 'ref' if any supporting record is an
    exact/AST reference match, else 'human'. Incorrect: 'exec' if any supporting record is a recorded
    compile/test failure, else 'human'.
    """
    arch = arch or load_archive()
    legacy = {r["candidate_id"]: r["legacy_candidate_ids"] for r in V.jsonl(V.INPUTS["evaluation_evidence"])}
    basis, detail = {}, Counter()
    for k, y in data.e0.items():
        if y is None:
            basis[k] = None
            continue
        ev = Counter()
        prov = Counter()
        for old in legacy[k]:
            rec = arch[old]
            if (y == 1 and rec["label"] == "correct") or (y == 0 and rec["label"] == "incorrect"):
                ev.update(rec["annotation_evidence"])
                prov.update(rec["reviewer_provenance_statuses"])
        if y == 1:
            b = "ref" if ev.keys() & REF else ("human" if ev.keys() & HUMAN_CORRECT else "other")
        else:
            b = "exec" if ev.keys() & EXEC else ("human" if ev.keys() & HUMAN_INCORRECT else "other")
        basis[k] = b
        sub = ""
        if b == "ref":
            sub = "+".join(sorted(ev.keys() & REF))
        elif b == "human":
            sub = "tiebreak" if prov.get("third_reviewer_tiebreak") else "agreement"
        detail[(y, b, sub)] += 1
    return basis, detail


def main():
    data = V.load()
    arch = load_archive()
    basis, detail = basis_map(data, arch)
    occ_table = Counter((y, basis[k]) for k, y in data.e0.items())
    # bug-level identity classes (primary identity): basis set of each known class
    pools = V.build_pools(data, "bug", "ast")
    cls = Counter()
    for _, (bug, classes) in pools.items():
        for kl in classes:
            y, conflict = V.class_label(kl.members, data.e0, "known_wins")
            if conflict:
                cls[("conflict", "-")] += 1
                continue
            if y is None:
                cls[("unknown", "-")] += 1
                continue
            bases = sorted({basis[m] for m in kl.members if data.e0[m] == y})
            cls[(y, "+".join(bases))] += 1
    # census compatibility controls (R1 Q1, R1 M4): provenance by stratum
    worklist = json.loads((V.RES / "conflict_census/preparation_v1/worklist.json").read_text())
    ctrl = Counter()
    for r in worklist:
        if r["role"] == "compatibility_control":
            ctrl[(r["stratum"], basis.get(r["candidate_id"]))] += 1
    out = V.RES / "v4" / "provenance"
    out.mkdir(parents=True, exist_ok=True)
    res = {
        "protocol_sha256": data.input_hashes["protocol"],
        "occurrence_level": {f"{('correct' if y == 1 else 'incorrect' if y == 0 else 'unknown')}|{b}": n
                             for (y, b), n in sorted(occ_table.items(), key=str)},
        "occurrence_detail": {f"{y}|{b}|{s}": n for (y, b, s), n in sorted(detail.items(), key=str)},
        "bug_level_classes_primary_identity": {f"{y}|{b}": n for (y, b), n in sorted(cls.items(), key=str)},
        "census_controls_by_stratum_and_basis": {f"{s}|{b}": n for (s, b), n in sorted(ctrl.items(), key=str)},
    }
    (out / "provenance.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
