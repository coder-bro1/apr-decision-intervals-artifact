"""Container-only official Defects4J feasibility runner; produces evidence, not labels."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time


def sha(data):
    return hashlib.sha256(data).hexdigest()


def place_method(files, anchor, patch):
    if not anchor.strip() or not patch.strip():
        raise ValueError("Empty method")
    anchor, patch = anchor.replace("\r\n", "\n"), patch.replace("\r\n", "\n")
    hits = []
    for path in files:
        raw = path.read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n")
        for match in re.finditer(re.escape(anchor), text):
            hits.append((path, raw, text, match.start()))
    if len(hits) != 1:
        raise ValueError(f"Expected one exact method occurrence, got {len(hits)}")
    path, raw, text, start = hits[0]
    replaced = text[:start] + patch + text[start + len(anchor):]
    return path, replaced.encode("utf-8"), {"original_sha256": sha(raw),
        "normalized_original_sha256": sha(text.encode()), "patched_sha256": sha(replaced.encode()),
        "start_offset_lf": start, "anchor_sha256": sha(anchor.encode()), "patch_sha256": sha(patch.encode())}


def _balanced_end(text, opening):
    depth = 0
    in_string = None
    escaped = False
    in_line_comment = False
    in_block_comment = False
    i = opening
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
        elif in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 1
        elif in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_string:
                in_string = None
        elif ch == "/" and nxt == "/":
            in_line_comment = True
            i += 1
        elif ch == "/" and nxt == "*":
            in_block_comment = True
            i += 1
        elif ch in ('"', "'"):
            in_string = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def _normalized_with_map(text):
    normalized = []
    positions = []
    for index, char in enumerate(text):
        if not char.isspace():
            normalized.append(char)
            positions.append(index)
    return "".join(normalized), positions


def place_d4c_method(files, patch):
    """Place D4C's complete method despite formatting drift in its archive."""
    patch = patch.replace("\r\n", "\n").replace("@Override", "")
    opening = patch.find("{")
    if opening < 0 or not patch.strip():
        raise ValueError("D4C patch is not a complete method")
    header = patch[:opening + 1]
    normalized_header = re.sub(r"\s+", "", header)
    matches = []
    for path in files:
        raw = path.read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n")
        normalized_text, positions = _normalized_with_map(text)
        start = 0
        while True:
            found = normalized_text.find(normalized_header, start)
            if found < 0:
                break
            original_start = positions[found]
            brace = positions[found + len(normalized_header) - 1]
            end = _balanced_end(text, brace)
            if end is None:
                raise ValueError("D4C method has unbalanced braces")
            matches.append((path, raw, text, original_start, end))
            start = found + 1
    if len(matches) != 1:
        raise ValueError(f"Expected one normalized D4C method occurrence, got {len(matches)}")
    path, raw, text, start, end = matches[0]
    replaced = text[:start] + patch.strip() + text[end:]
    return path, replaced.encode("utf-8"), {"original_sha256": sha(raw),
        "normalized_original_sha256": sha(text.encode()), "patched_sha256": sha(replaced.encode()),
        "start_offset_lf": start, "patch_sha256": sha(patch.encode()),
        "placement_mode": "d4c_normalized_signature_balanced_method"}


def run_command(argv, cwd, log, timeout):
    start = time.monotonic()
    with log.open("wb") as stream:
        proc = subprocess.Popen(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        try:
            code = proc.wait(timeout=max(0.01, timeout))
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait()
    text = log.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"^Failing tests: (\d+)\s*$", text, re.MULTILINE)
    return {"argv": argv, "exit_code": code, "timeout": timed_out,
            "seconds": time.monotonic() - start, "log_sha256": sha(log.read_bytes()),
            "failing_tests": int(matches[-1]) if code == 0 and not timed_out and matches else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--bug", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if os.name != "posix" or not Path("/.dockerenv").exists():
        raise RuntimeError("Run only inside the bounded research container")
    Path(os.environ.get("HOME", "/tmp/home")).mkdir(parents=True, exist_ok=True)
    if not re.fullmatch(r"[A-Za-z]+-[0-9]+", args.bug):
        raise ValueError("Invalid bug id")
    cases = [json.loads(p.read_text()) for p in sorted(args.cases.glob("*.json"))]
    cases = [r for r in cases if r["bug_id"] == args.bug]
    if not cases or len({r["candidate_id"] for r in cases}) != len(cases):
        raise ValueError("Missing or duplicate candidates")
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    project, number = args.bug.split("-")
    work = Path("/tmp") / ("official-pilot-" + args.bug)
    work.mkdir(exist_ok=False)
    result = {"bug_id": args.bug, "setup": [], "variants": [], "labels_changed": False,
              "status": "started", "runner_sha256": sha(Path(__file__).read_bytes())}
    def save():
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    save()
    try:
        setup_start = time.monotonic()
        for suffix in ("b", "f"):
            action = run_command(["defects4j", "checkout", "-p", project, "-v", number + suffix,
                                  "-w", str(work / suffix)], work, out / ("checkout_" + suffix + ".log"),
                                 1800 - (time.monotonic() - setup_start))
            result["setup"].append(action)
            save()
            if action["exit_code"] != 0:
                raise RuntimeError("Official checkout failed or timed out")
        metadata = {}
        for prop in ("dir.src.classes", "classes.modified", "tests.trigger"):
            destination = work / (prop + ".txt")
            action = run_command(["defects4j", "export", "-p", prop, "-o", str(destination)],
                                 work / "b", out / ("export_" + prop + ".log"),
                                 1800 - (time.monotonic() - setup_start))
            result["setup"].append(action)
            if action["exit_code"] != 0:
                raise RuntimeError("Metadata export failed")
            metadata[prop] = destination.read_text().strip()
        result["metadata"] = metadata
        triggers = metadata["tests.trigger"].splitlines()
        if not triggers:
            raise RuntimeError("No official triggers")
        for repeat in (1, 2):
            variants = [("fixed", None), ("buggy", None)] + [(r["candidate_id"], r) for r in cases]
            if repeat == 2:
                variants.reverse()
            for name, case in variants:
                key = f"{name}_r{repeat}"
                dst = work / key
                shutil.copytree(work / ("f" if name == "fixed" else "b"), dst, symlinks=True)
                vr = {"variant": name, "repeat": repeat, "commands": []}
                result["variants"].append(vr)
                if case:
                    files = [dst / metadata["dir.src.classes"] / (c.replace(".", "/") + ".java")
                             for c in metadata["classes.modified"].splitlines()]
                    for p in files:
                        p.resolve().relative_to(dst.resolve())
                    try:
                        if case.get("placement_mode") == "d4c_normalized_signature":
                            path, data, proof = place_d4c_method(files, case["patch"])
                        else:
                            path, data, proof = place_method(files, case["anchor"], case["patch"])
                    except (ValueError, OSError, UnicodeError) as exc:
                        vr["placement_error"] = str(exc)
                        save()
                        continue
                    vr["placement"] = {**proof, "source_path": str(path.relative_to(dst))}
                    (out / (key + "_original.java")).write_bytes(path.read_bytes())
                    path.write_bytes(data)
                    (out / (key + "_patched.java")).write_bytes(data)
                started = time.monotonic()
                commands = [["defects4j", "compile"]] + [["defects4j", "test", "-t", t] for t in triggers]
                for i, command in enumerate(commands):
                    left = 600 - (time.monotonic() - started)
                    if left <= 0:
                        vr["budget_exhausted"] = True
                        break
                    action = run_command(command, dst, out / f"{key}_{i}.log", left)
                    vr["commands"].append(action)
                    failure = dst / "failing_tests"
                    if command[1] == "test" and failure.exists():
                        shutil.copyfile(failure, out / f"{key}_{i}_failing_tests.txt")
                    save()
                    if action["exit_code"] != 0:
                        break
                vr["compile_and_test_seconds"] = time.monotonic() - started
                save()
        result["status"] = "execution_finished_requires_control_interpretation"
    except Exception as exc:
        result["status"] = "setup_or_runner_failure"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        save()


if __name__ == "__main__":
    main()
