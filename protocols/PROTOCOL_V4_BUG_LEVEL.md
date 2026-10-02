# Protocol v4: Bug-Level Re-Analysis and Revision Analyses

Frozen 2026-09-29 (Dhaka), before any production v4 result was computed.
Implements REVISION_PLAN.md items A1-C3, D1, D3, E1, E4, H1, and the
evidence-acquisition items F1-F6 and G1 as separately frozen addenda.

## Disclosure (analysis status)

On 2026-09-29, during the FSE-submittability audit (workflow
`wf_d3f6b33d-ec3`), read-only exploratory probes computed preview versions of
several cells defined below (bug-level, identity and no-op variants,
before/after census). Probe scripts: `t1_probe.py`, `t1_multiverse_probe.py`,
`bug_level_preview.py`, `breakdown_preview.py`, `baseline_preview.py`,
`pod_preview.py`, `t4_probe.py`, in the session scratchpad.

Therefore **no v4 analysis on the RepairLLaMA/Defects4J pool, POD or RepairBench
is confirmatory**. The status of each analysis is:
- **"pre-specified on inspected data"**, if its definition below did not
  change after the probes;
- **"post hoc"**, where the probes informed the choice. The primary no-op rule
  (N-a) and the reporting of the full specification grid are labelled
  "post hoc, informed by exploratory probes".

Only G1 (a fresh campaign) can be confirmatory.

## 1. Inputs (frozen; hashes recorded by the v4 scripts)

- `results/contract_step1/{contexts,decision_candidates,evaluation_evidence}.jsonl`:
  the candidate occurrences, sources and accepted evidence labels (E0).
- `results/pilot_step2/predictions.jsonl`, role `test`: frozen held-out
  challenger scores (product of the compile, test|compile and correct|test
  stages), one per occurrence.
- `results/noop_filter/v1/{candidate_structure.jsonl,parser_output.tsv}`:
  the javac AST digests (`BatchMethodFingerprint`, comments and whitespace
  removed, annotations kept) and the no-op structure.
- `results/conflict_census/summary_v1/candidate_evidence.json`: the census.
  **E1** = E0 plus the 185 `controlled_trigger_failure` candidates set to
  incorrect.
- The label provenance comes from the archived candidate records in
  `llm_apr_dataset` (reference match / execution failure / human judgment).

## 2. Unit, identity, labels

- **Decision unit: the bug** (488). The pool of bug b is the union of its
  contexts' candidates. The metric is budget-one expected correctness,
  averaged over bugs with equal weight. A bug with no eligible candidate
  abstains and scores 0.
- **Identity (primary I-ast).** Occurrences are the same candidate when their
  javac AST digests are equal (status `ok`). Otherwise the key is the exact
  text with leading and trailing whitespace stripped.
- **Identity sensitivities:**
  - I-exact: exact text;
  - I-ast-noann: AST digest with annotations removed;
  - I-alpha: AST with consistent renaming of local variables and parameters
    (C1).
- **Class label (primary "known-wins").**
  - A class takes the common known label of its members when all known
    labels agree, even if other members are unknown. Equal programs have
    equal correctness, up to debug line numbers; this caveat is stated.
  - Classes with conflicting known labels are unknown, and their count is
    reported.
  - Sensitivity "strict": a class is known only if all members are known and
    agree.
- **Class scores.**
  - Challenger: the maximum member score.
  - Minimum-rank aggregation (MRA; the draft's "native order", renamed): the
    minimum over members of the minimum `candidate_index` across sources.

## 3. Policies and ties

- **Selection** is uniform over the classes tied at the best score (primary).
- **Tie sensitivities (B5):**
  - (i) archived file order: the first occurrence in context order, then
    candidate order;
  - (ii) the smallest SHA-256 of the class key. This is label-independent.
- **No-op rule.** A class is a no-op when its AST digest equals the buggy
  method's digest (existing structure flags). Three treatments:
  - **N-a (primary):** frozen unfiltered policies; no-op classes are evidence
    for "incorrect", because every executed buggy control failed its
    triggers. An accepted-correct no-op is a contradiction: keep the known
    label and report it.
  - **N-b:** no-op classes are ineligible for both policies (the draft's
    filter).
  - **N-c:** neither.
  - **Stronger-normaliser sensitivity (B4):** also treat as no-op the classes
    whose AST differs from the buggy method only in `throws` clauses (the
    Time-18 pattern).
- **Eligibility sensitivity (B6):** all candidates; compilable-only;
  plausible-only (accepted or recorded test pass). These are post-execution
  pools; plausible-only is decision point 2 (D2).

## 4. Comparisons

- **Primary:** challenger vs MRA, under I-ast, known-wins, N-a, uniform ties,
  evidence E1. Reported with E0 as well.
- **Pre-registered secondary** (same contract):
  - challenger vs best single configuration top-1. The configuration is
    chosen per rotation on its training-fold bugs only: the highest share of
    bugs whose rank-0 candidate is accepted correct, ties broken by
    configuration name;
  - challenger vs first global occurrence (the smallest archived position);
  - challenger vs Borda: score = Σ over sources of (1 − index/n_s), where
    n_s is that source's candidate count for the bug;
  - challenger vs reciprocal-rank fusion: Σ 1/(60 + index);
  - challenger vs mean normalised position;
  - challenger vs occurrence count = plurality over identity classes;
  - challenger vs MRA plus occurrence (lexicographic: occurrence, then MRA);
  - challenger vs testability product (compile × test|compile);
  - challenger vs a one-stage logistic model on the same metadata (fit per
    rotation on training folds);
  - challenger vs CodeT5+ similarity;
  - challenger vs naturalness/entropy-delta from a local code LM (D1; its own
    addendum);
  - MRA vs every baseline, as a descriptive matrix.
- **Grid (reported in full):** unit {context, bug} × identity {exact, ast,
  ast-noann} × label rule {known-wins, strict} × no-op {N-a, N-b, N-c} ×
  evidence {E0, E1}, for the primary pair.

## 5. Robustness (B3, C1)

For every identified comparison, report exact minima (by sorting influence
|d_c|):
- (i) witnesses withdrawn to unknown until L ≤ 0;
- (ii) accepted labels **withdrawn** to unknown, and separately **flipped**,
  until L ≤ 0. Reported per provenance basis: human judgment, archived
  execution failure, reference match;
- (iii) the effect of counting the 10 re-executed consistent compile
  failures as incorrect;
- (iv) placement and setup failures are already adversarial as unknowns.
  Stated.

Label-error budget curve: L as a function of the number of adversarial
flips m.

Missing-at-random frontier: unknown test-passers in a stratum are correct with
probability within [ρ − δ, ρ + δ] of the reviewed test-passers in the same
stratum (strata: bug project). Report the δ at which L = 0.

## 6. Beyond budget one (C2)

- Success within k (k = 3, 5).
- Expected attempts to the first correct class, capped at 5.
- Exact per-bug bounds by enumerating correct counts per cell of the joint
  partition of the two policies' tie blocks that intersect either top-5.
  Bugs are summed.
- Verified exhaustively on random small pools against brute force.

## 7. POD and ratio metrics (C3, E1)

- Balanced-accuracy differences between detectors on the 169-patch split.
  The 79 skipped-review negatives are unknown. Exact bounds by enumerating
  the number of true positives among the unknowns and sorting.
- Plus bootstrap CIs on the 90 reviewed patches (10,000 resamples, seed
  20260929).
- A label-polarity check for DL4PatchCorrectness.
- Re-examination of the source paper's headline comparison on its
  RepairLLaMA subset.

## 8. Inference (H1)

- An Imbens-Manski CI for the primary bug-level Δ.
- A bug-cluster bootstrap that refits the three logistic stages inside each
  replicate (2,000 replicates, seed 20260929).
- Coverage simulation: 1,000 replicates per scenario, with within-bug
  dependence.
- If the coverage validation fails, report identification intervals and
  break-down numbers only.
- The ad hoc outer region is removed in all cases.

## 9. Acquisition addenda (frozen separately, before each run)

Each is frozen in its own addendum before it runs:
- F1: v2/Java 8 concordance of all 185 witnesses plus 67 trigger-passers;
- F2: census top-up for every pre-registered comparison;
- F3: EvoSuite/Randoop differential witnesses with a frozen relevance rule;
- F4/F5: human review with two annotators;
- F6: a random false-rejection panel of 100;
- E2: PrevaRank permutations (50);
- E3: the HumanEval-Java harness;
- G1: the fresh campaign.

## 10. Reporting rules

- All numbers are exact fractions; they are converted to percentage points
  only for display.
- Every v4 result file records this protocol's SHA-256 and its input hashes.
- Nothing in the July or September frozen artifacts is modified.
