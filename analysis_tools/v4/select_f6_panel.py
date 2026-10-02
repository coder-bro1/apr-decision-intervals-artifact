"""F6: draw the random false-rejection panel frame and sample (ADDENDUM_V4_F6_FALSE_REJECTION_PANEL.md)."""
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import provenance as P  # noqa: E402


def unanimous_true(values):
    keys = {k for k, n in values.items() if n}
    return keys == {"true"}


def main():
    data = V.load()
    arch = P.load_archive()
    basis, _ = P.basis_map(data, arch)
    legacy = {r["candidate_id"]: r["legacy_candidate_ids"] for r in V.jsonl(V.INPUTS["evaluation_evidence"])}
    pkg = json.loads((V.RES / "conflict_census/execution_v1/jobs.json").read_text())
    used = {e["candidate_id"] for j in pkg for e in j["cases"]}
    frame = []
    for k, y in data.e0.items():
        if y != 1 or k in used or data.occ[k].noop:
            continue
        tv = Counter()
        for old in legacy[k]:
            tv.update(arch[old]["test_values"])
        if unanimous_true(tv):
            frame.append(k)
    frame.sort()
    sample = random.Random(20260929).sample(frame, 100)
    out = V.RES / "v4" / "f6_panel"
    out.mkdir(parents=True, exist_ok=True)
    (out / "panel_candidates.json").write_text(json.dumps([{"candidate_id": k, "compile_only": False} for k in sample], indent=1))
    summary = {"frame_size": len(frame), "sample": 100, "seed": 20260929,
               "sample_basis": dict(Counter(basis[k] for k in sample)),
               "frame_basis": dict(Counter(basis[k] for k in frame)),
               "sample_bugs": len({data.occ[k].bug for k in sample}),
               "protocol_sha256": data.input_hashes["protocol"]}
    (out / "selection_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
