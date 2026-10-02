"""Single-worker, resumable census launcher. Controls and census are separate phases."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from execution_tools.census_evidence import interpret


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, obj):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def verify(base, mapping):
    for name, expected in mapping.items():
        path = (base / name.replace("\\", "/")).resolve()
        path.relative_to(base.resolve())
        if digest(path) != expected:
            raise ValueError("Hash mismatch: " + str(path))


def load_package(package):
    manifest = json.loads((package / "manifest.json").read_text())
    verify(ROOT, manifest["inputs"])
    verify(package, manifest["outputs"])
    return manifest, json.loads((package / "jobs.json").read_text())


def completed(path, job, package_hash):
    terminal = json.loads((path / "terminal.json").read_text())
    if terminal["job_id"] != job["job_id"] or terminal["package_sha256"] != package_hash:
        raise ValueError("Completed job belongs to different inputs")
    verify(path, terminal["files"])
    analysis = json.loads((path / "analysis.json").read_text())
    if terminal["findings"] != analysis["findings"] or terminal["controls_compile"] != analysis["controls_compile"]:
        raise ValueError("Terminal record disagrees with verified analysis")
    return terminal


def execute(package, out, job, image, package_hash):
    path = out / job["job_id"]
    if path.exists():
        if not (path / "terminal.json").exists():
            raise RuntimeError(f"Nonterminal attempt preserved at {path}; diagnose before an explicit new output directory")
        return completed(path, job, package_hash)
    path.mkdir()
    name = "apr-census-" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    command = ["docker", "run", "--name", name, "--network", "none", "--read-only",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--cpus", "2",
               "--memory", "4g", "--memory-swap", "4g", "--pids-limit", "512",
               "--tmpfs", "/tmp:rw,exec,size=12g", "-e", "HOME=/tmp/home", "-e", "TZ=America/Los_Angeles",
               "--mount", f"type=bind,src={package},dst=/inputs,readonly",
               "--mount", f"type=bind,src={ROOT / 'execution_tools'},dst=/tools,readonly",
               "--mount", f"type=bind,src={path},dst=/output",
               image, "python3", "/tools/census_runner.py", "--job", f"/inputs/jobs/{job['job_id']}.json",
               "--cases", "/inputs/cases", "--output", "/output/evidence"]
    launch = {"command": command, "job_id": job["job_id"], "image": image,
              "package_sha256": package_hash, "started_utc": datetime.now(timezone.utc).isoformat(), "status": "starting"}
    write(path / "launch.json", launch)
    start = time.monotonic()
    inspected = None
    try:
        with (path / "container.log").open("wb") as log:
            proc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                  timeout=1800 + 1200 * (len(job["cases"]) + 2) + 900)
        launch.update(status="container_exited", exit_code=proc.returncode)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True, timeout=60)
        launch["status"] = "host_timeout"
    except BaseException:
        # Only kill this launcher's uniquely named container, never other jobs.
        subprocess.run(["docker", "kill", name], capture_output=True, timeout=60)
        launch["status"] = "interrupted_requires_diagnosis"
        raise
    finally:
        launch["seconds"] = time.monotonic() - start
        state = subprocess.run(["docker", "inspect", name], capture_output=True, text=True, timeout=60)
        if state.returncode == 0:
            inspected = json.loads(state.stdout)[0]
            write(path / "container_inspect.json", inspected)
            if not inspected["State"]["Running"]:
                removed = subprocess.run(["docker", "rm", name], capture_output=True, text=True, timeout=60)
                launch["container_removed"] = removed.returncode == 0
        write(path / "launch.json", launch)
    result_path = path / "evidence/result.json"
    good_container = (launch.get("exit_code") == 0 and inspected is not None
                      and not inspected["State"]["OOMKilled"] and not inspected["State"]["Running"])
    if result_path.exists() and good_container:
        result = json.loads(result_path.read_text())
        verify(path / "evidence", json.loads((path / "evidence/manifest.json").read_text()))
        if result["bug_id"] != job["bug_id"]:
            raise ValueError("Result bug mismatch")
        analysis = interpret(result, job["cases"])
        if analysis != result["interpretation"]:
            raise ValueError("Host and container interpretations differ")
    else:
        analysis = {"controls_compile": False, "admissible_triggers": [], "labels_changed": False,
                    "findings": [{"candidate_id": c["candidate_id"], "compile_status": "unknown",
                                  "evidence_status": "unresolved_container_failure", "rejection_witnesses": []} for c in job["cases"]]}
    write(path / "analysis.json", analysis)
    terminal = {"job_id": job["job_id"], "package_sha256": package_hash,
                "findings": analysis["findings"], "controls_compile": analysis["controls_compile"],
                "seconds": launch["seconds"], "container_ok": good_container,
                "files": {p.relative_to(path).as_posix(): digest(p) for p in sorted(path.rglob("*")) if p.is_file()}}
    write(path / "terminal.json", terminal)
    return terminal


def compatibility(worklist, findings):
    report = []
    for r in worklist:
        if r["role"] != "compatibility_control" or r["candidate_id"] not in findings:
            continue
        f = findings[r["candidate_id"]]
        expected_compile = r["stratum"] != "incorrect_compile_fail"
        observed = f["compile_status"]
        status = f["evidence_status"]
        comparison = "unresolved"
        if not status.startswith("unresolved"):
            if observed == "compile_pass":
                comparison = "compile_pass_agrees" if expected_compile else "compile_discrepancy"
            elif observed == "compile_command_failed_twice":
                comparison = "compile_discrepancy" if expected_compile else "nonzero_compile_exit_agrees_diagnosis_pending"
        test_comparison = "not_compared"
        if observed == "compile_pass" and not r["stratum"].endswith("compile_fail"):
            if status == "controlled_trigger_failure":
                test_comparison = "test_discrepancy" if r["stratum"].endswith("test_pass") else "trigger_failure_compatible_with_archive"
            elif status == "admissible_triggers_pass_semantics_unknown":
                test_comparison = "trigger_pass_only_full_suite_not_compared"
            else:
                test_comparison = "unresolved"
        report.append({"candidate_id": r["candidate_id"], "bug_id": r["bug_id"], "stratum": r["stratum"],
                       "compile_comparison": comparison, "test_comparison": test_comparison,
                       "evidence_status": status})
    return {"candidates": len(report), "compile_comparisons": dict(Counter(r["compile_comparison"] for r in report)),
            "test_comparisons": dict(Counter(r["test_comparison"] for r in report)), "records": report,
            "note": "Coverage-oriented controls, not a population agreement estimate; trigger passes do not reproduce archived full-suite passes."}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package", type=Path, required=True)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--phase", choices=("smoke", "controls", "census", "full"))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--acknowledge-control-review", action="store_true")
    args = ap.parse_args()
    package = args.package.resolve()
    package.relative_to((ROOT / "results").resolve())
    manifest, jobs = load_package(package)
    image = manifest["image"]
    info = subprocess.run(["docker", "info", "--format", "{{json .}}"], capture_output=True, text=True, check=True, timeout=60)
    resources = json.loads(info.stdout)
    if resources["MemTotal"] < 5 * 1024**3:
        raise RuntimeError("Docker VM needs at least 5 GiB for one 4-GiB worker plus headroom")
    inspected = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, check=True, timeout=60)
    if json.loads(inspected.stdout)[0]["Id"] != image:
        raise ValueError("Pinned image mismatch")
    print(json.dumps({"package_verified": True, "image": image, "docker_memory_bytes": resources["MemTotal"],
                      "workers": 1, "jobs": dict(Counter(j["phase"] for j in jobs))}), flush=True)
    if args.check:
        return
    if not args.output or not args.phase:
        ap.error("--output and --phase required unless --check")
    out = args.output.resolve()
    out.relative_to((ROOT / "results").resolve())
    if out == package or out.is_relative_to(package) or package.is_relative_to(out):
        raise ValueError("Execution output must be separate from the frozen package")
    out.mkdir(parents=True, exist_ok=True)
    package_hash = digest(package / "manifest.json")
    if args.phase not in ("smoke", "full"):
        smoke = [completed(out / j["job_id"], j, package_hash) for j in jobs if j["phase"] == "smoke"]
        statuses = Counter(f["evidence_status"] for r in smoke for f in r["findings"])
        if statuses != {"controlled_trigger_failure": 1, "admissible_triggers_pass_semantics_unknown": 1}:
            raise RuntimeError("Both known pilot smoke fixtures must reproduce with new execution evidence")
    if args.phase == "census":
        if not args.acknowledge_control_review:
            raise RuntimeError("Inspect compatibility_report.json, then explicitly acknowledge the control review")
        controls = [completed(out / j["job_id"], j, package_hash) for j in jobs if j["phase"] == "controls"]
        findings = {f["candidate_id"]: f for r in controls for f in r["findings"]}
        report = compatibility(json.loads((package / "worklist.json").read_text()), findings)
        if report["candidates"] != 75:
            raise RuntimeError("Incomplete control coverage")
        write(out / "compatibility_report.json", report)
    lock = out / "worker.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    os.close(fd)
    try:
        write(lock, {"pid": os.getpid(), "phase": args.phase, "package_sha256": package_hash})
        receipt = out / (args.phase + "_launch_receipt.json")
        if not receipt.exists():
            write(receipt, {"package_sha256": package_hash, "phase": args.phase, "image": image,
                            "control_review_acknowledged": args.acknowledge_control_review,
                            "control_report_sha256": digest(out / "compatibility_report.json") if args.phase == "census" else None,
                            "docker_resources": {k: resources[k] for k in ("MemTotal", "NCPU")}})
        else:
            previous = json.loads(receipt.read_text())
            if previous["package_sha256"] != package_hash:
                raise ValueError("Receipt belongs to a different package")
        selected = [j for j in jobs if j["phase"] == args.phase]
        terminal = []
        for i, job in enumerate(selected, 1):
            print(f"[{i}/{len(selected)}] {job['job_id']}", flush=True)
            # Fail closed if code/protocol inputs have changed while unattended.
            for p, h in manifest["inputs"].items():
                if p.endswith((".py", ".md")) and digest(ROOT / p) != h:
                    raise ValueError("Code or protocol changed during batch: " + p)
            verify(package, manifest["outputs"])
            terminal.append(execute(package, out, job, image, package_hash))
            findings = {f["candidate_id"]: f for r in terminal for f in r["findings"]}
            write(out / (args.phase + "_progress.json"), {
                "phase": args.phase, "jobs_completed": i, "jobs_total": len(selected),
                "candidates_completed": len(findings), "statuses": dict(Counter(f["evidence_status"] for f in findings.values())),
                "container_seconds": sum(r["seconds"] for r in terminal),
                "complete": i == len(selected), "labels_changed": False,
                "terminal_hashes": {r["job_id"]: digest(out / r["job_id"] / "terminal.json") for r in terminal}})
            if args.phase == "controls":
                write(out / "compatibility_report.json", compatibility(json.loads((package / "worklist.json").read_text()), findings))
        print(f"Phase {args.phase} complete. Results: {out}", flush=True)
    finally:
        lock.unlink()


if __name__ == "__main__":
    main()
