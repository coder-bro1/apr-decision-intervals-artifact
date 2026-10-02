"""F3 in-container differential-test runner (ADDENDUM_V4_F3_DIFFTEST.md). Produces evidence, never labels.

Per bug: checkout b and f; generate EvoSuite (ids 1, 2) and Randoop (id 1) suites on f for the modified classes
(180 s each); remove tests failing on f with fix_test_suite.pl; run every remaining suite twice on f, b and each
candidate (placed into b with the census place_method; the second repetition reverses the variant order).
"""
import argparse
import json
import os
import re
import shutil
import tarfile
import time
from pathlib import Path

from official_defects4j_runner import place_method, run_command, sha

GENERATORS = (("evosuite", 1), ("evosuite", 2), ("randoop", 1))
BUDGET = 180


def headers(text):
    return sorted({m.group(1).strip() for m in re.finditer(r"^--- (\S+)", text, re.MULTILINE)})


def safe_rm(path, root):
    path.resolve().relative_to(root.resolve())
    if path.exists():
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
    for e in job["cases"]:
        if not re.fullmatch(r"obscand_[0-9a-f]{64}", e["candidate_id"]):
            raise ValueError("Invalid candidate id")
        c = json.loads((args.cases / (e["candidate_id"] + ".json")).read_text())
        if c["bug_id"] != bug:
            raise ValueError("Case/job mismatch")
        cases.append(c)
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    work = Path("/tmp/difftest-work")
    work.mkdir()
    Path(os.environ.get("HOME", "/tmp/home")).mkdir(parents=True, exist_ok=True)
    shims = []
    if shutil.which("bc") is None:
        # Defects4J's evosuite.sh/randoop.sh compute per-class budgets with `echo "a/b/c" | bc`; the pinned image lacks
        # bc. This shim evaluates the same integer expression with bash arithmetic (bc's default scale is 0).
        sb = Path("/tmp/shim-bin")
        sb.mkdir(exist_ok=True)
        (sb / "bc").write_text('#!/usr/bin/env bash\nread -r e\necho $(( e ))\n')
        (sb / "bc").chmod(0o755)
        os.environ["PATH"] = f"{sb}:{os.environ['PATH']}"
        shims.append("bc (bash integer arithmetic)")
    res = {"shims": shims,"bug_id": bug, "status": "started", "setup": [], "suites": {}, "runs": [],
           "runner_sha256": sha(Path(__file__).read_bytes()), "labels_changed": False}

    def save():
        tmp = out / "result.tmp"
        tmp.write_text(json.dumps(res, indent=2) + "\n")
        tmp.replace(out / "result.json")

    save()
    try:
        project, number = bug.split("-")
        start = time.monotonic()
        for suffix in ("b", "f"):
            a = run_command(["defects4j", "checkout", "-p", project, "-v", number + suffix, "-w", str(work / suffix)],
                            work, out / f"checkout_{suffix}.log", 1800)
            res["setup"].append(a)
            if a["exit_code"] != 0 or a["timeout"]:
                raise RuntimeError("checkout failed")
        exports = {}
        for prop in ("dir.src.classes", "classes.modified"):
            dest = work / (prop + ".txt")
            a = run_command(["defects4j", "export", "-p", prop, "-o", str(dest)], work / "b", out / f"export_{prop}.log", 600)
            if a["exit_code"] != 0:
                raise RuntimeError("export failed")
            exports[prop] = dest.read_text().strip()
        res["exports"] = exports
        gen = work / "gen"
        suites_dir = work / "suites"
        suites_dir.mkdir()
        for g, sid in GENERATORS:
            a = run_command(["gen_tests.pl", "-g", g, "-p", project, "-v", number + "f", "-n", str(sid),
                             "-o", str(gen), "-b", str(BUDGET), "-s", str(sid)], work, out / f"gen_{g}_{sid}.log",
                            BUDGET * 4 + 900)
            res["setup"].append({**a, "generator": g, "suite_id": sid})
            for p in gen.rglob("*.tar.bz2"):
                if not (suites_dir / p.name).exists():
                    shutil.copyfile(p, suites_dir / p.name)
            save()
        res["suites_generated"] = sorted(p.name for p in suites_dir.glob("*.tar.bz2"))
        a = run_command(["perl", "/defects4j/framework/util/fix_test_suite.pl", "-p", project, "-d", str(suites_dir),
                         "-v", number + "f"], work, out / "fix_test_suite.log", 7200)
        res["setup"].append({**a, "step": "fix_test_suite"})
        suites = sorted(p for p in suites_dir.glob("*.tar.bz2"))
        keep = out / "suites"
        keep.mkdir()
        for p in suites:
            shutil.copyfile(p, keep / p.name)
            try:
                with tarfile.open(p) as t:
                    n = sum(1 for m in t.getmembers() if m.name.endswith(".java"))
            except tarfile.TarError:
                n = -1
            res["suites"][p.name] = {"java_files": n, "sha256": sha(p.read_bytes())}
        save()
        variants = [("fixed", None), ("buggy", None)] + [(c["candidate_id"], c) for c in cases]
        for repeat in (1, 2):
            order = variants if repeat == 1 else list(reversed(variants))
            for name, case in order:
                dst = work / "variant"
                vr = {"variant": name, "repeat": repeat, "suites": {}}
                res["runs"].append(vr)
                try:
                    shutil.copytree(work / ("f" if name == "fixed" else "b"), dst, symlinks=True)
                    if case:
                        files = [dst / exports["dir.src.classes"] / (c.replace(".", "/") + ".java")
                                 for c in exports["classes.modified"].splitlines()]
                        try:
                            path, data, proof = place_method(files, case["anchor"], case["patch"])
                        except (ValueError, OSError, UnicodeError) as exc:
                            vr["placement_error"] = str(exc)
                            continue
                        path.write_bytes(data)
                        vr["placement"] = proof
                    key = f"{name[:24]}_r{repeat}"
                    vr["compile"] = run_command(["defects4j", "compile"], dst, out / f"{key}_compile.log", 900)
                    if vr["compile"]["exit_code"] != 0 or vr["compile"]["timeout"]:
                        continue
                    for s in suites:
                        for fn in ("all_tests", "failing_tests"):
                            if (dst / fn).exists():
                                (dst / fn).unlink()
                        log = out / f"{key}_{s.stem}.log"
                        a = run_command(["defects4j", "test", "-s", str(s)], dst, log, 1800)
                        ft = (dst / "failing_tests").read_text(errors="replace") if (dst / "failing_tests").exists() else ""
                        at = (dst / "all_tests").read_text(errors="replace") if (dst / "all_tests").exists() else ""
                        if ft:
                            (out / f"{key}_{s.stem}_failing_tests.txt").write_text(ft)
                        vr["suites"][s.name] = {"exit_code": a["exit_code"], "timeout": a["timeout"],
                                                "executed": len([x for x in at.splitlines() if x.strip()]),
                                                "failing": headers(ft), "reports_present": bool(at)}
                        save()
                finally:
                    safe_rm(dst, work)
                    save()
        res["status"] = "finished"
    except Exception as exc:
        res.update(status="unresolved_runner_or_setup", error=f"{type(exc).__name__}: {exc}")
    finally:
        res["seconds"] = time.monotonic() - start if "start" in dir() else None
        save()
        files = {str(p.relative_to(out)): sha(p.read_bytes()) for p in sorted(out.rglob("*")) if p.is_file()}
        (out / "manifest.json").write_text(json.dumps(files, indent=2) + "\n")


if __name__ == "__main__":
    main()
