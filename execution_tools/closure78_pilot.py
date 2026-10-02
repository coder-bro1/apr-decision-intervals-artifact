"""Bounded offline Closure-78 execution; never changes dataset/reviewer labels."""

import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "external_artifacts/closure78_execution"
SOURCE = ART / "upstream/closure-compiler-25829b0395164533782d608399096803321225a7"
FRAMEWORK = ROOT / "external_artifacts/defects4j_execution"
D4J_COMMIT = "8c16da8230843cdc918eaf4ddb449637f02b83c6"
FIXED_COMMIT = "25829b0395164533782d608399096803321225a7"
IMAGE = "sha256:ed8fda94050666632c745a4d4c0b40a7894309f8bc2efaa139501f8884078069"
JAVA_PATH = "src/com/google/javascript/jscomp/PeepholeFoldConstants.java"
CASE_ID = "review_66818ac2fa2ba61dd426"
ORDER = ("fixed", "buggy", "candidate", "candidate", "buggy", "fixed")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(path):
    files = {str(p.relative_to(path)).replace("\\", "/"): digest(p)
             for p in sorted(path.rglob("*")) if p.is_file()}
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def protected_hashes():
    paths = ["results/v2/paper_artifact_manifest.json", "results/contract_step1/manifest.json",
             "results/pilot_step2/manifest.json", "results/review_step3/manifest.json",
             "results/review_step3/reviewer_declarations.csv",
             "results/review_step3/reviewer_1/responses.csv",
             "results/review_step3/reviewer_2/responses.csv"]
    return {p: digest(ROOT / p) for p in paths}


def replace_once(source, original, replacement):
    if source.count(original) != 1:
        raise ValueError("Expected exactly one verbatim method match; refusing fuzzy patching.")
    return source.replace(original, replacement, 1)


def parse_log(log):
    pattern = r"^PILOT_RESULT mode=(trigger|class) runs=(\d+) failures=(\d+) errors=(\d+) elapsed_ms=(\d+)$"
    matches = re.findall(pattern, log, re.MULTILINE)
    if len(matches) != 2 or {m[0] for m in matches} != {"trigger", "class"}:
        raise ValueError("Missing or duplicate test outcomes; not a valid execution result.")
    if "PILOT_BUILD_OK" not in log or "PILOT_EXITS" not in log:
        raise ValueError("Build/completion evidence absent.")
    result = {m[0]: dict(zip(("runs", "failures", "errors", "elapsed_ms"), map(int, m[1:])))
              for m in matches}
    if result["trigger"]["runs"] != 1 or result["class"]["runs"] < 2:
        raise ValueError("Unexpected test counts.")
    exits = re.findall(r"^PILOT_EXITS trigger=(\d+) class=(\d+)$", log, re.MULTILINE)
    if len(exits) != 1:
        raise ValueError("Ambiguous process exits.")
    for mode, code in zip(("trigger", "class"), map(int, exits[0])):
        expected = int(result[mode]["failures"] + result[mode]["errors"] > 0)
        if code != expected:
            raise ValueError("Process exit disagrees with test evidence.")
    return result


def prepare(out):
    if out.exists():
        raise FileExistsError("Use a new output directory; pilot records are append-only.")
    commit = subprocess.check_output(["git", "-C", str(FRAMEWORK), "rev-parse", "HEAD"], text=True).strip()
    if commit != D4J_COMMIT:
        raise ValueError("Unexpected Defects4J framework revision.")
    case = next(json.loads(line) for line in (ROOT / "results/review_step3/cases.jsonl").read_text(
        encoding="utf-8").splitlines() if json.loads(line)["case_id"] == CASE_ID)
    refs = json.loads((ROOT / f"results/review_step3/references/{CASE_ID}.json").read_text(
        encoding="utf-8"))["archived_developer_fixes"]
    if case["bug_id"] != "Closure-78" or len(refs) != 1:
        raise ValueError("Unexpected case/reference identity.")
    source = (SOURCE / JAVA_PATH).read_text(encoding="utf-8")
    reference = refs[0].strip()
    variants = {"fixed": source,
                "buggy": replace_once(source, reference, case["buggy_method"].strip()),
                "candidate": replace_once(source, reference, case["candidate_method"].strip())}
    # Independently reconstruct the benchmark bug with Defects4J's official patch.
    out.mkdir(parents=True)
    for variant, text in variants.items():
        path = out / "variants" / f"{variant}.java"
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    patched = out / "official_patch_check" / JAVA_PATH
    patched.parent.mkdir(parents=True)
    patched.write_text(source, encoding="utf-8", newline="\n")
    patch = FRAMEWORK / "framework/projects/Closure/patches/78.src.patch"
    applied = subprocess.run(["git", "apply", "-"], input=patch.read_bytes().replace(b"\r\n", b"\n"),
                             cwd=out / "official_patch_check", capture_output=True)
    if applied.returncode:
        raise RuntimeError(applied.stderr.decode(errors="replace"))
    if patched.read_text(encoding="utf-8") != variants["buggy"]:
        raise ValueError("Archived buggy method differs from official Defects4J bug reconstruction.")
    manifest = {"case_id": CASE_ID, "bug_id": "Closure-78", "defects4j_commit": commit,
                "fixed_commit": FIXED_COMMIT, "image": IMAGE, "run_order": list(ORDER),
                "source_tree_sha256": tree_digest(SOURCE),
                "source_zip_sha256": digest(ART / "downloads/closure-fixed.zip"),
                "official_patch_sha256": digest(patch), "official_bug_reconstruction_matches": True,
                "ant_version": "1.10.15",
                "ant_sha256": {p.name: digest(p) for p in (ART / "tools").glob("*.jar")},
                "variant_sha256": {v: digest(out / "variants" / f"{v}.java") for v in variants},
                "protected_before": protected_hashes(),
                "runner_sha256": {p.name: digest(p) for p in (ROOT / "execution_tools").glob("*") if p.is_file()},
                "scope": "Disclosed single-case engineering pilot; no population effect or new-method claim.",
                "source_target_override": "7 on JDK 11, identical across variants",
                "locale": "C.UTF-8", "timezone": "America/Los_Angeles", "java_encoding": "UTF-8",
                "full_defects4j_cli_used": False, "full_project_test_suite_run": False,
                "cpu_limit": 2, "memory_limit": "3g", "timeout_seconds": 600}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def execute(out):
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    if (out / "summary.json").exists():
        raise FileExistsError("Completed run exists; use a new output directory.")
    if tree_digest(SOURCE) != manifest["source_tree_sha256"]:
        raise ValueError("Upstream source changed after preparation.")
    for name, expected in manifest["runner_sha256"].items():
        if digest(ROOT / "execution_tools" / name) != expected:
            raise ValueError("Runner changed after preparation; prepare a new attempt.")
    for name, expected in manifest["ant_sha256"].items():
        if digest(ART / "tools" / name) != expected:
            raise ValueError("Ant runtime changed after preparation.")
    for variant, expected in manifest["variant_sha256"].items():
        if digest(out / "variants" / f"{variant}.java") != expected:
            raise ValueError("Prepared variant changed.")
    records = []
    try:
        for i, variant in enumerate(ORDER):
            name = f"closure78-pilot-{i}-{int(time.time())}"
            args = ["docker", "run", "--rm", "--name", name, "--network", "none", "--read-only",
                    "--cpus", "2", "--memory", "3g", "--pids-limit", "256", "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,exec,size=2g",
                    "--mount", f"type=bind,source={SOURCE},target=/source,readonly",
                    "--mount", f"type=bind,source={ART / 'tools'},target=/ant,readonly",
                    "--mount", f"type=bind,source={out / 'variants'},target=/variants,readonly",
                    "--mount", f"type=bind,source={ROOT / 'execution_tools'},target=/runner,readonly",
                    "--entrypoint", "/bin/sh", IMAGE, "/runner/run_closure_container.sh", variant]
            path = out / f"run_{i}_{variant}.log"
            if path.exists():
                raise FileExistsError("Prior attempt exists; do not overwrite failed attempts.")
            start = time.monotonic()
            with path.open("w", encoding="utf-8") as log:
                try:
                    proc = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, timeout=600)
                    code = proc.returncode
                except subprocess.TimeoutExpired:
                    subprocess.run(["docker", "kill", name], capture_output=True, timeout=30)
                    code = "timeout"
            record = {"run": i, "variant": variant, "container_exit": code,
                      "end_to_end_seconds": time.monotonic() - start, "command": args,
                      "log": path.name, "log_sha256": digest(path)}
            records.append(record)
            if code != 0:
                record["status"] = "infrastructure_failure_or_timeout"
                raise RuntimeError(f"Execution incomplete: inspect {path}")
            try:
                record["tests"] = parse_log(path.read_text(encoding="utf-8"))
                record["status"] = "executed"
            except ValueError:
                record["status"] = "invalid_or_incomplete_test_evidence"
                raise
            print(json.dumps({k: v for k, v in record.items() if k != "command"}), flush=True)
    finally:
        unchanged = protected_hashes() == manifest["protected_before"]
        result = {"case_id": CASE_ID, "records": records, "complete": len(records) == len(ORDER)
                  and all(r.get("status") == "executed" for r in records),
                  "protected_files_unchanged": unchanged, "dataset_labels_changed": False,
                  "human_reviews_completed": 0, "population_or_method_superiority_claim": False}
        (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        if not unchanged:
            raise RuntimeError("Protected file hashes changed during execution.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to((ROOT / "results").resolve())
    if args.action == "prepare":
        print(json.dumps(prepare(out), indent=2))
    else:
        execute(out)


if __name__ == "__main__":
    main()
