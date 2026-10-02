# F3 relevance review (tier 1)

Rule: `ADDENDUM_V4_F3_DIFFTEST.md`, section "Relevance rule". Every counterexample was
read in the review below. The verdicts and reasons are in `relevance_review.json`; the
unreviewed file is kept as `relevance_review.pre_review.json`.

- **When:** 2026-10-01, after F3 tier 1 finished (76/76 jobs).
- **Who:** Claude (AI assistant), at the author's request. This goes in the AI-use statement.
- **How:** each counterexample's generated test source and failure message was read
  next to the candidate's diff against the developer fix. The view comes from
  `analysis_tools/v4/f3_review_view.py`; `f3_record_verdicts.py` records the verdicts.
  - For Lang-45 (570 items), every item was read in a compact listing: its
    `abbreviate(...)` call and the failure message.
  - The 11 items whose call the listing could not extract were opened individually.

## Result

**All 612 counterexamples are witnesses (not excluded).** They come from 23
candidates across 11 bugs, and none meets exclusions (a)–(d).

| Bug | Candidates | Counterexamples | Behavioural difference |
|---|---:|---:|---|
| Chart-1 | 1 | 2 | Null dataset: the fix returns an empty legend; the candidate throws NullPointerException |
| Chart-8 | 1 | 5 | Null time zone: the fix throws IllegalArgumentException; the candidate ignores the argument |
| Cli-17 | 1 | 1 | `flatten` returns 4 tokens instead of 3 (an extra "--") |
| Cli-19 | 1 | 1 | With `stopAtNonOption=false` the candidate stops at the first unknown option (throw vs no-throw) |
| JacksonCore-25 | 1 | 1 | NullPointerException instead of IOException (different exception type) |
| Jsoup-39 | 1 | 2 | Empty input: the fix returns an empty Document; the candidate returns null |
| Lang-24 | 1 | 2 | `isNumber("L")` and `isNumber("l")`: the fix returns false; the candidate returns true |
| Lang-45 | 4 | 570 | `abbreviate` returns a different string, or does not throw where the fix throws; the candidates clamp `lower` differently |
| Math-3 | 1 | 4 | Empty arrays: the fix throws ArrayIndexOutOfBoundsException; the candidate returns 0 |
| Math-72 | 1 | 2 | Returns 0.0 instead of the endpoint; also an iteration count of 31 instead of 0 for the same root |
| Math-85 | 10 | 22 | No sign change once both bounds are reached: the fix throws ConvergenceException; the candidates return a non-bracketing interval |

By kind of difference:

- different return value or observable state: 575;
- throw vs no-throw: 36;
- different exception type: 1.

## Points considered under the exclusions

- **(d) mocked environment.**
  - **Chart-8:** EvoSuite `MockDate` / `MockGregorianCalendar` appear only as inputs.
    The same difference shows in Randoop tests without mocks.
  - **Jsoup-39:** the EvoSuite `MockFile` supplies the same empty file to both versions,
    and a real empty file gives the same difference.
  - **JacksonCore-25:** the Mockito `ObjectCodec` mock is not on the path of the difference.
  - In all three, the difference comes from the patched code, not from the mock.
- **(b) exception message text.** No item differs only in message text. Every
  exception-related item differs in throw vs no-throw or in exception type.
- **(c) unspecified output.** No item compares `toString()`, `hashCode()`, identity
  or unordered iteration.
  - Math-72 `test04` compares `getIterationCount()`, a public accessor, so it counts as
    observable state. That candidate also has a return-value witness (`test18`).
- **(a) environment.** No timeout, out-of-memory, or generator runtime failure
  appears among the counterexamples.

## Consequence

The 23 candidates' classes are labelled incorrect in the view E1+F2+F3, built by
`analysis_tools/v4/final_evidence.py`.

Cross-check with the independent two-annotator review (F4):
- none of the 19 classes the annotators judged correct has a counterexample;
- 4 of the 25 they judged incorrect do.
