"""E2 driver (ADDENDUM_V4_E2_PREVARANK.md): 50 label-independent input-order permutations of the 465 mixed PrevaRank
pools, each through the unchanged prepare -> run -> verify -> evaluate pipeline.

Resumable and crash-safe: a permutation counts as finished only when results/v4/prevarank/perm_XX.done exists (written
after evaluate succeeds), so a ledger cut off by a crash is never mistaken for a finished run. Any leftovers of an
unfinished permutation (run directory, partial evaluation files) are moved to perm_XX_aborted_<time>/ (never deleted)
and the permutation is redone. A failing permutation is recorded and the driver moves on to the next one; the exit code
is non-zero if any permutation failed, and a relaunch retries only the unfinished ones.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
OUT = ROOT / "results/v4/prevarank"
PROBE = ROOT / "results/v2/prevarank_llm/canonical_v2/runtime_probes/mixed_ctx_9f09_v1/runtime_compatibility_report.json"


def sh(args, log):
    with open(log, "a", encoding="utf-8") as f:
        f.write("\n$ " + " ".join(map(str, args)) + "\n")
        f.flush()
        r = subprocess.run([str(a) for a in args], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        raise RuntimeError(f"failed ({r.returncode}): {Path(str(args[2])).name}")


def move_with_retry(src, dst):
    for attempt in range(6):  # Docker Desktop's file share can hold handles briefly after a container exits
        try:
            src.rename(dst)
            return
        except OSError:
            time.sleep(10)
    src.rename(dst)


def set_aside(label):
    leftovers = [p for p in [OUT / label] + sorted(OUT.glob(f"{label}_evaluation*")) if p.exists()]
    if not leftovers:
        return
    aside = OUT / f"{label}_aborted_{int(time.time())}"
    aside.mkdir()
    for p in leftovers:
        move_with_retry(p, aside / p.name)
    print(f"{label}: moved leftovers of an unfinished attempt to {aside.name}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=int, default=1)
    ap.add_argument("--last", type=int, default=50)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    total = args.last - args.first + 1
    failed = []
    for k in range(args.first, args.last + 1):
        label = f"perm_{k:02d}"
        done = OUT / f"{label}.done"
        if done.exists():
            continue
        set_aside(label)
        log = OUT / f"{label}.log"
        t0 = time.time()
        try:
            sh([PY, "-B", "prepare_prevarank_llm_v2.py", "--output-root", OUT, "--run-label", label,
                "--pool-types", "mixed", "--input-order", "stable_hash", "--input-order-seed", f"e2-perm-{k}",
                "--runtime-probe-report", PROBE], log)
            manifest = OUT / label / "preparation_manifest.json"
            sh([PY, "-B", "run_prevarank_llm_v2.py", "--manifest", manifest, "--pool-type", "mixed"], log)
            sh([PY, "-B", "verify_prevarank_llm_run_v2.py", "--manifest", manifest, "--pool-type", "mixed"], log)
            sh([PY, "-B", "evaluate_prevarank_llm_v2.py", "--manifest", manifest, "--pool-types", "mixed",
                "--output", OUT / f"{label}_evaluation.json"], log)
        except Exception as exc:  # recorded; the next permutation still runs
            failed.append(k)
            print(f"{label}: FAILED ({exc}); see {log.name}. Continuing with the next permutation.", flush=True)
            continue
        done.write_text(json.dumps({"permutation": k, "seconds": round(time.time() - t0)}))
        n_done = sum(1 for j in range(args.first, args.last + 1) if (OUT / f"perm_{j:02d}.done").exists())
        print(f"E2 {n_done}/{total} ({100 * n_done / total:.0f}%)  {label} done in {round(time.time() - t0)} s", flush=True)
    if failed:
        print(f"E2: {len(failed)} permutation(s) failed: {failed}. Relaunch E2 to retry them.", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
