"""Run one frozen pilot bug in a pinned, isolated Defects4J container."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bug", required=True)
    ap.add_argument("--image", required=True, help="Full sha256 image ID, not a mutable tag")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image):
        raise ValueError("Pinned image ID required")
    sample_root = ROOT / "results/multibug_execution/v1"
    sample = json.loads((sample_root / "sample.json").read_text())
    if args.bug not in {r["bug_id"] for r in sample}:
        raise ValueError("Not a frozen pilot bug")
    frozen = json.loads((sample_root / "manifest.json").read_text())
    for name, expected in frozen["outputs"].items():
        if digest(sample_root / name) != expected:
            raise ValueError("Frozen sample artifact changed: " + name)
    out = args.output.resolve()
    out.relative_to((ROOT / "results").resolve())
    out.mkdir(parents=True, exist_ok=False)
    runner = ROOT / "execution_tools/official_defects4j_runner.py"
    inputs = [runner, Path(__file__), ROOT / "CONFLICT_EXECUTION_AMENDMENT.md",
              ROOT / "execution_tools/Dockerfile.defects4j", sample_root / "manifest.json"]
    before = {str(p.relative_to(ROOT)): digest(p) for p in inputs}
    image = subprocess.run(["docker", "image", "inspect", args.image], capture_output=True, text=True, check=True)
    (out / "image_inspect.json").write_text(image.stdout, encoding="utf-8")
    name = "apr-official-" + args.bug.lower() + "-" + hashlib.sha256(str(out).encode()).hexdigest()[:10]
    cmd = ["docker", "run", "--rm", "--name", name, "--network", "none", "--read-only",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--cpus", "2",
           "--memory", "4g", "--pids-limit", "512", "--tmpfs", "/tmp:rw,exec,size=12g",
           "-e", "HOME=/tmp/home", "-e", "TZ=America/Los_Angeles",
           "--mount", f"type=bind,src={sample_root / 'cases'},dst=/cases,readonly",
           "--mount", f"type=bind,src={runner},dst=/runner.py,readonly",
           "--mount", f"type=bind,src={out},dst=/output",
           args.image, "python3", "/runner.py", "--cases", "/cases", "--bug", args.bug,
           "--output", "/output/evidence"]
    state = {"command": cmd, "input_sha256": before, "status": "starting", "image_id": args.image}
    def save():
        (out / "launch.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    save()
    start = time.monotonic()
    try:
        with (out / "container.log").open("wb") as log:
            result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=8500)
        state.update(status="container_exited", exit_code=result.returncode)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True, timeout=30)
        state["status"] = "host_timeout"
    finally:
        state["seconds"] = time.monotonic() - start
        state["inputs_unchanged"] = before == {str(p.relative_to(ROOT)): digest(p) for p in inputs}
        save()
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
