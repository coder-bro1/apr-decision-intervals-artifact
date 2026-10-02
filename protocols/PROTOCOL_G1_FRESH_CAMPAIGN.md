# Protocol G1: a fresh, pre-registered patch campaign

Frozen 2026-09-29, **before any candidate was generated**. Its SHA-256 is
recorded in `results/v4/protocol_freeze.json` before generation starts.
Nothing in this campaign has been looked at.

## 1. Purpose

Every reviewer noted that all our earlier data had been inspected before the
analysis was fixed. G1 is a confirmatory test of the same evaluation contract,
on candidates nobody has seen. The evidence-acquisition rule starts from zero
labels, so G1 also measures how much execution it takes to identify each
comparison when starting from nothing.

## 2. Bugs and inputs

- **Bugs.** The same 488 single-function Defects4J bugs. For each bug there is
  exactly one context: the one whose buggy method (anchor) is shortest after
  stripping whitespace, with ties broken by context id. This picks the variant
  without the Javadoc comment.
- **Information the generator sees.** Only the buggy method. There are no tests,
  no error messages and no developer fix. This is decision point 1.

## 3. Generator

- **Model.** `Qwen/Qwen2.5-Coder-7B-Instruct`, which is not among RepairLLaMA's
  14 configurations. It runs on the local RTX 3060 in 4-bit NF4 (bitsandbytes,
  bf16 compute). The revision hash is recorded in `models/model_revisions.json`.
- **Prompt.** A chat template:
  - system message: "You are an expert Java developer.";
  - user message: "The following Java method contains a bug. Fix the bug and
    return the complete fixed method only, in one ```java code block, with no
    explanation." followed by the method in a ```java block.
- **Sampling.**
  - 10 samples per bug: temperature 0.8, top-p 0.95;
  - `max_new_tokens` = min(2048, 2 × anchor tokens + 128);
  - seed = 20260930 + the bug's index in sorted bug order.
- **Extraction.** Take the first ```java block, or else the first ``` block,
  or else the whole output. Strip it. An empty extraction is kept as a
  candidate that is an empty string.
- **Provenance.** Every sample has source configuration
  `qwen2.5-coder-7b-instruct-nf4-t0.8` and candidate index 0–9, the sample
  number. Identical outputs are merged into one candidate, and every sample
  that produced it is kept as a source.

## 4. Policies, all fixed before generation

| Name | Definition |
|---|---|
| `challenger_frozen` | The Defects4J three-stage challenger, refit once on all 488 bugs as in `analysis_tools/v4/repairbench_v4.py`, applied unchanged |
| `occurrence` | Number of samples producing a program in the identity class (majority vote, also called self-consistency) |
| `uniform` | Random choice |
| `sample_order` | Lowest sample index (MRA); descriptive only, because sample order carries no information |
| `codet5_similarity` | As in D1 |
| `naturalness` | As in `ADDENDUM_V4_D1_NATURALNESS.md` |

The contract is unchanged: bug unit, AST identity, known-wins class labels,
N-a, uniform ties, exact shared-label bounds, equal-bug weighting, and top-k
with k = 3 and 5.

## 5. Pre-registered comparisons

- **Primary (P1):** `challenger_frozen` vs `occurrence`, budget-one success.
  The test is two-sided. It is reported as identified positive, identified
  negative, or open.
- **Secondary:**
  - S1: `occurrence` vs `uniform`;
  - S2: `challenger_frozen` vs `uniform`;
  - S3: `codet5_similarity` vs `uniform`;
  - S4: `naturalness` vs `uniform`;
  - top-k versions of P1 and S1.

## 6. Evidence acquisition, starting with every label unknown

1. **G-E0, no execution.**
   - Reference match: the class's AST equals the AST of the developer fix
     method, or the text is identical. Such a class is correct.
   - No-op: the class's AST equals the buggy method's AST. Such a class is
     incorrect (N-a).
   - Everything else is unknown.
2. **G-E1, execution.**
   - **Which classes run:** every class that is still unknown and
     decision-relevant (non-zero coefficient) in any pre-registered
     comparison. One representative each, the lowest sample index.
   - **How:** the unchanged census witness protocol (`run_census.py`, phase
     `full`, v3 image).
   - **Labels:**
     - a controlled trigger failure makes the class incorrect;
     - "compile command failed twice" while the fixed and buggy controls
       compile makes the class incorrect (primary). As a sensitivity analysis,
       such classes are left unknown instead;
     - admissible triggers pass (plausible) leaves the class unknown;
     - any other status leaves the class unknown.
   - Relevance does not depend on labels, so one round covers every
     comparison.
3. **G-E2 (if time allows).**
   - Decision-relevant test-passing unknowns go through the F3 differential
     tests and the F4-style blinded human review. The rules are the same as in
     those addenda.
   - Whether this stage finishes before submission is reported. If it does not
     finish, it is never reported partially.

## 7. What is reported, whatever it shows

For each comparison and each evidence view:

- the interval;
- the number of decision-relevant unknown classes;
- executions and container hours used.

Also reported:

- the break-down counts for P1 under the final view;
- the generation statistics (samples, distinct programs, classes, share that
  parse).

No other comparison is promoted to "primary" after results are seen.

## 8. Stopping rule

G-E1 executes every class selected in 6.2 once, and then stops. There are no
repeated rounds and no additional sampling.
