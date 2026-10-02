import argparse
import importlib.metadata
import json
import platform
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

import make_paper_tables


DEFAULT_REPORT = Path("results/v2/reproducibility_run.json")
TRACKED_PACKAGES = (
    "numpy",
    "scikit-learn",
    "scipy",
    "torch",
    "transformers",
    "tqdm",
)


def top_level_test_modules(root=Path(".")):
    return sorted(path.stem for path in root.glob("test_*.py") if path.is_file())


def environment_snapshot():
    packages = {}
    for package in TRACKED_PACKAGES:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None

    accelerator = {
        "torch_available": False,
        "cuda_available": False,
        "device_count": 0,
        "devices": [],
    }
    try:
        import torch

        accelerator["torch_available"] = True
        accelerator["cuda_available"] = torch.cuda.is_available()
        if accelerator["cuda_available"]:
            accelerator["device_count"] = torch.cuda.device_count()
            accelerator["devices"] = [
                torch.cuda.get_device_name(index)
                for index in range(torch.cuda.device_count())
            ]
    except ImportError:
        pass

    return {
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "packages": packages,
        "accelerator": accelerator,
    }


def run_top_level_tests(verbosity=1):
    modules = top_level_test_modules()
    loader = unittest.defaultTestLoader
    suite = loader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return {
        "modules": modules,
        "module_count": len(modules),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "successful": result.wasSuccessful(),
    }


def write_report(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build(report_path=DEFAULT_REPORT, skip_tests=False, test_verbosity=1):
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()

    generator_args = make_paper_tables.parse_args([])
    manifest = make_paper_tables.generate(generator_args)
    tests = (
        {
            "modules": [],
            "module_count": 0,
            "tests_run": 0,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "successful": None,
            "skipped_by_request": True,
        }
        if skip_tests
        else run_top_level_tests(verbosity=test_verbosity)
    )

    completed_at = datetime.now(timezone.utc)
    report = {
        "status": (
            "passed"
            if tests["successful"] is not False
            and all(manifest["validation_checks"].values())
            else "failed"
        ),
        "started_at_utc": started_at.isoformat(),
        "completed_at_utc": completed_at.isoformat(),
        "elapsed_seconds": time.perf_counter() - started,
        "command": "python build_paper_artifacts.py",
        "paper_artifact_version": manifest["artifact_version"],
        "paper_manifest": str(generator_args.manifest),
        "paper_manifest_sha256": make_paper_tables.sha256(
            generator_args.manifest
        ),
        "generated_table_count": len(manifest["table_ids"]),
        "generated_claim_count": len(manifest["claim_ids"]),
        "integrity_check_count": len(manifest["validation_checks"]),
        "integrity_checks_all_pass": all(
            manifest["validation_checks"].values()
        ),
        "tests": tests,
        "environment": environment_snapshot(),
    }
    write_report(report_path, report)

    if report["status"] != "passed":
        raise SystemExit(1)
    return report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate paper artifacts, validate all pinned evidence, run "
            "top-level research tests, and record the environment."
        )
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--test-verbosity", type=int, default=1)
    return parser.parse_args(argv)


def main():
    args = parse_args()
    report = build(
        report_path=args.report,
        skip_tests=args.skip_tests,
        test_verbosity=args.test_verbosity,
    )
    print(
        "Paper artifact build passed: "
        f"{report['generated_table_count']} tables, "
        f"{report['generated_claim_count']} claims, "
        f"{report['integrity_check_count']} integrity checks, "
        f"{report['tests']['tests_run']} tests."
    )


if __name__ == "__main__":
    main()
