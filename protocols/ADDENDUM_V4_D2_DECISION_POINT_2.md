# Addendum to Protocol v4: D2, decision point 2 (after tests pass)

Frozen 2026-09-29, before any D2 comparison was computed.
Parent protocol: `PROTOCOL_V4_BUG_LEVEL.md`, Section 3. It defines
plausible-only eligibility, meaning unanimous archived compile and test
passes, as decision point 2.

## Pool

Everything follows the primary specification (bug unit, AST identity,
known-wins, N-a, uniform ties, E0 and E1), with one change: both policies may
choose only classes that contain a plausible member. A policy with no eligible
class in a bug abstains, and contributes 0 to that bug.

## Policies

| Policy | Score of a class (maximum over members, unless stated) |
|---|---|
| `challenger` | The three-stage product. Within plausible pools it ranks like the correctness stage times the test-pass stages. |
| `correctness_stage` | The challenger's P(correct given compiled and test-passing). This is its stage 3, which is the relevant stage at decision point 2. |
| `mra`, `occurrence`, `codet5_similarity`, `naturalness`, `entropy_delta` | As in D1 |
| `appt` | 1 − P(overfitting) from the authors' released APPT checkpoint (`analysis_tools/v4/appt_scores.py`), used only if its gate passes |
| `prevarank` | See below |

`prevarank` uses the released PrevaRank output on the canonical native-order
run (`results/v2/prevarank_llm_mixed_evaluation_ledger.jsonl`), joined to v4
candidates through legacy ids.

- **Candidate score:** −(rank − 1) / (pool size), which is its normalized
  position in its context pool.
- **Class score:** the maximum over members.
- **Unranked members** (not in PrevaRank's 4,180-patch input) get −2, below
  every ranked patch.
- The share of plausible classes that PrevaRank did not rank is reported.

## Comparisons

- `challenger` and `correctness_stage`, each against every other policy.
- `prevarank` against `mra` and `occurrence`.
- `appt` against `mra` and `occurrence`.

For each: budget-one bounds, top-k (k = 3, 5) bounds, and the number of
decision-relevant unknown classes.

## Caveats reported with the results

- APPT was trained on Defects4J patches from classic APR tools, for bugs that
  overlap ours.
- PrevaRank's result depends on input order (E2).
