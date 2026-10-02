"""Build the G1-F3 difftest package (ADDENDUM_V4_G1_F3.md) in the exact layout of prepare_v4_rerun_package.py
(cases/, jobs/, jobs.json, summary.json, manifest.json), copying the selected representatives' cases from the G1
tier-P census package. Image: v2_jdk8 (as F3)."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "results/g1/exec_tierP_package_v1"
SEL = ROOT / "results/g1/f3_targets/candidates.json"
OUT = ROOT / "results/g1/f3_package_v1"
IMAGE = "sha256:335001efa26b313093968f26dee062e31ae69a8b24f0e9ecb124ae97b73b9323"
CODE = ["execution_tools/difftest_runner.py", "execution_tools/run_difftest.py", "execution_tools/official_defects4j_runner.py",
        "ADDENDUM_V4_F3_DIFFTEST.md", "ADDENDUM_V4_G1_F3.md", "analysis_tools/v4/select_g1_f3_targets.py",
        "analysis_tools/v4/prepare_g1_difftest_package.py"]


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write_json(p, obj):
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    src_manifest = json.loads((SRC / "manifest.json").read_text())
    for name, h in src_manifest["outputs"].items():
        if digest(SRC / name) != h:
            raise ValueError("source package changed: " + name)
    wanted = json.loads(SEL.read_text())
    cases = {w["candidate_id"]: json.loads((SRC / "cases" / (w["candidate_id"] + ".json")).read_text()) for w in wanted}
    by_bug = {}
    for w in wanted:
        by_bug.setdefault(cases[w["candidate_id"]]["bug_id"], []).append({"candidate_id": w["candidate_id"], "compile_only": False})
    jobs = [{"job_id": "full_" + b, "phase": "full", "bug_id": b, "cases": sorted(v, key=lambda e: e["candidate_id"])}
            for b, v in sorted(by_bug.items())]
    OUT.mkdir(parents=True)
    (OUT / "cases").mkdir()
    (OUT / "jobs").mkdir()
    for k, c in cases.items():
        write_json(OUT / "cases" / (k + ".json"), c)
    for j in jobs:
        write_json(OUT / "jobs" / (j["job_id"] + ".json"), j)
    write_json(OUT / "jobs.json", jobs)
    write_json(OUT / "summary.json", {"candidates": len(cases), "jobs": len(jobs), "image_name": "v2_jdk8", "image": IMAGE,
                                      "compile_only": dict(Counter("false" for _ in cases))})
    inputs = {p: digest(ROOT / p) for p in CODE}
    inputs[SEL.relative_to(ROOT).as_posix()] = digest(SEL)
    inputs[(SRC / "manifest.json").relative_to(ROOT).as_posix()] = digest(SRC / "manifest.json")
    write_json(OUT / "manifest.json", {"image": IMAGE, "inputs": inputs,
                                       "outputs": {p.relative_to(OUT).as_posix(): digest(p) for p in sorted(OUT.rglob("*")) if p.is_file()}})
    print((OUT / "summary.json").read_text())


if __name__ == "__main__":
    main()
