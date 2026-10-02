# Addendum to Protocol v4: F2 census top-up for every pre-registered comparison

Frozen 2026-09-29, before any top-up candidate was executed.
Parent protocol: `PROTOCOL_V4_BUG_LEVEL.md`.

## Why

The original census executed only the decision-relevant unknowns of one
comparison (challenger vs native order), at context level. Reviewer 1 (E3)
pointed out a consequence: for other comparisons, "cannot show" mixes two
things, "the evidence says no" and "we never ran those patches".

## Selection

The selector is `analysis_tools/v4/select_f2_topup.py`. It is run once, after
the naturalness and entropy-delta scores exist, so that all pre-registered
comparisons are included.

- **Comparisons:** challenger against every baseline in Protocol v4, Section 4.
  All use the primary specification: bug unit, AST identity, known-wins,
  N-a, E1.
- **Take** every decision-relevant unknown identity class of those
  comparisons.
- **Exclude** a class when either holds:
  - one of its members is already in the census;
  - every member passed the archived tests unanimously. Execution cannot
    reject such a class, so it goes to F3/F4.
- **One run per remaining class:** its representative is the member with the
  smallest candidate id.

## Execution

The runner is unchanged: `execution_tools/run_census.py`, phase `full`. The
witness protocol is also unchanged: fixed, buggy and candidate controls, two
repetitions, admissible triggers, and both coefficient signs.

- Image: the v3 / Java 11 census image,
  `sha256:9d43d93cc76845e19fb314247714f4015f0c5fd99277e6e90208069024e5d05e`.
- Package: `prepare_v4_rerun_package.py --image v3_jdk11 --candidates
  results/v4/f2_topup/f2_candidates.json`.

## Use

- A representative whose status is `controlled_trigger_failure` becomes a
  rejection witness. Its whole identity class is then labelled incorrect in a
  new evidence view: **E2 = E1 plus the F2 witnesses**.
- Every other status leaves the class unknown.
- All comparisons are reported under E0, E1 and E2.
- The share of representatives in each status is reported, whatever it is.
