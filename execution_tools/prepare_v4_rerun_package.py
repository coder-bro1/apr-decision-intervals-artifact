"""Freeze a v4 re-execution package that reuses the unchanged census runner with a different image/case set.

Used for F1 (v2/Java 8 concordance of the v1 census package) and F6 (random false-rejection panel).
"""
import sys as _sys  # release layout: shared helper modules live in lib/
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / "lib").is_dir()) / "lib"))
import argparse
import json
from collections import Counter
from pathlib import Path

from prepare_multibug_execution import ROOT, digest, rows, write_json

CODE = ["execution_tools/census_runner.py", "execution_tools/census_evidence.py",
        "execution_tools/official_defects4j_runner.py", "execution_tools/run_census.py",
        "prepare_v4_rerun_package.py", "PROTOCOL_V4_BUG_LEVEL.md"]
IMAGES = {
    "v2_jdk8": "sha256:335001efa26b313093968f26dee062e31ae69a8b24f0e9ecb124ae97b73b9323",
    "v3_jdk11": "sha256:9d43d93cc76845e19fb314247714f4015f0c5fd99277e6e90208069024e5d05e",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--image", choices=sorted(IMAGES), required=True)
    ap.add_argument("--addendum", type=Path, required=True)
    ap.add_argument("--from-package", type=Path, help="copy every case of an existing census package")
    ap.add_argument("--candidates", type=Path, help="JSON list of {candidate_id, compile_only} for new cases")
    args = ap.parse_args()
    out = args.output.resolve()
    out.relative_to((ROOT / "results").resolve())
    if out.exists():
        raise FileExistsError(out)
    code = [ROOT / p for p in CODE] + [args.addendum.resolve()]
    inputs = {p.relative_to(ROOT).as_posix(): digest(p) for p in code}
    cases, entries = {}, []
    if args.from_package:
        src = args.from_package.resolve()
        manifest = json.loads((src / "manifest.json").read_text())
        for name, expected in manifest["outputs"].items():
            if digest(src / name) != expected:
                raise ValueError("Source package changed: " + name)
        inputs[(src / "manifest.json").relative_to(ROOT).as_posix()] = digest(src / "manifest.json")
        compile_only = {}
        for job in json.loads((src / "jobs.json").read_text()):
            if job["phase"] == "smoke":
                continue
            for e in job["cases"]:
                compile_only[e["candidate_id"]] = e["compile_only"]
        for k, co in compile_only.items():
            cases[k] = json.loads((src / "cases" / (k + ".json")).read_text())
            entries.append({"candidate_id": k, "compile_only": co})
    if args.candidates:
        wanted = json.loads(args.candidates.read_text())
        inputs[args.candidates.resolve().relative_to(ROOT).as_posix()] = digest(args.candidates.resolve())
        ids = {w["candidate_id"] for w in wanted}
        ctx = {r["context_id"]: r for r in rows(ROOT / "results/contract_step1/contexts.jsonl")}
        for v in rows(ROOT / "results/contract_step1/decision_candidates.jsonl"):
            if v["candidate_id"] in ids:
                cases[v["candidate_id"]] = {"candidate_id": v["candidate_id"], "bug_id": ctx[v["context_id"]]["bug_id"],
                                            "anchor": v["anchor"], "patch": v["patch"], "context_id": v["context_id"]}
        if set(cases) < ids:
            raise ValueError("Missing candidates")
        entries += [{"candidate_id": w["candidate_id"], "compile_only": w["compile_only"]} for w in wanted]
    by_bug = {}
    for e in entries:
        by_bug.setdefault(cases[e["candidate_id"]]["bug_id"], []).append(e)
    jobs = [{"job_id": "full_" + b, "phase": "full", "bug_id": b, "cases": sorted(v, key=lambda e: e["candidate_id"])}
            for b, v in sorted(by_bug.items())]
    out.mkdir(parents=True)
    (out / "cases").mkdir()
    (out / "jobs").mkdir()
    for k, c in cases.items():
        write_json(out / "cases" / (k + ".json"), c)
    for j in jobs:
        write_json(out / "jobs" / (j["job_id"] + ".json"), j)
    write_json(out / "jobs.json", jobs)
    write_json(out / "summary.json", {"candidates": len(cases), "jobs": len(jobs), "image_name": args.image,
                                      "image": IMAGES[args.image], "compile_only": dict(Counter(e["compile_only"] for e in entries))})
    write_json(out / "manifest.json", {"image": IMAGES[args.image], "inputs": inputs,
                                      "outputs": {p.relative_to(out).as_posix(): digest(p) for p in sorted(out.rglob("*")) if p.is_file()}})
    print((out / "summary.json").read_text())


if __name__ == "__main__":
    main()
