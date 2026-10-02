# Addendum to Protocol v4: re-running archived failures that equal the developer fix

Frozen 2026-10-01, before any re-execution. The hashes of this file and of the
selection are recorded in `results/v4/protocol_freeze.json`.

## Why

C1 (`ADDENDUM_V4_C1_EQUIVALENCE.md`) found 40 rename-aware classes that contain
a member equivalent to the developer fix but also carry an archived "incorrect"
label.

- Those labels cover 80 candidates in 38 bugs.
- Every one is `incorrect_test_failure`; 51 of them record a compile failure.
- Checked examples differ from the fix only by comments, blank lines or
  indentation.
- Because of these labels, 34 of the classes stay unknown (their members
  contradict each other), and the other 6 are labelled incorrect.

The C1 addendum forbids changing known labels, so treating these classes as
correct is only a post-hoc sensitivity. This addendum replaces it with evidence:
re-execute the archived failures under the unchanged census protocol.

## Selection (text only, no outcome read)

- **What:** every candidate with an archived (E0) label of 0 whose C1-id class
  contains a member equivalent to its context's developer fix. Equivalence is
  the same javac AST fingerprint or the same normalised AST.
- **Built by:** `analysis_tools/v4/select_c1_fixrerun.py`.
- **Result:** 80 candidates, 38 bugs, 40 classes. None is an existing census
  witness.

## Execution

This is the unchanged witness protocol of the census and F2:

- `execution_tools/run_census.py`, phase `full`, v3 image
  `sha256:9d43d93cc76845e19fb314247714f4015f0c5fd99277e6e90208069024e5d05e`;
- fixed, buggy and candidate controls, run twice;
- package built by `prepare_v4_rerun_package.py`.

## Rule

For each re-executed candidate:

- **`admissible_triggers_pass_semantics_unknown`:** the archived failure does
  not reproduce, so the archived "incorrect" label is removed and the candidate
  becomes unknown.
- **`controlled_trigger_failure`:** the archived failure reproduces, so the
  label stays 0. This is flagged, because a copy of the developer fix should
  not fail.
- **Any other status:** the archived label stays unchanged.

The C1-fix rule from the C1 addendum is then applied unchanged: a class with no
remaining known label and a fix-equivalent member becomes correct.

The resulting view is called **E1+F2+F3+F4+R**. All comparisons are reported
under AST identity and under C1-id, next to the post-hoc sensitivity it
replaces.
