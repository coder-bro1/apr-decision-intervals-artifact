"""E3 HumanEval-Java re-execution (ADDENDUM_V4_E3_HUMANEVAL.md).

build: python run_humaneval_e3.py build --targets <jsonl> --package <dir>
    one input folder per bug: fixed control (correct file, package renamed), buggy control, and each candidate placed
    into the buggy file by exact anchor replacement (place_method). Placement failures are recorded, not executed.
run:   python run_humaneval_e3.py run --package <dir> --output <dir> [--workers N]
    one container per bug (pinned image, no network, read-only root), resumable: finished bugs keep their
    terminal.json; a non-terminal attempt must first be moved aside by tools/resume_prep.py (prefix apr-he-)."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "execution_tools"))
from official_defects4j_runner import place_method  # noqa: E402

BENCH = ROOT / "external_artifacts/repairbench-framework/benchmarks/human-eval-java"
BENCH_COMMIT = "1f2e51909f3b35a16cb25017f751b255c1bef0ad"
IMAGE_TAG = "maven:3.9-eclipse-temurin-8"
FIXED = ["execution_tools/humaneval_e3_run.sh", "execution_tools/run_humaneval_e3.py", "ADDENDUM_V4_E3_HUMANEVAL.md"]


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, obj):
    tmp = Path(str(p) + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1), encoding="utf-8")
    tmp.replace(p)


def build(args):
    head = subprocess.run(["git", "-C", str(BENCH), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    if head != BENCH_COMMIT:
        raise ValueError("HumanEval-Java checkout is not the pinned commit")
    pkg = args.package.resolve()
    pkg.relative_to((ROOT / "results").resolve())
    if pkg.exists():
        raise FileExistsError(pkg)
    recs = [json.loads(l) for l in open(args.targets, encoding="utf-8") if l.strip()]
    by_bug = defaultdict(list)
    for r in recs:
        by_bug[r["bug_id"]].append(r)
    src = BENCH / "src/main/java/humaneval"
    jobs, placement = [], {}
    for bug in sorted(by_bug):
        d = pkg / bug
        buggy, correct = (src / "buggy" / f"{bug}.java"), (src / "correct" / f"{bug}.java")
        ctext = correct.read_text(encoding="utf-8").replace("\r\n", "\n")
        if ctext.count("package humaneval.correct;") != 1:
            raise ValueError("unexpected package line in " + bug)
        variants = {"fixed": ctext.replace("package humaneval.correct;", "package humaneval.buggy;"),
                    "buggy": buggy.read_text(encoding="utf-8").replace("\r\n", "\n")}
        cands = {}
        for n, r in enumerate(sorted(by_bug[bug], key=lambda x: x["candidate_id"]), 1):
            v = f"c{n:04d}"
            try:
                _, patched, meta = place_method([buggy], r["anchor"], r["patch"])
                variants[v] = patched.decode("utf-8")
                placement[r["candidate_id"]] = "placed"
                cands[v] = {"candidate_id": r["candidate_id"], **meta}
            except ValueError as e:
                placement[r["candidate_id"]] = "unresolved_placement: " + str(e)
        for v, text in variants.items():
            (d / "variants" / v).mkdir(parents=True)
            (d / "variants" / v / f"{bug}.java").write_bytes(text.encode("utf-8"))
        (d / "bug").write_bytes(bug.encode())
        write(d / "job.json", {"bug": bug, "candidates": cands})
        jobs.append({"job_id": bug, "candidates": len(cands)})
    outputs = {q.relative_to(pkg).as_posix(): digest(q) for q in sorted(pkg.rglob("*")) if q.is_file()}
    write(pkg / "placement.json", placement)
    write(pkg / "manifest.json", {"targets": str(Path(args.targets).resolve().relative_to(ROOT).as_posix()),
                                  "targets_sha256": digest(args.targets), "bench_commit": head,
                                  "image": image_id(), "jobs": jobs, "outputs": outputs,
                                  "placement_sha256": digest(pkg / "placement.json")})
    placed = sum(v == "placed" for v in placement.values())
    print(f"package {pkg.name}: {len(jobs)} bugs, {placed}/{len(placement)} candidates placed")


def image_id():
    ins = subprocess.run(["docker", "image", "inspect", IMAGE_TAG], capture_output=True, text=True, check=True, timeout=60)
    return json.loads(ins.stdout)[0]["Id"]


def execute(pkg, out, job, image, package_hash):
    path = out / job["job_id"]
    if (path / "terminal.json").exists():
        t = json.loads((path / "terminal.json").read_text())
        if t["package_sha256"] != package_hash:
            raise ValueError("terminal from a different package")
        return t
    if path.exists():
        raise RuntimeError(f"Nonterminal attempt preserved at {path}; run tools/resume_prep.py first")
    path.mkdir()
    name = "apr-he-" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    cmd = ["docker", "run", "--name", name, "--hostname", "localhost", "--network", "none", "--read-only",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--cpus", "1", "--memory", "1g",
           "--memory-swap", "1g", "--pids-limit", "512", "--tmpfs", "/tmp:rw,exec,size=2g", "-e", "HOME=/tmp",
           "--mount", f"type=bind,src={pkg / job['job_id']},dst=/inputs,readonly",
           "--mount", f"type=bind,src={BENCH},dst=/bench,readonly",
           "--mount", f"type=bind,src={ROOT / 'execution_tools'},dst=/tools,readonly",
           "--mount", f"type=bind,src={path},dst=/output", image, "bash", "/tools/humaneval_e3_run.sh"]
    launch = {"command": cmd, "job_id": job["job_id"], "image": image, "package_sha256": package_hash,
              "started_utc": datetime.now(timezone.utc).isoformat()}
    write(path / "launch.json", launch)
    start = time.monotonic()
    try:
        with (path / "container.log").open("wb") as log:
            p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=600 + 1300 * (job["candidates"] + 2))
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
    ok = (path / "res/ALLDONE").exists() and launch.get("exit_code") == 0 and not launch.get("oom_killed")
    terminal = {"job_id": job["job_id"], "package_sha256": package_hash, "container_ok": ok, "seconds": launch["seconds"],
                "files": {q.relative_to(path).as_posix(): digest(q) for q in sorted(path.rglob("*")) if q.is_file()}}
    write(path / "terminal.json", terminal)
    return terminal


def run(args):
    pkg = args.package.resolve()
    manifest = json.loads((pkg / "manifest.json").read_text())
    for rel, h in manifest["outputs"].items():
        if digest(pkg / rel) != h:
            raise ValueError("package file changed: " + rel)
    image = manifest["image"]
    if image_id() != image:
        raise ValueError("Pinned image mismatch")
    out = args.output.resolve()
    out.relative_to((ROOT / "results").resolve())
    out.mkdir(parents=True, exist_ok=True)
    package_hash = digest(pkg / "manifest.json")
    fixed = {p: digest(ROOT / p) for p in FIXED}
    receipt = out / "launch_receipt.json"
    if receipt.exists():
        prev = json.loads(receipt.read_text())
        if prev["package_sha256"] != package_hash or prev["fixed_code"] != fixed:
            raise ValueError("Receipt belongs to different inputs")
    else:
        write(receipt, {"package_sha256": package_hash, "image": image, "fixed_code": fixed})
    jobs = [j for j in manifest["jobs"] if not args.only or j["job_id"] in args.only]
    done = [0]

    def one(j):
        for p, h in fixed.items():
            if digest(ROOT / p) != h:
                raise ValueError("Code or addendum changed during batch: " + p)
        t = execute(pkg, out, j, image, package_hash)
        done[0] += 1
        print(f"[{done[0]}/{len(jobs)}] {j['job_id']} ({j['candidates']} candidates) ok={t['container_ok']} {t['seconds']:.0f}s", flush=True)
        return t

    with ThreadPoolExecutor(args.workers) as ex:
        results = list(ex.map(one, jobs))
    write(out / "progress.json", {"jobs_total": len(jobs), "container_ok": sum(r["container_ok"] for r in results)})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--targets", type=Path, required=True)
    b.add_argument("--package", type=Path, required=True)
    r = sub.add_parser("run")
    r.add_argument("--package", type=Path, required=True)
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--only", nargs="*")
    args = ap.parse_args()
    build(args) if args.cmd == "build" else run(args)


if __name__ == "__main__":
    main()
