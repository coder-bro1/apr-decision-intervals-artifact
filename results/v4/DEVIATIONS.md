# Deviations from frozen protocols and addenda (v4)

This file records every execution detail that differs from, or is not spelled
out in, the frozen texts. Each entry is recorded before the affected results
are analysed.

1. **F3: `bc` shim and container hostname** (2026-09-29, found during the smoke
   test before any production F3 run).
   - What went wrong: the pinned v2 image has no `bc`. Defects4J's
     `evosuite.sh` and `randoop.sh` use it to split the time budget
     (`echo "$D4J_TOTAL_BUDGET/2/$num_classes" | bc`). The result was empty, so
     EvoSuite failed with "Invalid value for property assertion_timeout".
   - Fix: the runner puts an integer-arithmetic `bc` replacement in `/tmp`.
     It gives bc's default scale-0 result.
   - Also: with `--network none`, the random container hostname did not
     resolve, which risks EvoSuite's local RMI. Containers now run with
     `--hostname localhost`.
   - Effect: the generators run as Defects4J intends. The first smoke attempt
     (`results/v4/f3_smoke_run_v1`) is kept and is not used.
2. **H1 bootstrap worker count** (2026-09-29).
   - What went wrong: the refit bootstrap ran out of host memory at replicate
     549 of 2,000, because 8 workers ran alongside the GPU scoring jobs and the
     Docker census.
   - Fix: it resumed with 5 workers.
   - Effect on results: none. Each replicate's resample is fixed by seed
     20260929 + r, completed replicates were kept, and fits are
     single-threaded, so results do not depend on the worker count.
3. **D1 naturalness launches** (2026-09-29).
   - What went wrong:
     - the first launch failed before scoring, because of offline resolution
       of the model snapshot;
     - the second failed on its first batch with CUDA out-of-memory.
   - Fix: the model is loaded from the local snapshot path, and batches are
     now built by token length. Neither failed launch wrote any score.
   - Effect: none on the definition in the addendum.
4. **APPT checkpoint loading** (2026-09-29).
   - What went wrong: the released checkpoint contains the buffer
     `bert.embeddings.position_ids`, which current `transformers` no longer
     registers.
   - Fix: only that constant buffer is dropped. Every other weight must match
     exactly (strict check).
5. **G1 sampling settings enforced** (2026-09-30, before any G1 sample was generated). An independent review found that the model snapshot's `generation_config.json` silently adds `top_k=20` and `repetition_penalty=1.1`. The protocol specifies temperature 0.8 and top-p 0.95 only. `g1_generate.py` now switches both extras off explicitly and records the effective generation config in `results/g1/generation_meta.json`. Other G1 hardening:
   - the batch split is fixed by prompt length, with an out-of-memory fallback of one sample per call, recorded per bug;
   - a torn last line after a crash is cut off on resume;
   - each record is flushed to disk (fsync).
   Sampling is unchanged apart from enforcing the protocol.
6. **E2 analysis aligned with the addendum** (2026-09-30, before any permutation ran).
   - success@1 is computed only over pools with at least one known-correct or unknown candidate, as the addendum states. The first version averaged over all 465 pools. Canonical E0 moves from [41.0, 60.5] to [56.6, 83.3]%, over 340 pools and 227 bugs.
   - Added: first-correct rank; the share of permutations whose interval lies entirely above or below canonical; check T as a per-group share (0.755 canonical), next to the pairwise agreement (0.917).
   - Only permutations with a completion marker are analysed.
7. **Overnight job orchestration hardened** (2026-09-30), after a 28-agent adversarial review (`results/v4/overnight_review_findings.json`; 19 of 25 findings confirmed). None of these changes alters any measurement:
   - fail-closed process checks;
   - crash-resumable queue markers;
   - QuickEdit disabled in job consoles;
   - a Docker watchdog that pauses jobs while Docker is down, instead of letting census jobs be recorded as container failures;
   - `resume_prep --retry-container-failures`;
   - the E2 driver continues after a failed permutation and removes orphan PrevaRank containers.
8. **G1: two bugs without a buggy method** (2026-09-30).
   - Chart-23 and Collections-27 have only an empty context (no anchor, zero candidates) in the frozen dataset, so the frozen context rule sent the model an empty method. Their generations are meaningless and are ignored.
   - The two bugs stay in the 488-bug denominator with empty pools, exactly as in the Defects4J pool, so each contributes 0 to every difference.
9. **E3 HumanEval-Java runner** (2026-10-01). The original RepairBench runner used `mvn test` with JUnit 4.13.2. E3 compiles with `javac` and runs JUnit 4.12 `JUnitCore`, using the jars shipped in the benchmark's own `lib/`, inside `maven:3.9-eclipse-temurin-8` with no network access.
   - The tests use only `@Test(timeout)` and `Assert`, which behave the same in both JUnit versions. The addendum states this choice before any run.
   - The smoke run (`results/v4/e3_smoke_v1`, SORT_ARRAY) is not counted. Production reruns that bug.
10. **Analyses designed after seeing a related result** (2026-10-01). Each is labelled post hoc in its output, and none replaces a pre-registered result.
   - **E3 `X4-posthoc`:** equivalence plus execution negatives only, trusting no archived review label. Added after tier A, because F5 questioned archived "correct" labels.
   - **C1 `c1+fix+override(posthoc)`:** fix-equivalent classes set correct even when archived incorrect. It was replaced by the pre-specified re-run in `ADDENDUM_V4_C1_FIXRERUN.md`, which was itself designed after this sensitivity was seen. The addendum says so.
   - **Single-function audit (`analysis_tools/v4/single_function_audit.py`):** triggered by the JxPath-14 re-run result.
11. **F3/F4 labels are applied to whole AST classes** (`final_evidence.py`). A class can only have known members overwritten when those members' archived labels contradict each other (identical AST, labels 0 and 1). This happened for 2 F4 classes, Mockito-29 (set correct) and Gson-5 (set incorrect), and is logged. Any other overwrite raises an error.
12. **C1 normaliser caveat.** `BatchMethodNormalize` removes annotations, so a candidate that adds `@Override` to a non-overriding method (Collections-26) counted as equivalent to the fix. The C1 fix re-run kept it incorrect (`compile_command_failed_twice`), so equivalence alone is never used to overturn an execution result.
14. **Determinism fix.** `c1_fixrerun_analysis.py` now sorts its status counts. Before, set iteration order changed the JSON key order between runs; the content was identical.
15. **Leave-one-layer-out sensitivity** (`analysis_tools/v4/decidability_sensitivity.py`, 2026-10-01). This was added after the final results and the independent audit, and it is exploratory. It versions the audit's read-only check: no F3 layer plus R without C1-fix, and context-split identity. It extends the check to every evidence layer.
