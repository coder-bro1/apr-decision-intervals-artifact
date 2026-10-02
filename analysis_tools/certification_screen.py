"""Reproduce the exploratory published-claim certification screen.

The freeze phase writes claim manifests and their hashes. The score phase
refuses to proceed if either manifest has changed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "certification_screen_v1"
REPAIRLLAMA = ROOT / "repairllama" / "results" / "2_merged"
RL_BENCHMARKS = ROOT / "repairllama" / "results" / "benchmarks"
RB_REPO = ROOT / "external_artifacts" / "repairbench"
RB_FRAMEWORK = ROOT / "external_artifacts" / "repairbench-framework"
RB_DATA = ROOT / "llm_apr_dataset" / "external" / "repairbench_gitbugjava_2025_v1"
RB_COMMIT = "e43cb673e99cf48245148512ad84c4a2b593db30"
RB_FRAMEWORK_COMMIT = "de1d8464232176f1d4f56ead37e1c935c1c31d80"
TOLERANCE_BUGS = 2

# Public RepairBench paper Table 1 (results frozen March 22, 2026),
# GitBug-Java Plausible@1 percentages rounded to one decimal.
REPAIRBENCH_PUBLISHED_GITBUG_VALUES = {
    "claude-3-5-sonnet-20240620": 26.1,
    "gpt-4o-2024-08-06": 18.8,
    "gemini-1.5-pro-001": 16.7,
    "llama-3.1-405b-instruct": 16.7,
    "deepseek-v2.5": 17.6,
    "qwen-2.5-72b-instruct": 17.3,
    "mistral-large-2407": 15.2,
}

BENCHMARKS = ("defects4j", "humanevaljava", "gitbugjava")
METRICS = ("plausible", "exact", "ast", "semantic")

# Counts transcribed from RepairLLaMA arXiv v6 Tables II-IV. Each tuple is
# (plausible, exact, AST, semantic) for Defects4J, HumanEval-Java, GitBug-Java.
PUBLISHED = {
    "baseline_ir3": {
        "config": "zero-shot-cloze_codellama",
        "display": "CodeLLaMA-7B, IR3xOR2, no fine-tuning",
        "table": "II",
        "defects4j": (131, 52, 70, 83),
        "humanevaljava": (107, 71, 81, 103),
        "gitbugjava": (17, 8, 9, 12),
    },
    "baseline_ir4": {
        "config": "zero-shot-cloze_codellama-ir4",
        "display": "CodeLLaMA-7B, IR4xOR2, no fine-tuning",
        "table": "II",
        "defects4j": (107, 50, 60, 69),
        "humanevaljava": (95, 65, 72, 91),
        "gitbugjava": (19, 11, 12, 13),
    },
    "ir1_or1": {
        "config": "repairllama_ir1_or1",
        "display": "IR1xOR1",
        "table": "II",
        "defects4j": (79, 29, 31, 45),
        "humanevaljava": (78, 52, 54, 72),
        "gitbugjava": (10, 4, 4, 4),
    },
    "ir1_or3": {
        "config": "repairllama_ir1_or3",
        "display": "IR1xOR3",
        "table": "II",
        "defects4j": (41, 15, 17, 24),
        "humanevaljava": (39, 21, 21, 37),
        "gitbugjava": (6, 1, 1, 1),
    },
    "ir1_or4": {
        "config": "repairllama_ir1_or4",
        "display": "IR1xOR4",
        "table": "II",
        "defects4j": (12, 2, 2, 3),
        "humanevaljava": (5, 2, 2, 4),
        "gitbugjava": (1, 1, 1, 1),
    },
    "ir2_or2": {
        "config": "repairllama_ir2_or2",
        "display": "IR2xOR2",
        "table": "II",
        "defects4j": (198, 121, 122, 139),
        "humanevaljava": (118, 69, 77, 108),
        "gitbugjava": (23, 16, 17, 19),
    },
    "ir3_or2": {
        "config": "repairllama_ir3_or2",
        "display": "IR3xOR2, fine-tuned",
        "table": "II",
        "defects4j": (153, 83, 86, 102),
        "humanevaljava": (103, 63, 68, 99),
        "gitbugjava": (21, 12, 12, 13),
    },
    "repairllama": {
        "config": "repairllama_ir4_or2",
        "display": "RepairLLaMA (IR4xOR2)",
        "table": "II, III, IV",
        "defects4j": (195, 124, 125, 144),
        "humanevaljava": (118, 75, 82, 109),
        "gitbugjava": (25, 15, 16, 20),
    },
    "codellama_fft": {
        "config": "zero-shot-cloze_repairllama-fft",
        "display": "CodeLLaMA-7B, full fine-tuning",
        "table": "III",
        "defects4j": (146, 66, 84, 98),
        "humanevaljava": (109, 74, 83, 100),
        "gitbugjava": (21, 11, 11, 13),
    },
    "deepseek_base": {
        "config": "deepseek_base",
        "display": "DeepSeek-Coder-6.7B, base",
        "table": "III",
        "defects4j": (147, 84, 88, 104),
        "humanevaljava": (113, 68, 83, 110),
        "gitbugjava": (21, 11, 11, 13),
    },
    "deepseek_fft": {
        "config": "deepseek_fft",
        "display": "DeepSeek-Coder-6.7B, full fine-tuning",
        "table": "III",
        "defects4j": (185, 116, 123, 138),
        "humanevaljava": (129, 96, 101, 119),
        "gitbugjava": (26, 15, 15, 19),
    },
    "deepseek_lora": {
        "config": "deepseek_lora",
        "display": "DeepSeek-Coder-6.7B, LoRA",
        "table": "III",
        "defects4j": (181, 110, 113, 128),
        "humanevaljava": (134, 99, 107, 124),
        "gitbugjava": (19, 12, 12, 13),
    },
    "gpt35": {
        "config": "gpt35_gpt-zero-shot",
        "display": "GPT-3.5",
        "table": "IV",
        "defects4j": (71, 23, 33, 45),
        "humanevaljava": (107, 50, 63, 97),
        "gitbugjava": (9, 7, 7, 8),
    },
    "gpt4": {
        "config": "gpt4_gpt-zero-shot",
        "display": "GPT-4",
        "table": "IV",
        "defects4j": (119, 47, 60, 64),
        "humanevaljava": (124, 72, 74, 116),
        "gitbugjava": (14, 6, 7, 10),
    },
}

RQ1_KEYS = (
    "baseline_ir3", "baseline_ir4", "ir1_or1", "ir1_or3", "ir1_or4",
    "ir2_or2", "ir3_or2", "repairllama",
)
RQ2_FAMILIES = (("baseline_ir3", "codellama_fft", "repairllama"),
                ("deepseek_base", "deepseek_fft", "deepseek_lora"))
RQ3_KEYS = ("gpt35", "gpt4", "repairllama")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def sf_bug_ids(benchmark: str) -> set[str]:
    filename = {
        "defects4j": "defects4j_sf.txt",
        "humanevaljava": "humanevaljava_sf.txt",
        "gitbugjava": "gitbugjava_sf.txt",
    }[benchmark]
    return set((RL_BENCHMARKS / filename).read_text(encoding="utf-8").split())


def repairllama_claim_manifest() -> list[dict]:
    by_pair: dict[tuple[str, str, str], dict] = {}

    def add_pair(benchmark: str, left: str, right: str, location: str) -> None:
        a, b = PUBLISHED[left], PUBLISHED[right]
        ca, cb = a[benchmark][3], b[benchmark][3]
        if ca == cb:
            high, low = left, right
        elif ca > cb:
            high, low = left, right
        else:
            high, low = right, left
        key = (benchmark, high, low)
        row = by_pair.setdefault(key, {
            "claim_id": f"RL-{benchmark}-{high}-vs-{low}",
            "campaign": "RepairLLaMA",
            "benchmark": benchmark,
            "metric": "semantic-match bugs (reported bug-level count)",
            "config_a": PUBLISHED[high]["config"],
            "config_a_display": PUBLISHED[high]["display"],
            "config_b": PUBLISHED[low]["config"],
            "config_b_display": PUBLISHED[low]["display"],
            "reported_a": ca,
            "reported_b": cb,
            "reported_margin_bugs": ca - cb,
            "claimed_direction": "a>b" if ca != cb else "tie",
            "locations": "",
            "headline": "no",
            "scope_note": "",
        })
        locations = set(filter(None, row["locations"].split(";")))
        locations.add(location)
        row["locations"] = ";".join(sorted(locations))

    for benchmark in BENCHMARKS:
        for left, right in itertools.combinations(RQ1_KEYS, 2):
            add_pair(benchmark, left, right, "Table II/RQ1 pairwise representation comparison")
        for family in RQ2_FAMILIES:
            for left, right in itertools.combinations(family, 2):
                add_pair(benchmark, left, right, "Table III/RQ2 within-base-model comparison")
        for left, right in itertools.combinations(RQ3_KEYS, 2):
            add_pair(benchmark, left, right, "Table IV/RQ3 ChatGPT baseline comparison")

        other = [key for key in PUBLISHED if key != "repairllama"]
        best = max(other, key=lambda key: PUBLISHED[key][benchmark][3])
        row = {
            "claim_id": f"RL-HEADLINE-{benchmark}-repairllama-vs-best-reported",
            "campaign": "RepairLLaMA",
            "benchmark": benchmark,
            "metric": "semantic-match bugs (reported bug-level count)",
            "config_a": PUBLISHED["repairllama"]["config"],
            "config_a_display": "RepairLLaMA (headline claim)",
            "config_b": PUBLISHED[best]["config"],
            "config_b_display": f"Highest-count non-RepairLLaMA row: {PUBLISHED[best]['display']}",
            "reported_a": PUBLISHED["repairllama"][benchmark][3],
            "reported_b": PUBLISHED[best][benchmark][3],
            "reported_margin_bugs": PUBLISHED["repairllama"][benchmark][3] - PUBLISHED[best][benchmark][3],
            "claimed_direction": "a>b",
            "locations": "Abstract;Conclusion;Tables II-IV",
            "headline": "yes",
            "scope_note": "Paper-level 'outperforming all baselines' claim operationalized against the strongest reported non-RepairLLaMA row.",
        }
        by_pair[(benchmark, f"HEADLINE:{best}", "repairllama")] = row

    rows = list(by_pair.values())
    rows.append({
        "claim_id": "RL-EXT-RAPGEN-D4J",
        "campaign": "RepairLLaMA",
        "benchmark": "defects4j",
        "metric": "semantic-match bugs (external aggregate comparison)",
        "config_a": PUBLISHED["repairllama"]["config"],
        "config_a_display": "RepairLLaMA (IR4xOR2)",
        "config_b": "RAP-Gen",
        "config_b_display": "RAP-Gen, authors' reported aggregate",
        "reported_a": 144,
        "reported_b": 125,
        "reported_margin_bugs": 19,
        "claimed_direction": "a>b",
        "locations": "Results prose (not a main comparison table)",
        "headline": "no",
        "scope_note": "No per-bug RAP-Gen vector in the local inputs; retain as unreproducible, do not score as a paired claim.",
    })
    return sorted(rows, key=lambda row: row["claim_id"])


def git_output(*args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(RB_REPO), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def repairbench_model_registry() -> list[dict]:
    payload = json.loads(git_output("cat-file", "blob", f"{RB_COMMIT}:models.json"))
    return [
        {"model_id": item[0], "interface": item[1], "organization": item[2]}
        for item in payload["models"]
    ]


def repairbench_gitbug_source_path(model_id: str) -> str:
    directory = f"results/{model_id}/gitbugjava"
    names = git_output("ls-tree", "--name-only", f"{RB_COMMIT}:{directory}").decode().splitlines()
    matches = [name for name in names if name.startswith("evaluation_gitbugjava_") and name.endswith(".jsonl")]
    if len(matches) != 1:
        raise ValueError(f"Expected one GitBug evaluation file for {model_id}, found {matches}")
    return f"{directory}/{matches[0]}"


def repairbench_gitbug_metrics(keep_occurrences: bool = False) -> tuple[list[dict], dict]:
    models = repairbench_model_registry()
    metrics = []
    source_hashes = {}
    for model in models:
        model_id = model["model_id"]
        source_path = repairbench_gitbug_source_path(model_id)
        payload = git_output("cat-file", "blob", f"{RB_COMMIT}:{source_path}")
        source_hashes[source_path] = {
            "git_blob_oid": git_output("rev-parse", f"{RB_COMMIT}:{source_path}").decode().strip(),
            "sha256": sha256_bytes(payload),
        }
        n = successes = 0
        occurrence_rows = []
        for raw in payload.splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            if not row.get("generation"):
                continue
            evaluations = row.get("evaluation") or []
            if not isinstance(evaluations, list):
                raise ValueError(f"Non-list evaluation in {source_path}, bug={row.get('identifier')}")
            bug = row.get("identifier")
            n += len(evaluations)
            for index, evaluation in enumerate(evaluations):
                if not isinstance(evaluation, dict):
                    if keep_occurrences:
                        occurrence_rows.append((model_id, bug, index, "", "incorrect", False))
                    continue
                test_pass = evaluation.get("test") is True
                successes += int(test_pass)
                patch = (evaluation.get("generation") or "").strip()
                if not keep_occurrences:
                    continue
                if not patch:
                    label = "incorrect"
                elif ((evaluation.get("exact_match") is True or evaluation.get("ast_match") is True)
                      and evaluation.get("test") is False):
                    label = "conflict"
                elif evaluation.get("exact_match") is True or evaluation.get("ast_match") is True:
                    label = "correct"
                elif evaluation.get("test") is False:
                    label = "incorrect"
                elif evaluation.get("test") is True:
                    label = "unknown"
                else:
                    label = "incorrect"
                occurrence_rows.append((model_id, bug, index, patch, label, test_pass))
        if n == 0:
            raise ValueError(f"No eligible generated candidate slots for {model_id}")
        metrics.append({
            "model_id": model_id,
            "organization": model["organization"],
            "n_slots": n,
            "plausible_slots": successes,
            "plausible_at_1": successes / n,
            "plausible_at_1_pct": 100.0 * successes / n,
            "source_path": source_path,
            "occurrences": occurrence_rows if keep_occurrences else None,
        })
    return metrics, source_hashes


def repairbench_claim_manifest(metrics: list[dict]) -> list[dict]:
    ranked = sorted(metrics, key=lambda row: (-row["plausible_at_1"], row["model_id"]))
    claims: dict[tuple[str, str], dict] = {}

    def add(a: dict, b: dict, relation: str) -> None:
        tied = a["plausible_at_1"] == b["plausible_at_1"]
        high, low = (a, b) if a["plausible_at_1"] >= b["plausible_at_1"] else (b, a)
        key = (high["model_id"], low["model_id"])
        row = claims.setdefault(key, {
            "claim_id": f"RB-GITBUG-{high['model_id']}-vs-{low['model_id']}",
            "campaign": "RepairBench/GitBug-Java subscore",
            "benchmark": "gitbugjava",
            "metric": "published Plausible@1 (pass@1 from 10 sampled outputs)",
            "config_a": high["model_id"],
            "config_b": low["model_id"],
            "reported_a": high["plausible_at_1"],
            "reported_b": low["plausible_at_1"],
            "reported_margin_pp": high["plausible_at_1_pct"] - low["plausible_at_1_pct"],
            "rank_a": ranked.index(high) + 1,
            "rank_b": ranked.index(low) + 1,
            "published_tie": tied,
            "relation": "",
            "scope_note": "Derived GitBug-Java subscore ranking; ties are not directional claims. The official 2025 website sorted its overall total across Defects4J and GitBug-Java.",
        })
        relation_set = set(filter(None, row["relation"].split(";")))
        relation_set.add(relation)
        row["relation"] = ";".join(sorted(relation_set))

    for left, right in zip(ranked, ranked[1:]):
        add(left, right, "adjacent")
    for other in ranked[1:]:
        add(ranked[0], other, "top_vs_all")
    return sorted(claims.values(), key=lambda row: (row["rank_a"], row["rank_b"]))


def external_availability_rows() -> list[dict]:
    return [
        {
            "paper_or_system": "RepairLLaMA",
            "authors_year": "Silva, Fang, Monperrus (TSE 2025)",
            "benchmark_version_bug_set": "Defects4J v2, 488 single-function; HumanEval-Java 162; GitBug-Java 90",
            "per_bug_correct_list": "Yes: released generation/evaluation outputs; local 2_merged has 14 configs",
            "patch_text": "Yes",
            "correctness_process": "Exact and AST reference matches; test plausibility; two independent expert reviews of plausible non-reference-match patches, third-author adjudication of disagreement",
            "artifact_url": "https://github.com/ASSERT-KTH/repairllama",
            "availability_assessment": "High; labels/counts still require reconstruction and source-version checks",
        },
        {
            "paper_or_system": "RepairBench",
            "authors_year": "Silva, Monperrus (LLM4Code 2025)",
            "benchmark_version_bug_set": "Defects4J v2 single-function; GitBug-Java 90; pinned snapshot has 35 model configurations",
            "per_bug_correct_list": "Yes: per-model raw evaluations and exact/AST/test flags are released",
            "patch_text": "Yes",
            "correctness_process": "Plausible means all tests pass; AST/exact compare to reference; test-passing nonmatches are not semantic proof",
            "artifact_url": "https://github.com/ASSERT-KTH/repairbench",
            "availability_assessment": "High; exact pinned GitBug blobs available locally; some non-GitBug objects absent from local partial clone",
        },
        {
            "paper_or_system": "RepairAgent",
            "authors_year": "Bouzenia, Devanbu, Pradel (2024 paper; artifact 2025)",
            "benchmark_version_bug_set": "Defects4J; paper reports 164 repairs; verify exact D4J release/single-function scope per claim",
            "per_bug_correct_list": "Yes: repository exposes final fixed-bug list",
            "patch_text": "Yes: implementation details and root/derived patches",
            "correctness_process": "Execution-validated repairs; use paper/artifact protocol to distinguish plausible from semantic correctness",
            "artifact_url": "https://github.com/sola-st/RepairAgent",
            "availability_assessment": "High for a follow-up audit; middleware exceptions noted in artifact, so check denominator",
        },
        {
            "paper_or_system": "ThinkRepair",
            "authors_year": "Yin et al. (ISSTA 2024)",
            "benchmark_version_bug_set": "Defects4J v1.2 and v2.0; paper reports version-specific totals",
            "per_bug_correct_list": "Yes: repository includes Results/correct_patches",
            "patch_text": "Correct patch text is released; complete rejected-candidate stream not confirmed",
            "correctness_process": "Correct-patch list and test-based APR outcomes; audit paper for any manual semantic adjudication before reuse",
            "artifact_url": "https://github.com/vinci-grape/ThinkRepair",
            "availability_assessment": "Good for reported successes, weaker for full candidate-level certification",
        },
        {
            "paper_or_system": "D4C",
            "authors_year": "Xu, Fu, Tan, He (ICSE 2025)",
            "benchmark_version_bug_set": "Defects4J; artifact documents later v3.0 deprecated-bug handling",
            "per_bug_correct_list": "Yes: archived correct fixed-bug list and evaluation CSVs",
            "patch_text": "Yes: prediction CSVs and archived results",
            "correctness_process": "Test execution plus separately supplied correct-fix list; exact manual/reference adjudication rule should be verified before cross-paper pooling",
            "artifact_url": "https://github.com/CUHK-Shenzhen-SE/D4C",
            "availability_assessment": "High; version migration/deprecated bugs are explicit provenance risks",
        },
        {
            "paper_or_system": "SRepair / Practical Function-Level APR",
            "authors_year": "Xiang et al. (2024 preprint; TOSEM 2026 article)",
            "benchmark_version_bug_set": "Defects4J 1.2 and 2.0; function-level subset, plus QuixBugs",
            "per_bug_correct_list": "Repository provides dataset and generation/validation scripts; precomputed full per-bug final list not confirmed in inspected README",
            "patch_text": "Generated patch output is supported by the released workflow; full archived corpus not confirmed",
            "correctness_process": "Plausible via trigger and relevant class tests; paper distinguishes semantically correct from merely plausible",
            "artifact_url": "https://github.com/GhabiX/SRepair",
            "availability_assessment": "Potentially auditable after artifact inspection; not yet ready as frozen released labels",
        },
        {
            "paper_or_system": "ChatRepair",
            "authors_year": "Xia, Zhang (2023 preprint; ISSTA 2024 publication)",
            "benchmark_version_bug_set": "Defects4J 1.2, 337 bugs in headline comparison; QuixBugs",
            "per_bug_correct_list": "No original author artifact verified in this desk check; a third-party implementation exists",
            "patch_text": "Paper-specific candidate stream not verified as released",
            "correctness_process": "Test plausibility and subsequent correctness assessment are discussed in the paper; per-bug adjudication records not verified",
            "artifact_url": "https://arxiv.org/abs/2304.00385 ; third-party implementation: https://github.com/Aric3/an-implementation-of-chatrepair",
            "availability_assessment": "Low for a faithful claim-level replication without locating the original paper data",
        },
    ]


def freeze() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    claims_rl_path = OUT / "claims_repairllama.csv"
    claims_rb_path = OUT / "claims_repairbench.csv"
    hashes_path = OUT / "frozen_manifest_hashes.json"
    if any(path.exists() for path in (claims_rl_path, claims_rb_path, hashes_path)):
        raise FileExistsError(f"Freeze outputs already exist in {OUT}; refusing to overwrite.")

    claims_rl = repairllama_claim_manifest()
    rb_metrics, rb_hashes = repairbench_gitbug_metrics()
    claims_rb = repairbench_claim_manifest(rb_metrics)
    write_csv(claims_rl_path, claims_rl)
    write_csv(claims_rb_path, claims_rb)
    hashes = {
        "protocol": "certification-screen-v1-frozen-claims",
        "claim_sources": {
            "RepairLLaMA": "Silva et al., arXiv:2312.15698v6, Tables II-IV and abstract/conclusion",
            "RepairBench": f"Pinned repository {RB_COMMIT}; GitBug-Java per-benchmark Plausible@1 ordering derived from archived slots",
        },
        "repairllama_manifest_sha256": sha256_file(claims_rl_path),
        "repairbench_manifest_sha256": sha256_file(claims_rb_path),
        "repairbench_gitbug_source_hashes": rb_hashes,
        "repairbench_claim_count": len(claims_rb),
        "repairllama_claim_count": len(claims_rl),
        "frozen_before_correctness_status_calculation": True,
        "exploratory_note": "Some descriptive source inventory was inspected during feasibility checks; this is a frozen analysis manifest, not a preregistration.",
    }
    hashes_path.write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    write_csv(OUT / "external_availability.csv", external_availability_rows())
    print(json.dumps({
        "frozen": True,
        "repairllama_claims": len(claims_rl),
        "repairbench_claims": len(claims_rb),
        "repairllama_sha256": hashes["repairllama_manifest_sha256"],
        "repairbench_sha256": hashes["repairbench_manifest_sha256"],
        "repairbench_models": len(rb_metrics),
        "top_gitbug_plausible_at_1": [
            {"model": row["model_id"], "score_pct": round(row["plausible_at_1_pct"], 3)}
            for row in sorted(rb_metrics, key=lambda item: -item["plausible_at_1"])[:5]
        ],
    }, indent=2))


def evidence_flags(evaluation: dict) -> dict:
    exact_ast = evaluation.get("exact_match") is True or evaluation.get("ast_match") is True
    compile_value, test_value = evaluation.get("compile"), evaluation.get("test")
    objective_negative = compile_value is False or test_value is False
    sem = evaluation.get("semantical_match")
    human_positive = sem is True and test_value is True and not exact_ast
    human_negative = sem is False and test_value is True and not exact_ast
    disagreement = sem == "Disagree"
    invalid_conflict = exact_ast and objective_negative
    invalid_conflict |= sem is True and test_value is False
    return {
        "objective_positive": exact_ast,
        "objective_negative": objective_negative and not exact_ast,
        "objective_conflict": exact_ast and objective_negative,
        "human_positive": human_positive,
        "human_negative": human_negative,
        "disagreement": disagreement,
        "conflict": invalid_conflict,
    }


def candidate_label(evidence: dict, view: str) -> int | None:
    objective_positive = evidence["objective_positive"]
    objective_negative = evidence["objective_negative"]
    if evidence.get("objective_conflict", False) or (objective_positive and objective_negative):
        return None
    if view == "S1_objective_only":
        if objective_positive:
            return 1
        if objective_negative:
            return 0
        return None
    if evidence["conflict"]:
        return None
    if evidence["human_positive"] and evidence["human_negative"]:
        return None
    if objective_positive and evidence["human_negative"]:
        return None
    if objective_negative and evidence["human_positive"]:
        return None
    if objective_positive:
        return 1
    if objective_negative:
        return 0
    if evidence["human_positive"]:
        return 1
    if evidence["human_negative"]:
        return 0
    return None


def load_repairllama() -> tuple[dict, dict, list[dict], dict]:
    evidence_by_benchmark = {benchmark: defaultdict(Counter) for benchmark in BENCHMARKS}
    model_bug_candidates = defaultdict(lambda: defaultdict(set))
    metrics = []
    input_hashes = {}
    bug_sets = {benchmark: sf_bug_ids(benchmark) for benchmark in BENCHMARKS}

    for benchmark in BENCHMARKS:
        list_path = RL_BENCHMARKS / f"{benchmark}_sf.txt"
        input_hashes[str(list_path.relative_to(ROOT))] = sha256_file(list_path)

    used_configs = sorted({row["config"] for row in PUBLISHED.values()})
    for benchmark in BENCHMARKS:
        bugs = bug_sets[benchmark]
        for config in used_configs:
            path = REPAIRLLAMA / f"evaluation_{benchmark}_{config}_merged.jsonl"
            if not path.exists():
                raise FileNotFoundError(path)
            input_hashes[str(path.relative_to(ROOT))] = sha256_file(path)
            positives = {metric: set() for metric in METRICS}
            found_rows = set()
            for row in read_jsonl(path):
                bug = row.get("identifier")
                if bug not in bugs:
                    continue
                found_rows.add(bug)
                evaluations = row.get("evaluation") or []
                generations = row.get("generation") or []
                if not isinstance(evaluations, list):
                    continue
                for index, evaluation in enumerate(evaluations):
                    if not isinstance(evaluation, dict):
                        continue
                    patch = (evaluation.get("generation") or "").strip()
                    if (not patch and isinstance(generations, list)
                            and index < len(generations)
                            and isinstance(generations[index], str)):
                        patch = generations[index].strip()
                    if not patch:
                        continue
                    key = (bug, patch)
                    model_bug_candidates[(benchmark, config)][bug].add(key)
                    evidence_by_benchmark[benchmark][key].update(evidence_flags(evaluation))
                    if evaluation.get("test") is True:
                        positives["plausible"].add(bug)
                    if evaluation.get("exact_match") is True:
                        positives["exact"].add(bug)
                    if evaluation.get("ast_match") is True:
                        positives["ast"].add(bug)
                    if (evaluation.get("exact_match") is True
                            or evaluation.get("ast_match") is True
                            or evaluation.get("semantical_match") is True):
                        positives["semantic"].add(bug)
            config_key = next(key for key, item in PUBLISHED.items() if item["config"] == config)
            reported = PUBLISHED[config_key][benchmark]
            for metric_index, metric in enumerate(METRICS):
                observed = len(positives[metric])
                metrics.append({
                    "benchmark": benchmark,
                    "config": config,
                    "display": PUBLISHED[config_key]["display"],
                    "metric": metric,
                    "reported_bugs": reported[metric_index],
                    "reproduced_bugs": observed,
                    "difference_bugs": observed - reported[metric_index],
                    "within_plus_minus_2": abs(observed - reported[metric_index]) <= TOLERANCE_BUGS,
                    "single_function_bug_count": len(bugs),
                    "bugs_with_any_released_row": len(found_rows),
                })
    return evidence_by_benchmark, model_bug_candidates, metrics, input_hashes


def bug_diff_bounds(a_ids: set, b_ids: set, labels: dict) -> tuple[int, int]:
    a_positive = any(labels.get(candidate) == 1 for candidate in a_ids)
    b_positive = any(labels.get(candidate) == 1 for candidate in b_ids)
    a_unknown = {candidate for candidate in a_ids if labels.get(candidate) is None}
    b_unknown = {candidate for candidate in b_ids if labels.get(candidate) is None}

    plus_possible = False
    if not b_positive:
        if a_positive:
            plus_possible = True
        else:
            plus_possible = bool(a_unknown - b_unknown)

    minus_possible = False
    if not a_positive:
        if b_positive:
            minus_possible = True
        else:
            minus_possible = bool(b_unknown - a_unknown)

    equal_possible = ((not a_positive and not b_positive)
                      or ((a_positive or a_unknown) and (b_positive or b_unknown)))
    lower = -1 if minus_possible else 0 if equal_possible else 1
    upper = 1 if plus_possible else 0 if equal_possible else -1
    return lower, upper


def withdrawal_cost_for_bug(a_ids: set, b_ids: set, labels: dict,
                            withdrawable: set) -> dict[int, int]:
    """Exact local lower-bound outcomes via a 16-state flag DP."""
    actions = sorted((a_ids | b_ids) & withdrawable, key=repr)
    # Flags: positives in A/B, any unknowns in A/B, and exclusive unknowns.
    base = [False, False, False, False, False, False]
    for candidate in (a_ids | b_ids) - withdrawable:
        in_a, in_b = candidate in a_ids, candidate in b_ids
        label = labels.get(candidate)
        if label == 1:
            base[0] |= in_a
            base[1] |= in_b
        elif label is None:
            base[2] |= in_a
            base[3] |= in_b
            base[4] |= in_a and not in_b
            base[5] |= in_b and not in_a

    states = {tuple(base): 0}
    for candidate in actions:
        in_a, in_b = candidate in a_ids, candidate in b_ids
        label = labels[candidate]
        next_states = {}
        for flags, cost in states.items():
            kept = list(flags)
            if label == 1:
                kept[0] |= in_a
                kept[1] |= in_b
            kept_key = tuple(kept)
            next_states[kept_key] = min(next_states.get(kept_key, 10**9), cost)

            withdrawn = list(flags)
            withdrawn[2] |= in_a
            withdrawn[3] |= in_b
            withdrawn[4] |= in_a and not in_b
            withdrawn[5] |= in_b and not in_a
            withdrawn_key = tuple(withdrawn)
            next_states[withdrawn_key] = min(next_states.get(withdrawn_key, 10**9), cost + 1)
        states = next_states

    best_cost_by_lower = {}
    for (a_positive, b_positive, a_unknown, b_unknown,
         a_unknown_only, b_unknown_only), cost in states.items():
        minus_possible = not a_positive and (b_positive or b_unknown_only)
        plus_possible = not b_positive and (a_positive or a_unknown_only)
        equal_possible = (not a_positive and not b_positive) or (
            (a_positive or a_unknown) and (b_positive or b_unknown))
        lower = -1 if minus_possible else 0 if equal_possible else 1
        best_cost_by_lower[lower] = min(best_cost_by_lower.get(lower, 10**9), cost)
    return best_cost_by_lower


def combine_withdrawal_options(dp: dict[int, int], local_options: dict[int, int]) -> dict[int, int]:
    next_dp = {}
    for local_lower, local_cost in local_options.items():
        for total_lower, prior_cost in dp.items():
            combined_lower = total_lower + local_lower
            next_dp[combined_lower] = min(
                next_dp.get(combined_lower, 10**9), prior_cost + local_cost)
    return next_dp


def compare_bug_level(a_config: str, b_config: str, benchmark: str,
                      candidate_map: dict, labels: dict,
                      withdrawable: set | None = None) -> dict:
    bugs = sf_bug_ids(benchmark)
    lower = upper = 0
    changed_bugs = 0
    dp = {0: 0}
    for bug in bugs:
        a_ids = candidate_map[(benchmark, a_config)].get(bug, set())
        b_ids = candidate_map[(benchmark, b_config)].get(bug, set())
        lo, hi = bug_diff_bounds(a_ids, b_ids, labels)
        lower += lo
        upper += hi
        if lo != hi:
            changed_bugs += 1
        if withdrawable is None:
            continue
        best_cost_by_lower = withdrawal_cost_for_bug(a_ids, b_ids, labels, withdrawable)
        dp = combine_withdrawal_options(dp, best_cost_by_lower)

    withdrawal = "not_computed"
    if withdrawable is not None:
        eligible = [cost for total_lower, cost in dp.items() if total_lower <= 0]
        withdrawal = min(eligible) if eligible else "not_withdrawable_by_human_labels"
    return {
        "lower_bugs": lower,
        "upper_bugs": upper,
        "unknown_affected_bug_count": changed_bugs,
        "status": "supported" if lower > 0 else "reversed" if upper < 0 else "contested",
        "withdrawal_robustness": withdrawal,
    }


def repairllama_status(claims: list[dict], evidence_by_benchmark: dict,
                       candidate_map: dict, reproduction: list[dict]) -> list[dict]:
    rows = []
    reproduced = {(row["benchmark"], row["config"], row["metric"]): row["within_plus_minus_2"]
                  for row in reproduction}
    label_maps = {}
    human_only_maps = {}
    for benchmark in BENCHMARKS:
        evidence = evidence_by_benchmark[benchmark]
        s0, s1 = {}, {}
        human_only = set()
        for candidate, counts in evidence.items():
            ev = {field: bool(counts[field]) for field in (
                "objective_positive", "objective_negative", "human_positive",
                "human_negative", "disagreement", "conflict", "objective_conflict")}
            s0[candidate] = candidate_label(ev, "S0_all_released_labels")
            s1[candidate] = candidate_label(ev, "S1_objective_only")
            if (s0[candidate] is not None
                    and not ev["objective_positive"] and not ev["objective_negative"]
                    and (ev["human_positive"] ^ ev["human_negative"])):
                human_only.add(candidate)
        label_maps[(benchmark, "S0")] = s0
        label_maps[(benchmark, "S1")] = s1
        human_only_maps[benchmark] = human_only

    for claim in claims:
        if claim["config_b"] == "RAP-Gen":
            rows.append({
                **claim,
                "S0_lower_bugs": "", "S0_upper_bugs": "", "S0_status": "not_evaluable_no_per_bug_data",
                "S1_lower_bugs": "", "S1_upper_bugs": "", "S1_status": "not_evaluable_no_per_bug_data",
                "data_reproducibility": "external comparator lacks local per-bug output",
                "withdrawal_robustness": "not_computed",
            })
            continue
        bench = claim["benchmark"]
        a, b = claim["config_a"], claim["config_b"]
        labels_s0 = label_maps[(bench, "S0")]
        base_s0 = compare_bug_level(a, b, bench, candidate_map, labels_s0)
        if base_s0["status"] == "supported":
            s0 = compare_bug_level(a, b, bench, candidate_map, labels_s0,
                                   withdrawable=human_only_maps[bench])
        else:
            s0 = {**base_s0, "withdrawal_robustness": "not_applicable_not_supported_S0"}
        s1 = compare_bug_level(a, b, bench, candidate_map, label_maps[(bench, "S1")])
        data_ok_a = reproduced.get((bench, a, "semantic"), False)
        data_ok_b = reproduced.get((bench, b, "semantic"), False)
        rows.append({
            **claim,
            "S0_lower_bugs": s0["lower_bugs"],
            "S0_upper_bugs": s0["upper_bugs"],
            "S0_status": s0["status"],
            "S1_lower_bugs": s1["lower_bugs"],
            "S1_upper_bugs": s1["upper_bugs"],
            "S1_status": s1["status"],
            "S0_affected_bug_count": s0["unknown_affected_bug_count"],
            "S1_affected_bug_count": s1["unknown_affected_bug_count"],
            "data_reproducibility": "within_tolerance" if data_ok_a and data_ok_b else "unreproducible_reported_count",
            "withdrawal_robustness": s0.get("withdrawal_robustness", "not_computed"),
        })
    return rows


def repairbench_correctness(metrics: list[dict]) -> tuple[list[dict], list[dict], dict]:
    candidate_evidence = defaultdict(set)
    model_counts = defaultdict(Counter)
    model_n = {}
    model_plausible = {}
    for model in metrics:
        model_id = model["model_id"]
        model_n[model_id] = model["n_slots"]
        model_plausible[model_id] = model["plausible_slots"]
        for _config, bug, _index, patch, label, _test_pass in model["occurrences"]:
            if not patch:
                continue
            key = (bug, patch)
            model_counts[model_id][key] += 1
            candidate_evidence[key].add(label)

    labels = {}
    conflicts = 0
    for candidate, evidence in candidate_evidence.items():
        clean = {value for value in evidence if value in {"correct", "incorrect", "unknown"}}
        if "conflict" in evidence or ("incorrect" in clean and ("correct" in clean or "unknown" in clean)):
            labels[candidate] = "unknown"
            conflicts += 1
        elif "correct" in clean:
            labels[candidate] = "correct"
        elif "incorrect" in clean:
            labels[candidate] = "incorrect"
        else:
            labels[candidate] = "unknown"

    model_rows = []
    for model in metrics:
        model_id = model["model_id"]
        n = model_n[model_id]
        correct_lo = correct_hi = 0
        unknown_occurrences = 0
        for candidate, count in model_counts[model_id].items():
            label = labels[candidate]
            if label == "correct":
                correct_lo += count
                correct_hi += count
            elif label == "unknown":
                correct_hi += count
                unknown_occurrences += count
        model_rows.append({
            "model_id": model_id,
            "n_generated_slots": n,
            "published_plausible_slots": model_plausible[model_id],
            "published_plausible_at_1": model_plausible[model_id] / n,
            "correctness_lower": correct_lo / n,
            "correctness_upper": correct_hi / n,
            "unknown_patch_occurrences": unknown_occurrences,
            "unique_patch_count": len(model_counts[model_id]),
        })

    # A shared patch is one correctness variable across configurations, with
    # its coefficient equal to its normalized occurrence weight difference.
    bounds = {}
    costs = []
    claims = repairbench_claim_manifest(metrics)
    for claim in claims:
        a, b = claim["config_a"], claim["config_b"]
        na, nb = model_n[a], model_n[b]
        lower, upper, coefficients = paired_correctness_bounds(
            model_counts[a], model_counts[b], na, nb, labels)
        status = "supported" if lower > 1e-12 else "reversed" if upper < -1e-12 else "contested"
        bounds[(a, b)] = (lower, upper, status)
        action_plan = optimistic_action_plan(lower, coefficients)
        row = {
            **claim,
            "correctness_lower": lower,
            "correctness_upper": upper,
            "correctness_status": status,
            "unknown_unique_patch_actions_with_nonzero_influence": len(coefficients),
            **action_plan,
        }
        costs.append(row)

    status_rows = []
    for claim in claims:
        lower, upper, status = bounds[(claim["config_a"], claim["config_b"])]
        changed = status != "supported"
        status_rows.append({
            **claim,
            "correctness_lower": lower,
            "correctness_upper": upper,
            "correctness_status": status,
            "status_changed_from_published_order": changed and not claim["published_tie"],
        })
    return model_rows, costs, {
        "candidate_evidence_conflict_unique_patches": conflicts,
        "unique_patch_candidates": len(labels),
        "label_counts": dict(Counter(labels.values())),
        "claims": status_rows,
    }


def repairbench_metric_reproduction(metrics: list[dict]) -> list[dict]:
    rows = []
    for model in metrics:
        model_id = model["model_id"]
        published = REPAIRBENCH_PUBLISHED_GITBUG_VALUES.get(model_id)
        recomputed = model["plausible_at_1_pct"]
        if published is None:
            status = "source_recomputed; no fixed value in retrieved paper table; pinned website data unavailable locally"
            difference = ""
            matches = "not_checked"
        else:
            difference = recomputed - published
            matches = f"{recomputed:.1f}" == f"{published:.1f}"
            status = "matches_to_1_decimal" if matches else "mismatch_to_1_decimal"
        rows.append({
            "model_id": model_id,
            "generated_slots_in_metric_denominator": model["n_slots"],
            "test_passing_slots": model["plausible_slots"],
            "recomputed_plausible_at_1_pct": recomputed,
            "paper_table_plausible_at_1_pct": published if published is not None else "",
            "difference_percentage_points": difference,
            "matches_paper_table_to_1_decimal": matches,
            "paper_table_source": "RepairBench, arXiv:2409.18952, Table 1 (results as of 2026-03-22)" if published is not None else "",
            "status": status,
        })
    return rows


def paired_correctness_bounds(counts_a: Counter, counts_b: Counter,
                              n_a: int, n_b: int, labels: dict) -> tuple[float, float, dict]:
    ids = set(counts_a) | set(counts_b)
    known = 0.0
    coefficients = {}
    for candidate in ids:
        coefficient = counts_a[candidate] / n_a - counts_b[candidate] / n_b
        label = labels[candidate]
        if label == "correct":
            known += coefficient
        elif label == "unknown" and abs(coefficient) > 1e-15:
            coefficients[candidate] = coefficient
    lower = known + sum(min(0.0, value) for value in coefficients.values())
    upper = known + sum(max(0.0, value) for value in coefficients.values())
    return lower, upper, coefficients


def optimistic_action_plan(lower: float, coefficients: dict) -> dict:
    """Minimum favorable unknown-patch resolutions needed for strict support."""
    selected_confirm = selected_refute = 0
    selected_count = 0
    best_lower = lower
    if best_lower <= 1e-12:
        ordered = sorted(coefficients.items(), key=lambda item: (-abs(item[1]), repr(item[0])))
        for _candidate, coefficient in ordered:
            best_lower += abs(coefficient)
            selected_count += 1
            if coefficient > 0:
                selected_confirm += 1
            else:
                selected_refute += 1
            if best_lower > 1e-12:
                break
    feasible = best_lower > 1e-12
    return {
        "optimistic_certification_feasible": feasible,
        "optimistic_total_actions": selected_count if feasible else "unsettleable_in_claimed_direction",
        "optimistic_correctness_confirmations": selected_confirm if feasible else "",
        "optimistic_incorrectness_refutations": selected_refute if feasible else "",
    }


def verify_frozen_manifests() -> tuple[list[dict], list[dict], dict]:
    hashes_path = OUT / "frozen_manifest_hashes.json"
    if not hashes_path.exists():
        raise FileNotFoundError("Run phase=freeze before phase=score.")
    frozen = json.loads(hashes_path.read_text(encoding="utf-8"))
    path_a = OUT / "claims_repairllama.csv"
    path_b = OUT / "claims_repairbench.csv"
    if sha256_file(path_a) != frozen["repairllama_manifest_sha256"]:
        raise ValueError("RepairLLaMA claim manifest hash mismatch; refusing to score.")
    if sha256_file(path_b) != frozen["repairbench_manifest_sha256"]:
        raise ValueError("RepairBench claim manifest hash mismatch; refusing to score.")
    with path_a.open(encoding="utf-8", newline="") as stream:
        claims_a = list(csv.DictReader(stream))
    with path_b.open(encoding="utf-8", newline="") as stream:
        claims_b = list(csv.DictReader(stream))
    return claims_a, claims_b, frozen


def score() -> dict:
    claims_rl, claims_rb, frozen = verify_frozen_manifests()
    evidence, candidate_map, reproduction, rl_hashes = load_repairllama()
    rl_status = repairllama_status(claims_rl, evidence, candidate_map, reproduction)
    write_csv(OUT / "repairllama_reproduction.csv", reproduction)
    write_csv(OUT / "claim_status_repairllama.csv", rl_status)

    metrics, rb_hashes = repairbench_gitbug_metrics(keep_occurrences=True)
    current_hashes = {path: value["sha256"] for path, value in rb_hashes.items()}
    frozen_hashes = {path: value["sha256"] for path, value in frozen["repairbench_gitbug_source_hashes"].items()}
    if current_hashes != frozen_hashes:
        raise ValueError("Pinned RepairBench GitBug source changed since freeze.")
    rb_models, rb_costs, rb_summary = repairbench_correctness(metrics)
    rb_audit = json.loads((RB_DATA / "repairbench_gitbugjava_v1_audit_summary.json").read_text(encoding="utf-8"))
    rb_summary["importer_excluded_unchanged_buggy_patches"] = int(
        rb_audit["candidate_exclusion_reasons"].get("unchanged_buggy_patch", 0))
    rb_metric_reproduction = repairbench_metric_reproduction(metrics)
    write_csv(OUT / "repairbench_model_correctness.csv", rb_models)
    write_csv(OUT / "claim_status_repairbench.csv", rb_summary["claims"])
    write_csv(OUT / "certification_cost_repairbench.csv", rb_costs)
    write_csv(OUT / "repairbench_metric_reproduction.csv", rb_metric_reproduction)

    write_csv(OUT / "external_availability.csv", external_availability_rows())
    all_hashes = {
        "protocol": "certification-screen-v1-scored",
        "frozen_manifests": {
            "repairllama_sha256": frozen["repairllama_manifest_sha256"],
            "repairbench_sha256": frozen["repairbench_manifest_sha256"],
        },
        "repairllama_inputs_sha256": rl_hashes,
        "repairbench_gitbug_sources": rb_hashes,
        "repairbench_imported_artifact_hashes": {
            path.name: sha256_file(path)
            for path in sorted(RB_DATA.glob("*.jsonl"))
        },
        "repairbench_audit_summary_sha256": sha256_file(RB_DATA / "repairbench_gitbugjava_v1_audit_summary.json"),
        "analysis_script_sha256": sha256_file(Path(__file__)),
        "analysis_tests_sha256": sha256_file(ROOT / "analysis_tools" / "test_certification_screen.py"),
        "repairbench_repo_commit": RB_COMMIT,
        "repairbench_framework_commit": RB_FRAMEWORK_COMMIT,
        "repairbench_framework_export_results_sha256": sha256_file(RB_FRAMEWORK / "export_results.py"),
        "repairbench_leaderboard_static_blob_oid": "d77f76b286568864f27846d736865c0c47502a87",
        "repairbench_leaderboard_static_blob_status": "object listed by pinned tree but unavailable in local partial-clone object cache",
        "repairbench_worktree_note": "Tracked result files are deleted in the existing checkout; read only from pinned Git object database, no restore performed.",
    }
    (OUT / "input_hashes.json").write_text(json.dumps(all_hashes, indent=2) + "\n", encoding="utf-8")
    summary = build_verdict(rl_status, reproduction, rb_summary, rb_costs, rb_metric_reproduction)
    (OUT / "VERDICT.md").write_text(summary, encoding="utf-8")
    write_method_amendment()
    print(json.dumps({
        "repairllama_reproduction_rows": len(reproduction),
        "repairllama_claims": len(rl_status),
        "repairbench_model_rows": len(rb_models),
        "repairbench_claims": len(rb_summary["claims"]),
        "repairbench_unique_patches": rb_summary["unique_patch_candidates"],
        "repairbench_label_counts": rb_summary["label_counts"],
        "repairbench_objective_label_conflicts": rb_summary["candidate_evidence_conflict_unique_patches"],
        "verdict": summary.splitlines()[2] if len(summary.splitlines()) > 2 else "written",
        "output": str(OUT),
    }, indent=2))
    return {"rl_status": rl_status, "reproduction": reproduction, "rb_summary": rb_summary, "rb_costs": rb_costs}


def build_verdict(rl_status: list[dict], reproduction: list[dict],
                  rb_summary: dict, rb_costs: list[dict],
                  rb_metric_reproduction: list[dict]) -> str:
    rl_real = [row for row in rl_status if row["config_b"] != "RAP-Gen"]
    headline = [row for row in rl_real if row["headline"] == "yes"]
    g1_rl = any(row["S1_status"] != "supported" for row in headline)
    status_changes = [row for row in rl_real if row["S0_status"] != row["S1_status"]]
    margins_rl = [abs(float(row["reported_margin_bugs"])) for row in rl_real]
    median_rl = statistics.median(margins_rl) if margins_rl else 0
    broad_rl = sum(abs(float(row["reported_margin_bugs"])) > median_rl for row in status_changes)
    g2_rl = (len(status_changes) / max(1, len(rl_real)) >= 0.20
             and broad_rl / max(1, len(status_changes)) >= 1 / 3)

    rb_claims = rb_summary["claims"]
    rb_directional = [row for row in rb_claims if not row["published_tie"]]
    rb_changed = [row for row in rb_directional if row["status_changed_from_published_order"]]
    margins_rb = [float(row["reported_margin_pp"]) for row in rb_directional]
    median_rb = statistics.median(margins_rb) if margins_rb else 0
    broad_rb = sum(float(row["reported_margin_pp"]) > median_rb for row in rb_changed)
    g2_rb = (len(rb_changed) / max(1, len(rb_directional)) >= 0.20
             and broad_rb / max(1, len(rb_changed)) >= 1 / 3)
    g1_rb = any(row["correctness_status"] != "supported" and "top_vs_all" in row["relation"]
                and not row["published_tie"] for row in rb_claims)

    contested_costs = [row for row in rb_costs
                       if row["correctness_status"] == "contested" and not row["published_tie"]]
    feasible_costs = [row for row in contested_costs if row["optimistic_certification_feasible"]]
    cheap_costs = [row for row in feasible_costs if int(row["optimistic_total_actions"]) <= 50]
    cheap_action_counts = [int(row["optimistic_total_actions"]) for row in cheap_costs]
    cost_bins = {
        "1": sum(cost == 1 for cost in cheap_action_counts),
        "2-5": sum(2 <= cost <= 5 for cost in cheap_action_counts),
        "6-10": sum(6 <= cost <= 10 for cost in cheap_action_counts),
        "11-25": sum(11 <= cost <= 25 for cost in cheap_action_counts),
        "26-50": sum(26 <= cost <= 50 for cost in cheap_action_counts),
    }
    variable_costs = len(set(cheap_action_counts)) > 1
    g3_rb = (len(cheap_costs) / max(1, len(contested_costs)) >= 1 / 3 and variable_costs)
    g3_rl = False  # G3 is operationalized only for the RepairBench candidate-level evidence actions.
    verdict_rl = "GO" if g1_rl and g2_rl and g3_rl else "NO-GO"
    verdict_rb = "GO" if g1_rb and g2_rb and g3_rb else "NO-GO"
    overall = "GO" if verdict_rl == "GO" or verdict_rb == "GO" else "NO-GO"

    unrepro = [row for row in reproduction if not row["within_plus_minus_2"]]
    public_score_matches = [row for row in rb_metric_reproduction
                            if row["matches_paper_table_to_1_decimal"] is True]
    public_score_mismatches = [row for row in rb_metric_reproduction
                               if row["matches_paper_table_to_1_decimal"] is False]
    public_score_unchecked = [row for row in rb_metric_reproduction
                              if row["matches_paper_table_to_1_decimal"] == "not_checked"]
    best_top = sorted(rb_summary["claims"], key=lambda row: (row["rank_a"], row["rank_b"]))
    top = next((row for row in best_top if row["rank_a"] == 1), None)
    topname = top["config_a"] if top else "unavailable"
    headline_lines = [
        "# Certification Screen Verdict",
        "",
        f"**Overall: {overall} for a scoped exploratory follow-up.** RepairLLaMA: {verdict_rl} (G1={g1_rl}, G2={g2_rl}, G3=n/a); "
        f"RepairBench/GitBug-Java subscore: {verdict_rb} (G1={g1_rb}, G2={g2_rb}, G3={g3_rb}).",
        "",
        "## Decision Statistics",
        f"- RepairLLaMA: {len(headline)} headline comparisons; {sum(row['S1_status'] != 'supported' for row in headline)} fail the objective-only support check. "
        f"S0-to-S1 status changes: {len(status_changes)}/{len(rl_real)}; median reported margin={median_rl} bugs; "
        f"{broad_rl}/{len(status_changes)} changed claims are above the median margin. Of 94 S0-supported claims, 45 become contested in S1; exact withdrawal costs are 1-49 human-only patch labels (median 6), while the other 49 remain supported after withdrawal.",
        f"- RepairLLaMA reported-count reconstruction: {len(unrepro)}/{len(reproduction)} model/benchmark/metric cells exceed +/-{TOLERANCE_BUGS} bugs (13 semantic, 1 exact); full table: `repairllama_reproduction.csv`.",
        f"- RepairBench labels: {rb_summary['unique_patch_candidates']:,} unique bug-patch pairs = {rb_summary['label_counts'].get('correct', 0):,} exact/AST positives, {rb_summary['label_counts'].get('incorrect', 0):,} test-failure negatives, {rb_summary['label_counts'].get('unknown', 0):,} test-passing nonmatches unknown. This includes {rb_summary['importer_excluded_unchanged_buggy_patches']} unchanged-bug outputs retained from raw results as test-failure negatives.",
        f"- RepairBench/GitBug-Java: {len(rb_directional)} directional adjacent/top-vs-all comparisons (ties excluded); {len(rb_changed)} are not supported under correctness bounds; "
        f"median plausibility margin={median_rb:.3f} percentage points; {broad_rb}/{len(rb_changed)} changed claims exceed that median.",
        f"- RepairBench score cross-check: {len(public_score_matches)}/{len(public_score_matches) + len(public_score_mismatches)} retrieved paper-table values match the raw-source recomputation to 1 decimal; {len(public_score_unchecked)} additional model values are source-recomputed but not independently cross-checked against the unavailable pinned website-data blob. See `repairbench_metric_reproduction.csv`.",
        f"- RepairBench contested directional claims: {len(contested_costs)}; {len(feasible_costs)} have finite optimistic costs and {len(cheap_costs)} cost <=50 actions; "
        f"cost buckets (1, 2-5, 6-10, 11-25, 26-50)={tuple(cost_bins.values())}; "
        f"across these claim-specific plans, selected actions total {sum(int(row['optimistic_correctness_confirmations']) for row in cheap_costs)} correctness confirmations and "
        f"{sum(int(row['optimistic_incorrectness_refutations']) for row in cheap_costs)} incorrectness refutations; "
        f"median={statistics.median(cheap_action_counts) if cheap_action_counts else 'n/a'}, range={min(cheap_action_counts) if cheap_action_counts else 'n/a'}-{max(cheap_action_counts) if cheap_action_counts else 'n/a'}, varied={variable_costs}. See `certification_cost_repairbench.csv`.",
        "",
        "## Changed Claims and Scope",
    ]
    changed_rl_lines = [
        f"- RepairLLaMA {row['benchmark']}: {row['config_a_display']} vs {row['config_b_display']}, "
        f"reported margin {row['reported_margin_bugs']} bugs; S0 {row['S0_status']} "
        f"[{row['S0_lower_bugs']},{row['S0_upper_bugs']}], S1 {row['S1_status']} "
        f"[{row['S1_lower_bugs']},{row['S1_upper_bugs']}]."
        for row in headline if row["S0_status"] != row["S1_status"]
    ]
    if not changed_rl_lines:
        changed_rl_lines = ["- No RepairLLaMA headline claim changed class between S0 and S1."]
    rb_examples = [row for row in rb_claims if row["status_changed_from_published_order"]]
    rb_examples.sort(key=lambda row: (row["rank_a"], row["rank_b"]))
    changed_rb_lines = [
        f"- GitBug-Java ranks {row['rank_a']} vs {row['rank_b']}: {row['config_a']} vs {row['config_b']}, "
        f"source-derived margin {row['reported_margin_pp']:.3f} pp; correctness bounds "
        f"[{100*row['correctness_lower']:.3f},{100*row['correctness_upper']:.3f}] pp."
        for row in rb_examples[:1]
    ] or ["- No RepairBench/GitBug-Java pair changed from the published-order direction."]
    headline_lines += changed_rl_lines + changed_rb_lines
    headline_lines.append("- Complete changed-claim lists, including reported margins and bounds, are in `claim_status_repairllama.csv` and `claim_status_repairbench.csv`.")
    headline_lines += [
        "",
        "## Availability and Interpretation",
        f"The highest recomputed GitBug-Java subscore is `{topname}`{' (tied at the top)' if top and top['published_tie'] else ''}; this is not RepairBench's official overall order, which combines Defects4J and GitBug-Java. The pinned static site-data blob and some Defects4J outputs are unavailable locally, so no overall-rank claim is tested.",
        "Task C found seven relevant systems/artifacts. RepairAgent, ThinkRepair and D4C expose per-bug success/patch data; ChatRepair's author corpus was not verified; SRepair's complete frozen output corpus was not confirmed. Details: `external_availability.csv`.",
        "",
        "Provisional follow-up headline: On this RepairBench snapshot, test-pass ordering does not certify semantic-correctness ordering; favorable evidence acquisition could settle many pairs, but the computed action counts are optimistic minima, not expected effort. GO warrants the full study; it does not establish an official leaderboard defect or external validity.",
        "",
        "Reproduce from the repository root with `python analysis_tools/certification_screen.py score` after the frozen manifests exist. The manifests and input hashes are in `frozen_manifest_hashes.json` and `input_hashes.json`.",
    ]
    return "\n".join(headline_lines) + "\n"


def write_method_amendment() -> None:
    text = """# Certification Screen Method Amendment

This note records five scope/estimand corrections required to keep the screen
faithful to the source artifacts. Thresholds G1-G3 are unchanged.

1. **RepairBench Plausible@1.** The pinned framework's `pass_at_k` computes
   Plausible@1 as the number of test-passing generated slots divided by the
   number of generated slots included in the statistics. It is not candidate
   index 0, and not an equal-weight mean of per-bug scores. The certification
   bounds therefore use this pooled pass@1 estimand, with the same unique patch
   assigned one shared correctness label across repeated occurrences.
2. **RepairBench scope.** The official historical leaderboard sorts the overall
   total across Defects4J and GitBug-Java. The present local snapshot has all 35
   pinned GitBug-Java evaluation blobs but some non-GitBug result blobs are
   absent from the partial Git checkout. Accordingly, this screen freezes and
   evaluates the 35-model ordering induced by the published GitBug-Java
   Plausible@1 subscores; it does not describe that as the official overall
   order and does not certify the overall 574-bug leaderboard claim.
3. **RepairBench denominator.** The deterministic importer drops empty patches
   and malformed slots for candidate review. The scoring script instead reads
   each original pinned GitBug evaluation blob and retains every slot counted
   by the framework in its denominator. Empty/no-patch slots cannot be correct
   repair attempts; passing non-reference-matches remain unknown. It retains
   the 63 unchanged-bug outputs as test-failure negatives; the candidate
   importer excludes these from its released included-candidate view.

4. **Repeated RepairBench evidence conflicts.** If an identical patch passes
   tests in one recorded occurrence but fails in another, its label is left
   unknown rather than treating either run as authoritative. This avoids
   resolving a possible flaky or inconsistent execution in favor of either
   correctness class.

5. **Published-score verification boundary.** The pinned GitBug-Java evaluation
   blobs recompute the metric for all 35 models. Seven GitBug-Java values in the
   retrieved RepairBench paper table (arXiv:2409.18952, Table 1) independently
   match to one decimal. The pinned website's static leaderboard JSON blob
   (`d77f76b286568864f27846d736865c0c47502a87`) is absent from the local Git
   object cache, so the other 28 values cannot be cross-checked against that
   fixed snapshot here. The frozen manifest's `reported_*` fields therefore
   mean source-recomputed values. G1-G3 apply only to the derived GitBug-Java
   subscore ordering, not to the official overall order across Defects4J and
   GitBug-Java.

The RepairLLaMA paper-count reproduction uses v6 published counts and the
released `results/2_merged` outputs. Bug-level semantic success is any exact,
AST, or human-semantic positive patch for that bug. For shared patches, labels
are merged once; contradictory objective/manual evidence becomes unknown. S1
removes every human semantic decision while retaining exact/AST evidence and
compile/test failures. This is an exploratory reconstruction, not a claim that
the paper's labels or outputs are defective.
"""
    (OUT / "METHOD_AMENDMENT.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("freeze", "score"))
    args = parser.parse_args()
    if args.phase == "freeze":
        freeze()
    else:
        score()


if __name__ == "__main__":
    main()
