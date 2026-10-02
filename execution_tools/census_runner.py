"""Isolated, trigger-only census runner using the pinned official Defects4J CLI."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import shutil
import time

from official_defects4j_runner import place_d4c_method, place_method, run_command, sha
from census_evidence import excluded, interpret, test_evidence, test_headers


def safe_remove(path, root):
    path.resolve().relative_to(root.resolve())
    if path.resolve() == root.resolve():
        raise ValueError("Refusing to remove work root")
    shutil.rmtree(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job", type=Path, required=True)
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if os.name != "posix" or not Path("/.dockerenv").exists():
        raise RuntimeError("Run in the isolated research container only")
    job = json.loads(args.job.read_text())
    bug = job["bug_id"]
    if not re.fullmatch(r"[A-Za-z]+-[0-9]+", bug):
        raise ValueError("Invalid bug")
    cases = []
    for entry in job["cases"]:
        key = entry["candidate_id"]
        if not re.fullmatch(r"obscand_[0-9a-f]{64}", key):
            raise ValueError("Invalid candidate id")
        case = json.loads((args.cases / (key + ".json")).read_text())
        if case["bug_id"] != bug or case["candidate_id"] != key:
            raise ValueError("Case/job mismatch")
        cases.append({**case, "compile_only": entry["compile_only"]})
    if not cases or len({c["candidate_id"] for c in cases}) != len(cases):
        raise ValueError("Empty or duplicate cases")
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    work = Path("/tmp/census-work")
    work.mkdir(exist_ok=False)
    Path(os.environ.get("HOME", "/tmp/home")).mkdir(parents=True, exist_ok=True)
    result = {"bug_id": bug, "status": "started", "setup": [], "variants": [],
              "runner_sha256": sha(Path(__file__).read_bytes()), "labels_changed": False}
    def save():
        temp = out / "result.tmp"
        temp.write_text(json.dumps(result, indent=2) + "\n")
        temp.replace(out / "result.json")
    save()
    try:
        project, number = bug.split("-")
        directory = Path("/defects4j/framework/projects") / project
        meta_out = out / "benchmark_metadata"
        meta_out.mkdir()
        def metadata(path):
            if not path.exists():
                result.setdefault("absent_metadata", []).append(str(path))
                return ""
            target = meta_out / path.relative_to(directory)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            return path.read_text()
        active = {r["bug.id"]: r for r in csv.DictReader(metadata(directory / "active-bugs.csv").splitlines())}
        deprecated = {r["bug.id"]: r for r in csv.DictReader(metadata(directory / "deprecated-bugs.csv").splitlines())}
        if number not in active:
            result.update(status="unresolved_inactive_bug", benchmark_entry=deprecated.get(number))
            return
        record = active[number]
        result["benchmark_entry"] = record
        exclusion_files = [directory / name for name in ("dependent_tests", "random_tests")]
        exclusion_files += [directory / "failing_tests" / record["revision.id." + k] for k in ("buggy", "fixed")]
        result["exclusions"] = sorted({t for path in exclusion_files for t in test_headers(metadata(path))})
        start = time.monotonic()
        for suffix in ("b", "f"):
            action = run_command(["defects4j", "checkout", "-p", project, "-v", number + suffix,
                                  "-w", str(work / suffix)], work, out / f"checkout_{suffix}.log",
                                 1800 - (time.monotonic() - start))
            result["setup"].append(action)
            save()
            if action["exit_code"] != 0 or action["timeout"]:
                raise RuntimeError("Official checkout failed or timed out")
        exports = {}
        for prop in ("dir.src.classes", "classes.modified", "tests.trigger"):
            destination = work / (prop + ".txt")
            action = run_command(["defects4j", "export", "-p", prop, "-o", str(destination)],
                                 work / "b", out / f"export_{prop}.log", 1800 - (time.monotonic() - start))
            result["setup"].append(action)
            if action["exit_code"] != 0 or action["timeout"]:
                raise RuntimeError("Export failed")
            exports[prop] = destination.read_text().strip()
        triggers = exports["tests.trigger"].splitlines()
        if not triggers or len(triggers) != len(set(triggers)):
            raise ValueError("Missing or duplicate triggers")
        result.update(exports=exports, triggers=triggers)
        controls_compile_only = all(c["compile_only"] for c in cases)
        for repeat in (1, 2):
            variants = [("fixed", None), ("buggy", None)] + [(c["candidate_id"], c) for c in cases]
            if repeat == 2:
                variants.reverse()
            for name, case in variants:
                key = f"{name}_r{repeat}"
                dst = work / "variant"
                vr = {"variant": name, "repeat": repeat, "tests": []}
                result["variants"].append(vr)
                began = time.monotonic()
                try:
                    shutil.copytree(work / ("f" if name == "fixed" else "b"), dst, symlinks=True)
                    if case:
                        files = [dst / exports["dir.src.classes"] / (c.replace(".", "/") + ".java")
                                 for c in exports["classes.modified"].splitlines()]
                        for p in files:
                            p.resolve().relative_to(dst.resolve())
                        try:
                            if case.get("placement_mode") == "d4c_normalized_signature":
                                path, data, proof = place_d4c_method(files, case["patch"])
                            else:
                                path, data, proof = place_method(files, case["anchor"], case["patch"])
                        except (ValueError, OSError, UnicodeError) as exc:
                            vr["placement_error"] = str(exc)
                            continue
                        vr["placement"] = {**proof, "source_path": str(path.relative_to(dst))}
                        (out / (key + "_original.java")).write_bytes(path.read_bytes())
                        path.write_bytes(data)
                        (out / (key + "_patched.java")).write_bytes(data)
                    started = time.monotonic()
                    vr["compile"] = run_command(["defects4j", "compile"], dst, out / f"{key}_compile.log", 600)
                    save()
                    if not (vr["compile"]["exit_code"] == 0 and not vr["compile"]["timeout"]):
                        continue
                    compile_only = case["compile_only"] if case else controls_compile_only
                    if compile_only:
                        continue
                    for i, trigger in enumerate(triggers):
                        if excluded(trigger, result["exclusions"]):
                            vr["tests"].append({"trigger": trigger, "excluded": True, "reason": "pinned_known_exclusion"})
                            continue
                        left = 600 - (time.monotonic() - started)
                        if left <= 0:
                            vr["budget_exhausted"] = True
                            break
                        # These two files are recreated by the native formatter.
                        # Removing them first prevents accidentally copying stale evidence.
                        for filename in ("all_tests", "failing_tests"):
                            path = dst / filename
                            path.resolve().relative_to(dst.resolve())
                            if path.exists():
                                path.unlink()
                        log = out / f"{key}_test{i}.log"
                        action = run_command(["defects4j", "test", "-t", trigger], dst, log, left)
                        texts = {}
                        for filename in ("all_tests", "failing_tests"):
                            source = dst / filename
                            source.resolve().relative_to(dst.resolve())
                            texts[filename] = source.read_text(errors="replace") if source.exists() else ""
                            if source.exists():
                                shutil.copyfile(source, out / f"{key}_test{i}_{filename}.txt")
                        action.update(trigger=trigger, excluded=False,
                                      reports_present=all((dst / n).exists() for n in texts),
                                      **test_evidence(log.read_text(errors="replace"), texts["all_tests"], texts["failing_tests"], trigger))
                        action["evidence_valid"] &= action["reports_present"]
                        vr["tests"].append(action)
                        save()
                        if action["timeout"]:
                            break
                finally:
                    vr["seconds"] = time.monotonic() - began
                    save()
                    if dst.exists():
                        safe_remove(dst, work)
        result["status"] = "finished"
    except Exception as exc:
        result.update(status="unresolved_runner_or_setup", error=f"{type(exc).__name__}: {exc}")
    finally:
        result["interpretation"] = interpret(result, cases)
        save()
        files = {str(p.relative_to(out)): sha(p.read_bytes()) for p in sorted(out.rglob("*")) if p.is_file()}
        (out / "manifest.json").write_text(json.dumps(files, indent=2) + "\n")


if __name__ == "__main__":
    main()
