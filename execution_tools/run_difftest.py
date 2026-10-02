"""F3 host launcher: resumable, one container per bug job, same isolation as the census launcher.

Package: built by prepare_v4_rerun_package.py --image v2_jdk8 (cases/, jobs/, manifest.json). The in-container
runner is execution_tools/difftest_runner.py; its hash and the addendum hash are fixed in the launch receipt, and the
batch stops if either changes while running.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from execution_tools.run_census import digest, load_package, verify, write  # noqa: E402

FIXED = ["execution_tools/difftest_runner.py", "execution_tools/official_defects4j_runner.py",
         "ADDENDUM_V4_F3_DIFFTEST.md"]


def execute(package, out, job, image, package_hash):
    path = out / job["job_id"]
    if (path / "terminal.json").exists():
        t = json.loads((path / "terminal.json").read_text())
        if t["package_sha256"] != package_hash:
            raise ValueError("terminal from a different package")
        verify(path, t["files"])
        return t
    if path.exists():
        raise RuntimeError(f"Nonterminal attempt preserved at {path}; diagnose first")
    path.mkdir()
    name = "apr-difftest-" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    # --hostname localhost: with --network none the random container hostname does not resolve, which breaks
    # EvoSuite's local RMI between master and client processes.
    cmd = ["docker", "run", "--name", name, "--hostname", "localhost", "--network", "none", "--read-only", "--cap-drop", "ALL",
           "--security-opt", "no-new-privileges", "--cpus", "2", "--memory", "4g", "--memory-swap", "4g",
           "--pids-limit", "1024", "--tmpfs", "/tmp:rw,exec,size=16g", "-e", "HOME=/tmp/home",
           "-e", "TZ=America/Los_Angeles", "--mount", f"type=bind,src={package},dst=/inputs,readonly",
           "--mount", f"type=bind,src={ROOT / 'execution_tools'},dst=/tools,readonly",
           "--mount", f"type=bind,src={path},dst=/output", image, "python3", "/tools/difftest_runner.py",
           "--job", f"/inputs/jobs/{job['job_id']}.json", "--cases", "/inputs/cases", "--output", "/output/evidence"]
    launch = {"command": cmd, "job_id": job["job_id"], "image": image, "package_sha256": package_hash,
              "started_utc": datetime.now(timezone.utc).isoformat()}
    write(path / "launch.json", launch)
    start = time.monotonic()
    try:
        with (path / "container.log").open("wb") as log:
            p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                               timeout=3600 * 2 + 3600 * 2 * (len(job["cases"]) + 2))
        launch.update(status="container_exited", exit_code=p.returncode)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True, timeout=60)
        launch["status"] = "host_timeout"
    finally:
        launch["seconds"] = time.monotonic() - start
        st = subprocess.run(["docker", "inspect", name], capture_output=True, text=True, timeout=60)
        if st.returncode == 0:
            ins = json.loads(st.stdout)[0]
            launch["oom_killed"] = ins["State"]["OOMKilled"]
            if not ins["State"]["Running"]:
                subprocess.run(["docker", "rm", name], capture_output=True, timeout=60)
        write(path / "launch.json", launch)
    rp = path / "evidence/result.json"
    ok = rp.exists() and launch.get("exit_code") == 0 and not launch.get("oom_killed")
    if ok:
        verify(path / "evidence", json.loads((path / "evidence/manifest.json").read_text()))
    terminal = {"job_id": job["job_id"], "package_sha256": package_hash, "container_ok": ok,
                "seconds": launch["seconds"],
                "files": {q.relative_to(path).as_posix(): digest(q) for q in sorted(path.rglob("*")) if q.is_file()}}
    write(path / "terminal.json", terminal)
    return terminal


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--only", nargs="*", help="job ids to run (smoke test)")
    args = ap.parse_args()
    package = args.package.resolve()
    manifest, jobs = load_package(package)
    image = manifest["image"]
    ins = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, check=True, timeout=60)
    if json.loads(ins.stdout)[0]["Id"] != image:
        raise ValueError("Pinned image mismatch")
    out = args.output.resolve()
    out.relative_to((ROOT / "results").resolve())
    out.mkdir(parents=True, exist_ok=True)
    package_hash = digest(package / "manifest.json")
    fixed = {p: digest(ROOT / p) for p in FIXED}
    receipt = out / "launch_receipt.json"
    if receipt.exists():
        prev = json.loads(receipt.read_text())
        if prev["package_sha256"] != package_hash or prev["fixed_code"] != fixed:
            raise ValueError("Receipt belongs to different inputs")
    else:
        write(receipt, {"package_sha256": package_hash, "image": image, "fixed_code": fixed})
    selected = [j for j in jobs if not args.only or j["job_id"] in args.only]

    def run(j):
        for p, h in fixed.items():
            if digest(ROOT / p) != h:
                raise ValueError("Code or addendum changed during batch: " + p)
        verify(package, manifest["outputs"])
        t = execute(package, out, j, image, package_hash)
        print(f"done {j['job_id']} ok={t['container_ok']} {t['seconds']:.0f}s", flush=True)
        return t

    with ThreadPoolExecutor(args.workers) as ex:
        results = list(ex.map(run, selected))
    write(out / "progress.json", {"jobs_total": len(selected), "container_ok": sum(r["container_ok"] for r in results)})


if __name__ == "__main__":
    main()
