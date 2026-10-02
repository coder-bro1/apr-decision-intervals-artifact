# Addendum to Protocol v4: F3 differential tests for test-passing unknowns

Frozen 2026-09-29, before any test was generated.
Parent protocol: `PROTOCOL_V4_BUG_LEVEL.md`.

## Question

Can automatically generated tests reject test-passing unknown candidates? These
are candidates that pass the project's own tests but whose correctness nobody
has confirmed.

The idea: generate tests on the developer-fixed program, then run them on the
candidate. **Passing generated tests never proves correctness.** Only failures
are used.

## Targets

- The selector is `analysis_tools/v4/select_f3_targets.py`. It takes the
  decision-relevant unknown identity classes in which **every** member passed
  the archived tests unanimously, under the primary specification (bug unit,
  AST identity, known-wins, N-a, E1). One representative per class: the
  member with the smallest candidate id.
- **Tier 1:** the classes relevant to challenger vs any baseline other than
  uniform.
- **Tier 2:** the remaining classes relevant only to challenger vs uniform.
- Tier 1 runs first. Tier 2 follows in the same way.

## Environment

- The v2 / Java 8 image,
  `sha256:335001efa26b313093968f26dee062e31ae69a8b24f0e9ecb124ae97b73b9323`,
  with Defects4J at commit `01f13c69`, EvoSuite 1.0.6 and Randoop 4.2.2.
- No network. The same container limits as the census.

## Procedure, per bug

1. Check out the buggy (`b`) and fixed (`f`) versions.
2. Generate tests on the fixed version for the classes the fix modifies:
   - EvoSuite, suite ids 1 and 2, with a 180-second budget each;
   - Randoop, suite id 1, with a 180-second budget.
3. Remove tests that fail on the fixed version with Defects4J
   `fix_test_suite.pl`. Only suites that still contain tests are used.
4. Run every remaining suite with `defects4j test -s` on these variants:
   - the fixed version;
   - the buggy version (for information only);
   - each representative candidate, placed into the buggy version with the
     census `place_method`.
   Each suite runs twice. The second repetition uses the reverse variant order.

## Candidate counterexample

A generated test is a **candidate counterexample** for a candidate when both
hold:

- it passes on the fixed version in both repetitions;
- it fails on the candidate in both repetitions.

The candidate and the fix differ only inside the patched method, so a
deterministic difference in outcome shows a behavioural difference between the
candidate and the developer fix.

## Relevance rule

A candidate counterexample becomes a **rejection witness** unless, on reading
the test source and the failure message, the only difference is one of:

- **(a) Environment.** Timeouts, out-of-memory, security-manager or other
  generator runtime failures.
- **(b) Exception message text.** Only the text of an exception message
  differs, while the type of the thrown exception and the thrown-or-not
  outcome are the same.
- **(c) Unspecified output.** Only `toString()`, `hashCode()`, identity-based
  output, or iteration order of unordered collections differs.
- **(d) Mocked environment.** The difference comes from mocked time,
  randomness, files or network that EvoSuite introduced.

Anything else, such as a different return value, a different exception type,
or throw-versus-no-throw, is a witness.

Every candidate counterexample is inspected by hand, with verdict and reason
recorded in `results/v4/f3_difftest/relevance_review.json`, and all are
reported. A candidate with at least one witness has its class labelled
incorrect in the evidence view **E3 = E2 plus the F3 witnesses**. All other
classes stay unknown.

## Limits stated up front

- Generated tests cover only the classes the fix modifies, within the budget.
- The absence of a counterexample says nothing about correctness.
