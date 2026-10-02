"""Execute the remaining frozen multi-bug pilot cases sequentially."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-bug", action="append", default=[])
    args = parser.parse_args()
    if not args.image.startswith("sha256:") or len(args.image) != 71:
        raise ValueError("Full image ID required")
    out = args.output.resolve()
    out.relative_to((ROOT / "results").resolve())
    out.mkdir(parents=True, exist_ok=False)
    sample_path = ROOT / "results/multibug_execution/v1/sample.json"
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    bugs = [row["bug_id"] for row in sample if row["bug_id"] not in set(args.skip_bug)]
    launcher = ROOT / "execution_tools/launch_official_pilot.py"
    inputs = {str(path.relative_to(ROOT)): digest(path) for path in (
        sample_path, launcher, ROOT / "execution_tools/official_defects4j_runner.py",
        ROOT / "CONFLICT_EXECUTION_AMENDMENT.md", Path(__file__))}
    state = {"image_id": args.image, "bugs": bugs, "skipped_bugs": args.skip_bug,
             "input_sha256": inputs, "runs": [], "status": "running"}
    state_path = out / "batch_state.json"
    save(state_path, state)
    for bug in bugs:
        run_out = out / bug
        command = [sys.executable, str(launcher), "--bug", bug, "--image", args.image,
                   "--output", str(run_out)]
        started = time.monotonic()
        with (out / f"{bug}.launcher.log").open("wb") as log:
            completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        record = {"bug_id": bug, "launcher_exit_code": completed.returncode,
                  "seconds": time.monotonic() - started, "output": str(run_out.relative_to(ROOT))}
        launch_path = run_out / "launch.json"
        if launch_path.exists():
            launch = json.loads(launch_path.read_text(encoding="utf-8"))
            record.update(container_status=launch.get("status"),
                          container_exit_code=launch.get("exit_code"),
                          inputs_unchanged=launch.get("inputs_unchanged"))
        state["runs"].append(record)
        save(state_path, state)
    state["status"] = "finished"
    state["inputs_unchanged"] = inputs == {str(path.relative_to(ROOT)): digest(path) for path in (
        sample_path, launcher, ROOT / "execution_tools/official_defects4j_runner.py",
        ROOT / "CONFLICT_EXECUTION_AMENDMENT.md", Path(__file__))}
    save(state_path, state)
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
