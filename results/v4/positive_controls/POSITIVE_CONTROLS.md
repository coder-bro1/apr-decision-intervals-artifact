# C5: built-in positive controls in released LLM-APR archives

Exploratory and post hoc. Nothing was executed for this analysis. Script: `analysis_tools/v4/positive_controls.py`; data: `positive_controls.json`, `flagged_occurrences.jsonl`.

## Headline (L1 text identity unless stated)

- Fix copies archived as failing: RepairLLaMA Defects4J 201/1871 (10.7%; 9.4-12.2) in 56 bugs; HumanEval-Java 440/2849 (15.4%; 14.1-16.8) in 98 bugs; RepairLLaMA GitBug-Java 0/585 (0.0%; 0.0-0.6); RepairBench GitBug-Java 56/2197 (2.5%; 1.9-3.3) in 6 bugs (not clean).
- Defects4J by configuration: GPT-4 88/273 (32.2%; 26.7-38.1), GPT-3.5 52/156 (33.3%; 26.0-41.3), IR1xOR3 12/29 (41.4%; 23.5-61.1); RepairLLaMA IR4xOR2 4/175 (2.3%; 0.6-5.8), DeepSeek LoRA 2/161 (1.2%; 0.1-4.4). Most GPT failures are compile failures (GPT-4 82 of 88).
- The Defects4J gap is not bug mix: on the 51 bugs where both produced copies, GPT-4 77/230 (33.5%; 27.4-40.0) vs RepairLLaMA 2/79 (2.5%; 0.3-8.8) (MH odds ratio 26.057, p = 1.1e-07).
- HumanEval-Java: GPT-3.5 151/386 (39.1%; 34.2-44.2), IR1xOR3 18/48 (37.5%; 23.9-52.6), IR2xOR2/IR3xOR2/IR4xOR2 24-27%, GPT-4 100/486 (20.6%; 17.1-24.4); the 6 DeepSeek and zero-shot/full-fine-tuning CodeLlama configurations 0/1262. Here GPT-4 and RepairLLaMA do not differ on shared bugs (86/433 (19.9%; 16.2-23.9) vs 31/133 (23.3%; 16.4-31.4), p = 0.757); the split is between two groups of configurations.
- Validation already on disk: R did not reproduce 68/71 (95.8%; 88.1-99.1) of the resolved re-runs (68 of 80 overall, 9 unresolved placement); inside the positive-control scope at L1-L2 68/68 (100.0%; 94.7-100.0). Every HumanEval-Java failing copy whose exact text E3 executed passed: 185/185 (100.0%; 98.0-100.0).
- Published counts: the 23 stated directions never reverse. The conceded HumanEval-Java GPT-4 > RepairLLaMA margin (116 vs 109) shrinks to +3 if every flag is spurious, +5 with the validated-or-equivalent flags, and would only reverse (-1) if RepairLLaMA's flags were all spurious and GPT-4's all genuine. Orderings inside a published table that change are listed in section 5.

## Discrepancies with the panel probe

- Defects4J total: probe 197/1,867 (curated `all` file, all bugs, v4core.text_norm); here 203/1873 (10.8%; 9.5-12.3) from the raw files over all bugs and 201/1871 (10.7%; 9.4-12.2) in the single-method scope. The raw files hold 629 evaluated outputs that the curated files do not.
- RepairLLaMA IR4xOR2 on Defects4J: probe 5/176 (2.8%); here 4/175 (2.3%; 0.6-5.8). The fifth failure is JxPath-14, which is outside the positive-control scope (its fix spans 3 methods).
- GPT-4 on Defects4J: probe 87/272; here 88/273 (32.2%; 26.7-38.1), which matches the judge's raw-file count.
- HumanEval-Java: probe 438/2,847; here 440/2849 (15.4%; 14.1-16.8). GitBug-Java: probe 0/583; here 0/585 (0.0%; 0.0-0.6). RepairBench: 56 failing copies in 6 bugs, as in the check report.
- Opposite verdicts on byte-identical outputs: Defects4J GPT-4 23 and GPT-3.5 13 strings among fix copies, as in the probe (all outputs: 34 and 21). HumanEval-Java does not match the probe's 54 and 42: GPT-4 45 and GPT-3.5 59 among fix copies, 69 and 94 over all outputs.
- Byte-identical outputs that both compiled and failed to compile in the same bug (compilation should be deterministic): Defects4J GPT-3.5 255, GPT-4 201, IR1xOR4 77, IR1xOR3 54; HumanEval-Java GPT-3.5 134, GPT-4 29. The probe did not report this. Only configurations that repeat outputs can show it, so it cannot be compared across all configurations.
- Defects4J count deltas (semantic, L1): GPT-4 +8, IR1xOR3 +6, CodeLlama zero-shot IR3 +6, GPT-3.5 +5, CodeLlama full FT +5, RepairLLaMA IR4xOR2 +3, IR2xOR2 +3; the check report had +8, +7, +6, +5, +5, +4, +4. IR1xOR3's extra bug there is Codec-17, a text_norm false positive (`new String` vs `newString`). Re-running the check script's own logic (curated file, single-method bugs) gives RepairLLaMA +3 and IR2xOR2 +2, so its +4 values could not be reproduced; the per-bug lists used here are in positive_controls.json. The HumanEval-Java deltas match the check report.
- HumanEval-Java E3 overlap: the check report found 110 of 131 flagged records with an equivalent text in E3. Here, of 318 unique failing copy candidates (L3, any label), 185 exact_text_executed:admissible_all_tests_pass, 113 only_other_copy_text_in_bug:admissible_all_tests_pass, 20 no_e3_evidence.

## What is measured

- **Positive control:** an archived generated candidate that is a copy of the developer fix for its bug. If the fix lies wholly inside the method that the candidate replaces, the copy must pass the tests.
- **Occurrence:** one archived evaluation entry (one of the up to 10 outputs per bug and configuration). **Unique candidate:** one distinct text per bug and configuration (or per bug, for the artifact total).
- **Archived failure:** compile is False or test is False. RepairBench and RepairLLaMA GitBug-Java do not record compile results, so there every failure is listed as a test failure.
- **Identity levels** (cumulative):
  - L1 text: the same token sequence once comments and whitespace are removed; string literals are kept verbatim;
  - L2 AST: L1, or the same javac AST fingerprint (`BatchMethodFingerprint`, which keeps annotations);
  - L3 rename: L2, or the same `BatchMethodNormalize` h_noann_alpha (annotations removed, locals and parameters renamed).
- **Scope:** Defects4J positive controls are restricted to the 483 bugs that `results/v4/single_function_audit` marks single_method_consistent. Excluded: Chart-23 (no_context), Collections-27 (no_context), Jsoup-15 (no_context), Jsoup-35 (no_context), JxPath-14 (changes_outside_method).
- **95% intervals** are Clopper-Pearson on occurrences. Occurrences of the same text in the same bug are not independent, so the intervals are too narrow; the bug and unique-candidate counts are given for that reason.
- The failure rate of fix copies is an upper bound on harness false rejection for this kind of patch. It is not a rate for all candidates, because fix copies are not a random sample.

## 1. Artifact totals

| Artifact | Level | Fix-copy occurrences archived failing (95% CI) | Compile / test failures | Bugs with copies / with failing copies | Unique candidates with a failing occurrence | of which every occurrence fails |
|---|---|---|---|---|---|---|
| repairllama_defects4j | L1_text | 201/1871 (10.7%; 9.4-12.2) | 156 / 45 | 196 / 56 | 133/1339 | 82 |
| repairllama_defects4j | L2_ast | 202/1882 (10.7%; 9.4-12.2) | 156 / 46 | 197 / 57 | 134/1346 | 83 |
| repairllama_defects4j | L3_rename | 203/1884 (10.8%; 9.4-12.3) | 157 / 46 | 197 / 58 | 135/1348 | 84 |
| repairllama_humanevaljava | L1_text | 440/2849 (15.4%; 14.1-16.8) | 268 / 172 | 120 / 98 | 303/1720 | 129 |
| repairllama_humanevaljava | L2_ast | 445/2890 (15.4%; 14.1-16.8) | 270 / 175 | 121 / 100 | 308/1744 | 129 |
| repairllama_humanevaljava | L3_rename | 463/3008 (15.4%; 14.1-16.7) | 280 / 183 | 122 / 101 | 318/1817 | 134 |
| repairllama_gitbugjava | L1_text | 0/585 (0.0%; 0.0-0.6) | 0 / 0 | 23 / 0 | 0/163 | 0 |
| repairllama_gitbugjava | L2_ast | 0/585 (0.0%; 0.0-0.6) | 0 / 0 | 23 / 0 | 0/163 | 0 |
| repairllama_gitbugjava | L3_rename | 0/585 (0.0%; 0.0-0.6) | 0 / 0 | 23 / 0 | 0/163 | 0 |
| repairbench_gitbugjava | L1_text | 56/2197 (2.5%; 1.9-3.3) | 0 / 56 | 26 / 6 | 47/724 | 47 |
| repairbench_gitbugjava | L2_ast | 56/2197 (2.5%; 1.9-3.3) | 0 / 56 | 26 / 6 | 47/724 | 47 |
| repairbench_gitbugjava | L3_rename | 61/2209 (2.8%; 2.1-3.5) | 0 / 61 | 27 / 7 | 52/735 | 52 |

Defects4J without the single-method restriction (for comparison with the probe): L1_text 203/1873 (10.8%; 9.5-12.3); L2_ast 204/1884 (10.8%; 9.5-12.3); L3_rename 205/1886 (10.9%; 9.5-12.4).

RepairLLaMA's own flags on the failing copies: repairllama_defects4j 0 of 201 failing L1 copies carry exact_match or ast_match = True (passing copies: 1670 of 1670); repairllama_humanevaljava 0 of 440 failing L1 copies carry exact_match or ast_match = True (passing copies: 2409 of 2409); repairllama_gitbugjava 0 of 0 failing L1 copies carry exact_match or ast_match = True (passing copies: 585 of 585); repairbench_gitbugjava 0 of 56 failing L1 copies carry exact_match or ast_match = True (passing copies: 2129 of 2141).

## 2. Per configuration (L1 text identity; L3 in the last column)

### repairllama_defects4j

| Configuration | Fix-copy occurrences failing (95% CI) | Compile / test | Bugs with failing copies | Unique failing / unique copies | Byte-identical outputs with pass and fail verdicts in one bug (all outputs; fix copies) | Byte-identical outputs that both compiled and failed to compile | L3: failing (95% CI) |
|---|---|---|---|---|---|---|---|
| IR1xOR4 | 2/4 (50.0%; 6.8-93.2) | 2 / 0 | 2 | 2/4 | 1; 0 | 77 | 2/4 (50.0%; 6.8-93.2) |
| IR1xOR3 | 12/29 (41.4%; 23.5-61.1) | 11 / 1 | 9 | 11/27 | 1; 1 | 54 | 12/29 (41.4%; 23.5-61.1) |
| GPT-3.5 | 52/156 (33.3%; 26.0-41.3) | 51 / 1 | 22 | 31/88 | 21; 13 | 255 | 52/159 (32.7%; 25.5-40.6) |
| GPT-4 | 88/273 (32.2%; 26.7-38.1) | 82 / 6 | 39 | 68/169 | 34; 23 | 201 | 88/273 (32.2%; 26.7-38.1) |
| IR1xOR1 | 7/47 (14.9%; 6.2-28.3) | 2 / 5 | 4 | 6/38 | 1; 1 | 1 | 7/49 (14.3%; 5.9-27.2) |
| CodeLlama zero-shot IR3 | 6/96 (6.2%; 2.3-13.1) | 0 / 6 | 6 | 6/95 | 0; 0 | 0 | 6/97 (6.2%; 2.3-13.0) |
| CodeLlama full FT | 8/164 (4.9%; 2.1-9.4) | 0 / 8 | 5 | 8/161 | 0; 0 | 0 | 8/164 (4.9%; 2.1-9.4) |
| CodeLlama zero-shot IR4 | 6/153 (3.9%; 1.5-8.3) | 0 / 6 | 3 | 6/153 | 0; 0 | 0 | 7/154 (4.5%; 1.8-9.1) |
| DeepSeek base | 5/148 (3.4%; 1.1-7.7) | 0 / 5 | 2 | 5/148 | 0; 0 | 0 | 5/148 (3.4%; 1.1-7.7) |
| IR2xOR2 | 4/163 (2.5%; 0.7-6.2) | 3 / 1 | 4 | 4/162 | 0; 0 | 0 | 5/164 (3.0%; 1.0-7.0) |
| RepairLLaMA IR4xOR2 | 4/175 (2.3%; 0.6-5.8) | 3 / 1 | 4 | 4/175 | 0; 0 | 0 | 4/176 (2.3%; 0.6-5.7) |
| DeepSeek full FT | 3/180 (1.7%; 0.4-4.8) | 0 / 3 | 3 | 3/180 | 0; 0 | 0 | 3/182 (1.7%; 0.3-4.7) |
| IR3xOR2 | 2/122 (1.6%; 0.2-5.8) | 2 / 0 | 2 | 2/121 | 0; 0 | 0 | 2/123 (1.6%; 0.2-5.8) |
| DeepSeek LoRA | 2/161 (1.2%; 0.1-4.4) | 0 / 2 | 2 | 2/161 | 0; 0 | 0 | 2/162 (1.2%; 0.1-4.4) |

Contradiction columns cover all bugs (no scope filter). With leading/trailing whitespace ignored the pass/fail counts are: GPT-3.5 21 (13 fix copies), GPT-4 35 (23 fix copies), IR1xOR1 1 (1 fix copies), IR1xOR3 1 (1 fix copies), IR1xOR4 1 (0 fix copies).

### repairllama_humanevaljava

| Configuration | Fix-copy occurrences failing (95% CI) | Compile / test | Bugs with failing copies | Unique failing / unique copies | Byte-identical outputs with pass and fail verdicts in one bug (all outputs; fix copies) | Byte-identical outputs that both compiled and failed to compile | L3: failing (95% CI) |
|---|---|---|---|---|---|---|---|
| IR1xOR4 | 6/8 (75.0%; 34.9-96.8) | 6 / 0 | 5 | 5/5 | 2; 2 | 13 | 6/8 (75.0%; 34.9-96.8) |
| GPT-3.5 | 151/386 (39.1%; 34.2-44.2) | 110 / 41 | 53 | 107/187 | 94; 59 | 134 | 162/409 (39.6%; 34.8-44.5) |
| IR1xOR3 | 18/48 (37.5%; 23.9-52.6) | 14 / 4 | 16 | 17/35 | 8; 5 | 21 | 18/48 (37.5%; 23.9-52.6) |
| IR2xOR2 | 48/175 (27.4%; 21.0-34.7) | 24 / 24 | 43 | 48/174 | 1; 1 | 1 | 48/188 (25.5%; 19.5-32.4) |
| IR3xOR2 | 45/178 (25.3%; 19.1-32.3) | 29 / 16 | 34 | 45/177 | 2; 1 | 2 | 49/189 (25.9%; 19.8-32.8) |
| RepairLLaMA IR4xOR2 | 42/173 (24.3%; 18.1-31.4) | 21 / 21 | 34 | 42/173 | 0; 0 | 0 | 43/184 (23.4%; 17.5-30.2) |
| IR1xOR1 | 30/133 (22.6%; 15.8-30.6) | 22 / 8 | 24 | 26/98 | 0; 0 | 1 | 33/139 (23.7%; 16.9-31.7) |
| GPT-4 | 100/486 (20.6%; 17.1-24.4) | 42 / 58 | 53 | 79/245 | 69; 45 | 29 | 104/517 (20.1%; 16.7-23.8) |
| CodeLlama full FT | 0/217 (0.0%; 0.0-1.7) | 0 / 0 | 0 | 0/217 | 0; 0 | 0 | 0/226 (0.0%; 0.0-1.6) |
| DeepSeek LoRA | 0/227 (0.0%; 0.0-1.6) | 0 / 0 | 0 | 0/227 | 0; 0 | 0 | 0/239 (0.0%; 0.0-1.5) |
| DeepSeek base | 0/225 (0.0%; 0.0-1.6) | 0 / 0 | 0 | 0/225 | 0; 0 | 0 | 0/240 (0.0%; 0.0-1.5) |
| CodeLlama zero-shot IR4 | 0/169 (0.0%; 0.0-2.2) | 0 / 0 | 0 | 0/169 | 0; 0 | 0 | 0/175 (0.0%; 0.0-2.1) |
| DeepSeek full FT | 0/265 (0.0%; 0.0-1.4) | 0 / 0 | 0 | 0/265 | 0; 0 | 0 | 0/276 (0.0%; 0.0-1.3) |
| CodeLlama zero-shot IR3 | 0/159 (0.0%; 0.0-2.3) | 0 / 0 | 0 | 0/158 | 0; 0 | 0 | 0/170 (0.0%; 0.0-2.1) |

Contradiction columns cover all bugs (no scope filter). With leading/trailing whitespace ignored the pass/fail counts are: GPT-3.5 94 (59 fix copies), GPT-4 70 (46 fix copies), IR1xOR1 11 (8 fix copies), IR1xOR3 8 (5 fix copies), IR1xOR4 2 (2 fix copies), IR2xOR2 1 (1 fix copies), IR3xOR2 2 (1 fix copies).

### repairllama_gitbugjava

| Configuration | Fix-copy occurrences failing (95% CI) | Compile / test | Bugs with failing copies | Unique failing / unique copies | Byte-identical outputs with pass and fail verdicts in one bug (all outputs; fix copies) | Byte-identical outputs that both compiled and failed to compile | L3: failing (95% CI) |
|---|---|---|---|---|---|---|---|
| IR1xOR1 | 0/42 (0.0%; 0.0-8.4) | 0 / 0 | 0 | 0/4 | 0; 0 | 0 | 0/42 (0.0%; 0.0-8.4) |
| GPT-4 | 0/24 (0.0%; 0.0-14.2) | 0 / 0 | 0 | 0/11 | 0; 0 | 0 | 0/24 (0.0%; 0.0-14.2) |
| CodeLlama full FT | 0/25 (0.0%; 0.0-13.7) | 0 / 0 | 0 | 0/25 | 0; 0 | 0 | 0/25 (0.0%; 0.0-13.7) |
| IR2xOR2 | 0/126 (0.0%; 0.0-2.9) | 0 / 0 | 0 | 0/21 | 0; 0 | 0 | 0/126 (0.0%; 0.0-2.9) |
| DeepSeek LoRA | 0/14 (0.0%; 0.0-23.2) | 0 / 0 | 0 | 0/14 | 0; 0 | 0 | 0/14 (0.0%; 0.0-23.2) |
| IR3xOR2 | 0/84 (0.0%; 0.0-4.3) | 0 / 0 | 0 | 0/14 | 0; 0 | 0 | 0/84 (0.0%; 0.0-4.3) |
| IR1xOR3 | 0/12 (0.0%; 0.0-26.5) | 0 / 0 | 0 | 0/1 | 0; 0 | 0 | 0/12 (0.0%; 0.0-26.5) |
| GPT-3.5 | 0/53 (0.0%; 0.0-6.7) | 0 / 0 | 0 | 0/11 | 0; 0 | 0 | 0/53 (0.0%; 0.0-6.7) |
| IR1xOR4 | 0/6 (0.0%; 0.0-45.9) | 0 / 0 | 0 | 0/1 | 0; 0 | 0 | 0/6 (0.0%; 0.0-45.9) |
| DeepSeek base | 0/15 (0.0%; 0.0-21.8) | 0 / 0 | 0 | 0/15 | 0; 0 | 0 | 0/15 (0.0%; 0.0-21.8) |
| CodeLlama zero-shot IR4 | 0/29 (0.0%; 0.0-11.9) | 0 / 0 | 0 | 0/29 | 0; 0 | 0 | 0/29 (0.0%; 0.0-11.9) |
| DeepSeek full FT | 0/20 (0.0%; 0.0-16.8) | 0 / 0 | 0 | 0/20 | 0; 0 | 0 | 0/20 (0.0%; 0.0-16.8) |
| CodeLlama zero-shot IR3 | 0/9 (0.0%; 0.0-33.6) | 0 / 0 | 0 | 0/9 | 0; 0 | 0 | 0/9 (0.0%; 0.0-33.6) |
| RepairLLaMA IR4xOR2 | 0/126 (0.0%; 0.0-2.9) | 0 / 0 | 0 | 0/21 | 0; 0 | 0 | 0/126 (0.0%; 0.0-2.9) |

Contradiction columns cover all bugs (no scope filter). With leading/trailing whitespace ignored the pass/fail counts are: none.

### repairbench_gitbugjava

| Configuration | Fix-copy occurrences failing (95% CI) | Compile / test | Bugs with failing copies | Unique failing / unique copies | Byte-identical outputs with pass and fail verdicts in one bug (all outputs; fix copies) | Byte-identical outputs that both compiled and failed to compile | L3: failing (95% CI) |
|---|---|---|---|---|---|---|---|
| o4-mini-2025-04-16-high | 13/55 (23.6%; 13.2-37.0) | 0 / 13 | 4 | 11/34 | 0; 0 | 0 | 17/59 (28.8%; 17.8-42.1) |
| gpt-4.1-2025-04-14 | 8/65 (12.3%; 5.5-22.8) | 0 / 8 | 3 | 7/35 | 0; 0 | 0 | 8/66 (12.1%; 5.4-22.5) |
| deepseek-v3-0324 | 11/104 (10.6%; 5.4-18.1) | 0 / 11 | 2 | 6/30 | 0; 0 | 0 | 11/104 (10.6%; 5.4-18.1) |
| gemini-2.5-pro-preview-03-25 | 6/69 (8.7%; 3.3-18.0) | 0 / 6 | 2 | 6/61 | 0; 0 | 0 | 7/70 (10.0%; 4.1-19.5) |
| claude-3-7-sonnet-20250219 | 7/95 (7.4%; 3.0-14.6) | 0 / 7 | 2 | 6/32 | 0; 0 | 0 | 7/95 (7.4%; 3.0-14.6) |
| llama-4-maverick | 4/58 (6.9%; 1.9-16.7) | 0 / 4 | 1 | 4/31 | 0; 0 | 0 | 4/58 (6.9%; 1.9-16.7) |
| mistral-small-2503 | 2/42 (4.8%; 0.6-16.2) | 0 / 2 | 1 | 2/16 | 0; 0 | 0 | 2/42 (4.8%; 0.6-16.2) |
| gemini-2.5-flash-preview-05-20 | 3/78 (3.9%; 0.8-10.8) | 0 / 3 | 1 | 3/68 | 0; 0 | 0 | 3/78 (3.9%; 0.8-10.8) |
| mistral-medium-2505 | 1/62 (1.6%; 0.0-8.7) | 0 / 1 | 1 | 1/16 | 0; 0 | 0 | 1/62 (1.6%; 0.0-8.7) |
| o3-mini-2025-01-31-high | 1/83 (1.2%; 0.0-6.5) | 0 / 1 | 1 | 1/64 | 0; 0 | 0 | 1/85 (1.2%; 0.0-6.4) |
| deepseek-r1-distill-llama-70b | 0/52 (0.0%; 0.0-6.9) | 0 / 0 | 0 | 0/30 | 0; 0 | 0 | 0/52 (0.0%; 0.0-6.9) |
| grok-2-1212 | 0/52 (0.0%; 0.0-6.9) | 0 / 0 | 0 | 0/37 | 0; 0 | 0 | 0/52 (0.0%; 0.0-6.9) |
| command-a | 0/50 (0.0%; 0.0-7.1) | 0 / 0 | 0 | 0/29 | 0; 0 | 0 | 0/51 (0.0%; 0.0-7.0) |
| magistral-medium-2506 | 0/61 (0.0%; 0.0-5.9) | 0 / 0 | 0 | 0/26 | 0; 0 | 0 | 0/61 (0.0%; 0.0-5.9) |
| qwen-2.5-coder-32b-instruct | 0/49 (0.0%; 0.0-7.2) | 0 / 0 | 0 | 0/32 | 0; 0 | 0 | 0/49 (0.0%; 0.0-7.2) |
| claude-3-5-sonnet-20240620 | 0/77 (0.0%; 0.0-4.7) | 0 / 0 | 0 | 0/16 | 0; 0 | 0 | 0/77 (0.0%; 0.0-4.7) |
| qwen-2.5-72b-instruct | 0/50 (0.0%; 0.0-7.1) | 0 / 0 | 0 | 0/23 | 0; 0 | 0 | 0/50 (0.0%; 0.0-7.1) |
| gemini-1.5-pro-002 | 0/74 (0.0%; 0.0-4.9) | 0 / 0 | 0 | 0/9 | 0; 0 | 0 | 0/74 (0.0%; 0.0-4.9) |
| deepseek-r1-distill-qwen-32b | 0/53 (0.0%; 0.0-6.7) | 0 / 0 | 0 | 0/38 | 0; 0 | 0 | 0/53 (0.0%; 0.0-6.7) |
| deepseek-r1 | 0/110 (0.0%; 0.0-3.3) | 0 / 0 | 0 | 0/31 | 0; 0 | 0 | 0/111 (0.0%; 0.0-3.3) |
| llama-3.1-405b-instruct | 0/66 (0.0%; 0.0-5.4) | 0 / 0 | 0 | 0/36 | 0; 0 | 0 | 0/67 (0.0%; 0.0-5.4) |
| llama-3.1-nemotron-70b-instruct | 0/25 (0.0%; 0.0-13.7) | 0 / 0 | 0 | 0/19 | 0; 0 | 0 | 0/25 (0.0%; 0.0-13.7) |
| llama-3.3-70b-instruct | 0/51 (0.0%; 0.0-7.0) | 0 / 0 | 0 | 0/30 | 0; 0 | 0 | 0/51 (0.0%; 0.0-7.0) |
| deepseek-v2.5 | 0/63 (0.0%; 0.0-5.7) | 0 / 0 | 0 | 0/42 | 0; 0 | 0 | 0/63 (0.0%; 0.0-5.7) |
| claude-3-5-sonnet-20241022 | 0/85 (0.0%; 0.0-4.2) | 0 / 0 | 0 | 0/24 | 0; 0 | 0 | 0/85 (0.0%; 0.0-4.2) |
| gemini-1.5-pro-001 | 0/86 (0.0%; 0.0-4.2) | 0 / 0 | 0 | 0/21 | 0; 0 | 0 | 0/86 (0.0%; 0.0-4.2) |
| gpt-4o-2024-08-06 | 0/69 (0.0%; 0.0-5.2) | 0 / 0 | 0 | 0/52 | 0; 0 | 0 | 0/69 (0.0%; 0.0-5.2) |
| gemma-3-27b-it | 0/52 (0.0%; 0.0-6.9) | 0 / 0 | 0 | 0/6 | 0; 0 | 0 | 0/52 (0.0%; 0.0-6.9) |
| codestral-2405 | 0/31 (0.0%; 0.0-11.2) | 0 / 0 | 0 | 0/23 | 0; 0 | 0 | 0/32 (0.0%; 0.0-10.9) |
| mistral-large-2411 | 0/57 (0.0%; 0.0-6.3) | 0 / 0 | 0 | 0/31 | 0; 0 | 0 | 0/57 (0.0%; 0.0-6.3) |
| codestral-2501 | 0/58 (0.0%; 0.0-6.2) | 0 / 0 | 0 | 0/20 | 0; 0 | 0 | 0/58 (0.0%; 0.0-6.2) |
| mistral-large-2407 | 0/58 (0.0%; 0.0-6.2) | 0 / 0 | 0 | 0/34 | 0; 0 | 0 | 0/58 (0.0%; 0.0-6.2) |
| gpt-4o-2024-11-20 | 0/66 (0.0%; 0.0-5.4) | 0 / 0 | 0 | 0/53 | 0; 0 | 0 | 0/66 (0.0%; 0.0-5.4) |
| deepseek-v3 | 0/64 (0.0%; 0.0-5.6) | 0 / 0 | 0 | 0/19 | 0; 0 | 0 | 0/64 (0.0%; 0.0-5.6) |
| gemini-2.0-flash-001 | 0/27 (0.0%; 0.0-12.8) | 0 / 0 | 0 | 0/5 | 0; 0 | 0 | 0/27 (0.0%; 0.0-12.8) |

Contradiction columns cover all bugs (no scope filter). With leading/trailing whitespace ignored the pass/fail counts are: none.

## 3. Is the error differential between configurations?

Each configuration against all other configurations, restricted to the bugs where both produced fix copies (L1), with a Cochran-Mantel-Haenszel test stratified by bug. This removes differences in bug mix.

### repairllama_defects4j

| Configuration | Shared bugs | Its failure rate on shared bugs | Other configurations on the same bugs | MH odds ratio | p |
|---|---|---|---|---|---|
| IR1xOR4 | 4 | 2/4 (50.0%; 6.8-93.2) | 6/35 (17.1%; 6.6-33.7) | inf | 0.237 |
| IR1xOR3 | 23 | 12/29 (41.4%; 23.5-61.1) | 57/350 (16.3%; 12.6-20.6) | 8.302 | 0.000112 |
| GPT-3.5 | 36 | 52/156 (33.3%; 26.0-41.3) | 85/678 (12.5%; 10.1-15.3) | 4.459 | 2.03e-10 |
| GPT-4 | 62 | 85/260 (32.7%; 27.0-38.8) | 84/826 (10.2%; 8.2-12.4) | 6.628 | 4.87e-23 |
| IR1xOR1 | 32 | 7/47 (14.9%; 6.2-28.3) | 67/522 (12.8%; 10.1-16.0) | 0.988 | 0.835 |
| CodeLlama zero-shot IR3 | 75 | 6/95 (6.3%; 2.4-13.2) | 148/1083 (13.7%; 11.7-15.9) | 0.591 | 0.426 |
| CodeLlama full FT | 88 | 8/164 (4.9%; 2.1-9.4) | 158/1235 (12.8%; 11.0-14.8) | 0.375 | 0.0119 |
| CodeLlama zero-shot IR4 | 60 | 6/151 (4.0%; 1.5-8.5) | 129/1008 (12.8%; 10.8-15.0) | 0.39 | 0.0474 |
| DeepSeek base | 84 | 5/140 (3.6%; 1.2-8.1) | 160/1184 (13.5%; 11.6-15.6) | 0.177 | 0.000352 |
| IR2xOR2 | 117 | 4/155 (2.6%; 0.7-6.5) | 174/1420 (12.2%; 10.6-14.1) | 0.235 | 0.0104 |
| RepairLLaMA IR4xOR2 | 126 | 4/173 (2.3%; 0.6-5.8) | 179/1471 (12.2%; 10.5-14.0) | 0.185 | 0.000915 |
| IR3xOR2 | 86 | 2/122 (1.6%; 0.2-5.8) | 150/1221 (12.3%; 10.5-14.3) | 0.175 | 0.0116 |
| DeepSeek LoRA | 105 | 2/156 (1.3%; 0.2-4.5) | 152/1301 (11.7%; 10.0-13.6) | 0.098 | 0.00107 |
| DeepSeek full FT | 113 | 2/172 (1.2%; 0.1-4.1) | 170/1337 (12.7%; 11.0-14.6) | 0.066 | 1.23e-05 |

### repairllama_humanevaljava

| Configuration | Shared bugs | Its failure rate on shared bugs | Other configurations on the same bugs | MH odds ratio | p |
|---|---|---|---|---|---|
| IR1xOR4 | 5 | 6/8 (75.0%; 34.9-96.8) | 43/229 (18.8%; 13.9-24.4) | 9.312 | 0.00101 |
| GPT-3.5 | 62 | 151/385 (39.2%; 34.3-44.3) | 223/1951 (11.4%; 10.1-12.9) | 4.94 | 2.46e-39 |
| IR1xOR3 | 30 | 18/48 (37.5%; 23.9-52.6) | 144/1003 (14.4%; 12.2-16.7) | 4.001 | 1.26e-05 |
| IR2xOR2 | 92 | 48/175 (27.4%; 21.0-34.7) | 370/2515 (14.7%; 13.4-16.2) | 2.221 | 8.83e-06 |
| IR3xOR2 | 77 | 45/178 (25.3%; 19.1-32.3) | 347/2348 (14.8%; 13.4-16.3) | 2.076 | 0.000134 |
| RepairLLaMA IR4xOR2 | 91 | 42/173 (24.3%; 18.1-31.4) | 371/2502 (14.8%; 13.5-16.3) | 1.823 | 0.00206 |
| IR1xOR1 | 63 | 30/133 (22.6%; 15.8-30.6) | 326/2020 (16.1%; 14.6-17.8) | 1.432 | 0.14 |
| GPT-4 | 74 | 98/479 (20.5%; 16.9-24.3) | 294/2009 (14.6%; 13.1-16.3) | 1.498 | 0.0032 |

### repairbench_gitbugjava

| Configuration | Shared bugs | Its failure rate on shared bugs | Other configurations on the same bugs | MH odds ratio | p |
|---|---|---|---|---|---|
| o4-mini-2025-04-16-high | 14 | 13/54 (24.1%; 13.5-37.6) | 31/1625 (1.9%; 1.3-2.7) | inf | 5.29e-24 |
| gpt-4.1-2025-04-14 | 10 | 8/65 (12.3%; 5.5-22.8) | 36/1312 (2.7%; 1.9-3.8) | 3.076 | 0.0866 |
| deepseek-v3-0324 | 15 | 11/104 (10.6%; 5.4-18.1) | 41/1957 (2.1%; 1.5-2.8) | 8.449 | 0.000911 |
| gemini-2.5-pro-preview-03-25 | 12 | 6/68 (8.8%; 3.3-18.2) | 43/1545 (2.8%; 2.0-3.7) | 10.425 | 0.035 |
| claude-3-7-sonnet-20250219 | 15 | 7/95 (7.4%; 3.0-14.6) | 45/1987 (2.3%; 1.7-3.0) | 3.615 | 0.0747 |
| llama-4-maverick | 9 | 4/58 (6.9%; 1.9-16.7) | 36/1610 (2.2%; 1.6-3.1) | 4.756 | 0.331 |
| mistral-small-2503 | 9 | 2/42 (4.8%; 0.6-16.2) | 12/1686 (0.7%; 0.4-1.2) | 6.665 | 0.0798 |
| gemini-2.5-flash-preview-05-20 | 16 | 3/75 (4.0%; 0.8-11.2) | 20/2027 (1.0%; 0.6-1.5) | 5.138 | 0.0788 |
| mistral-medium-2505 | 10 | 1/62 (1.6%; 0.0-8.7) | 19/1594 (1.2%; 0.7-1.9) | 1.608 | 0.827 |
| o3-mini-2025-01-31-high | 14 | 1/83 (1.2%; 0.0-6.5) | 46/1968 (2.3%; 1.7-3.1) | 0.095 | 0.0358 |

Pairs compared directly (bugs where both configurations produced an L1 fix copy):

| Benchmark | Pair | Shared bugs | First config failing | Second config failing | MH odds ratio | p |
|---|---|---|---|---|---|---|
| defects4j | GPT-4 vs RepairLLaMA IR4xOR2 | 51 | 77/230 (33.5%; 27.4-40.0) | 2/79 (2.5%; 0.3-8.8) | 26.057 | 1.1e-07 |
| defects4j | GPT-3.5 vs RepairLLaMA IR4xOR2 | 32 | 47/144 (32.6%; 25.1-40.9) | 3/55 (5.5%; 1.1-15.1) | 78.018 | 1.84e-05 |
| defects4j | GPT-4 vs DeepSeek LoRA | 44 | 72/219 (32.9%; 26.7-39.5) | 1/70 (1.4%; 0.0-7.7) | 79.502 | 1.03e-08 |
| defects4j | GPT-3.5 vs DeepSeek LoRA | 29 | 40/128 (31.2%; 23.4-40.0) | 1/57 (1.8%; 0.0-9.4) | 15.463 | 1.04e-05 |
| defects4j | GPT-4 vs GPT-3.5 | 28 | 62/170 (36.5%; 29.2-44.2) | 48/138 (34.8%; 26.9-43.4) | 1.4 | 0.303 |
| humanevaljava | GPT-4 vs RepairLLaMA IR4xOR2 | 66 | 86/433 (19.9%; 16.2-23.9) | 31/133 (23.3%; 16.4-31.4) | 0.893 | 0.757 |
| humanevaljava | GPT-3.5 vs RepairLLaMA IR4xOR2 | 56 | 146/364 (40.1%; 35.0-45.4) | 29/128 (22.7%; 15.7-30.9) | 2.54 | 0.000103 |
| humanevaljava | GPT-4 vs DeepSeek LoRA | 68 | 92/448 (20.5%; 16.9-24.6) | 0/174 (0.0%; 0.0-2.1) | inf | 5.12e-10 |
| humanevaljava | GPT-3.5 vs DeepSeek LoRA | 59 | 144/370 (38.9%; 33.9-44.1) | 0/166 (0.0%; 0.0-2.2) | inf | 6.15e-21 |
| humanevaljava | GPT-4 vs GPT-3.5 | 57 | 84/423 (19.9%; 16.2-24.0) | 146/373 (39.1%; 34.2-44.3) | 0.379 | 3.48e-09 |

## 4. Validation by existing re-execution (retrospective)

### Defects4J fix re-run (R)

R re-executed the 80 archived-incorrect candidates that sit in a rename-aware class with a fix-equivalent member (two repetitions, controls).

| Subset | Candidates | Bugs | Not reproduced | Reproduced | Compile failure | Unresolved placement | Not reproduced / resolved (95% CI) |
|---|---|---|---|---|---|---|---|
| all 80 | 80 | 38 | 68 | 2 | 1 | 9 | 68/71 (95.8%; 88.1-99.1) |
| direct identity level 1 | 78 | 36 | 67 | 2 | 0 | 9 | 67/69 (97.1%; 89.9-99.7) |
| direct identity level 2 | 1 | 1 | 1 | 0 | 0 | 0 | 1/1 (100.0%; 2.5-100.0) |
| direct identity level 3 | 1 | 1 | 0 | 0 | 1 | 0 | 0/1 (0.0%; 0.0-97.5) |
| in positive-control scope, L1-L2 | 77 | 36 | 68 | 0 | 0 | 9 | 68/68 (100.0%; 94.7-100.0) |
| in positive-control scope, L1-L3 | 78 | 37 | 68 | 0 | 1 | 9 | 68/69 (98.6%; 92.2-100.0) |

Candidates that were not 'not reproduced': JacksonDatabind-57 unresolved_placement_or_repetition (level 1, GPT-3.5); JxPath-14 controlled_trigger_failure (level 1, RepairLLaMA IR4xOR2); JacksonDatabind-57 unresolved_placement_or_repetition (level 1, RepairLLaMA IR4xOR2); Chart-24 unresolved_placement_or_repetition (level 1, GPT-4); Chart-24 unresolved_placement_or_repetition (level 1, GPT-3.5, GPT-4, IR1xOR1, IR1xOR3); Cli-24 unresolved_placement_or_repetition (level 1, GPT-4); Chart-24 unresolved_placement_or_repetition (level 1, GPT-4); Collections-26 compile_command_failed_twice (level 3, IR2xOR2); JxPath-14 controlled_trigger_failure (level 1, IR2xOR2); JacksonDatabind-57 unresolved_placement_or_repetition (level 1, IR2xOR2); Chart-24 unresolved_placement_or_repetition (level 1, RepairLLaMA IR4xOR2); Cli-24 unresolved_placement_or_repetition (level 1, GPT-4).

Failing occurrences behind the 80 re-run candidates, by configuration and R status: DeepSeek base {'admissible_triggers_pass_semantics_unknown': 5}; DeepSeek full FT {'admissible_triggers_pass_semantics_unknown': 3}; DeepSeek LoRA {'admissible_triggers_pass_semantics_unknown': 2}; GPT-3.5 {'admissible_triggers_pass_semantics_unknown': 12, 'unresolved_placement_or_repetition': 3}; GPT-4 {'admissible_triggers_pass_semantics_unknown': 36, 'unresolved_placement_or_repetition': 5}; IR1xOR1 {'unresolved_placement_or_repetition': 1}; IR1xOR3 {'unresolved_placement_or_repetition': 1}; IR2xOR2 {'compile_command_failed_twice': 1, 'admissible_triggers_pass_semantics_unknown': 1, 'controlled_trigger_failure': 1, 'unresolved_placement_or_repetition': 1}; RepairLLaMA IR4xOR2 {'controlled_trigger_failure': 1, 'unresolved_placement_or_repetition': 2, 'admissible_triggers_pass_semantics_unknown': 2}; CodeLlama zero-shot IR3 {'admissible_triggers_pass_semantics_unknown': 3}; CodeLlama zero-shot IR4 {'admissible_triggers_pass_semantics_unknown': 7}; CodeLlama full FT {'admissible_triggers_pass_semantics_unknown': 8}.

Re-execution coverage of every in-scope failing Defects4J fix copy (L3, occurrences; exact text means the same obscand id was re-run by R or by the conflict census):

- exact_text:admissible_triggers_pass_semantics_unknown: 79
- exact_text:census:admissible_triggers_pass_semantics_unknown: 60
- only_other_copy_text_in_bug:admissible_triggers_pass_semantics_unknown+census:admissible_triggers_pass_semantics_unknown: 15
- exact_text:census:unresolved_placement_or_repetition: 14
- exact_text:unresolved_placement_or_repetition: 13
- only_other_copy_text_in_bug:census:admissible_triggers_pass_semantics_unknown: 7
- no_reexecution: 7
- only_other_copy_text_in_bug:admissible_triggers_pass_semantics_unknown: 5
- only_other_copy_text_in_bug:unresolved_placement_or_repetition: 1
- only_other_copy_text_in_bug:census:unresolved_placement_or_repetition+unresolved_placement_or_repetition: 1
- exact_text:compile_command_failed_twice: 1

### HumanEval-Java E3 (retrospective, not a prediction)

Unique failing fix-copy candidates (L3): 318. Exact text executed in E3 and passed every test: 185/185 (100.0%; 98.0-100.0).

- exact_text_executed:admissible_all_tests_pass: 185
- only_other_copy_text_in_bug:admissible_all_tests_pass: 113
- no_e3_evidence: 20

Occurrence-level coverage (L3):

- exact_text:admissible_all_tests_pass: 326
- only_other_copy_text_in_bug:admissible_all_tests_pass: 115
- no_reexecution: 22

## 5. Effect on the published RepairLLaMA counts

Counts are bugs, inside the paper's scope (single-function bugs minus Math-28, Math-44, JacksonDatabind-82; Defects4J additionally needs a single_method_consistent fix for a copy to count). 'Computed' applies the paper's union logic to the raw files. A bug is added when the configuration has an archived failing fix copy for it and no plausible (or semantic) candidate. 'Validated' adds only bugs whose failing copy text was re-executed and passed (R, census or E3). 'Validated or equivalent' also adds a bug when the failing copy's own text was not re-executed but every re-executed copy text of that bug passed. The L1-L3 columns are upper bounds: they assume every flagged failure is spurious. The validated columns are lower bounds, and because re-execution covered configurations unevenly (E3 and the census only ran archived-unknown records), orderings under the validated columns can move for reasons of coverage alone.

### defects4j

| Configuration | Semantic: published / computed | + L1 | + L2 | + L3 | + validated | + validated or equivalent | Plausible: published / computed | + L1 | + L3 | + validated | + validated or equivalent | Failing fix-copy candidates (L1) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DeepSeek base | 104 / 104 | 2 | 2 | 2 | 2 | 2 | 147 / 147 | 2 | 2 | 2 | 2 | 5 |
| DeepSeek full FT | 138 / 138 | 1 | 1 | 1 | 1 | 1 | 185 / 185 | 1 | 1 | 1 | 1 | 3 |
| DeepSeek LoRA | 128 / 128 | 0 | 0 | 0 | 0 | 0 | 181 / 181 | 0 | 0 | 0 | 0 | 2 |
| GPT-3.5 | 45 / 45 | 5 | 5 | 5 | 3 | 4 | 71 / 71 | 5 | 5 | 3 | 4 | 31 |
| GPT-4 | 72 / 72 | 8 | 8 | 8 | 7 | 7 | 119 / 119 | 4 | 4 | 4 | 4 | 68 |
| IR1xOR1 | 45 / 45 | 2 | 2 | 2 | 2 | 2 | 79 / 79 | 2 | 2 | 2 | 2 | 6 |
| IR1xOR3 | 24 / 24 | 6 | 6 | 6 | 3 | 4 | 41 / 41 | 6 | 6 | 3 | 4 | 11 |
| IR1xOR4 | 3 / 3 | 2 | 2 | 2 | 2 | 2 | 12 / 12 | 2 | 2 | 2 | 2 | 2 |
| IR2xOR2 | 139 / 139 | 3 | 3 | 3 | 2 | 2 | 198 / 198 | 2 | 2 | 2 | 2 | 4 |
| IR3xOR2 | 102 / 102 | 2 | 2 | 2 | 0 | 0 | 153 / 153 | 1 | 1 | 0 | 0 | 2 |
| RepairLLaMA IR4xOR2 | 144 / 144 | 3 | 3 | 3 | 2 | 2 | 195 / 195 | 3 | 3 | 2 | 2 | 4 |
| CodeLlama zero-shot IR3 | 83 / 83 | 6 | 6 | 6 | 4 | 6 | 131 / 131 | 6 | 6 | 4 | 6 | 6 |
| CodeLlama zero-shot IR4 | 69 / 69 | 3 | 4 | 4 | 4 | 4 | 107 / 107 | 3 | 4 | 4 | 4 | 6 |
| CodeLlama full FT | 98 / 98 | 5 | 5 | 5 | 5 | 5 | 146 / 146 | 5 | 5 | 5 | 5 | 8 |

### humanevaljava

| Configuration | Semantic: published / computed | + L1 | + L2 | + L3 | + validated | + validated or equivalent | Plausible: published / computed | + L1 | + L3 | + validated | + validated or equivalent | Failing fix-copy candidates (L1) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DeepSeek base | 110 / 110 | 0 | 0 | 0 | 0 | 0 | 113 / 113 | 0 | 0 | 0 | 0 | 0 |
| DeepSeek full FT | 119 / 119 | 0 | 0 | 0 | 0 | 0 | 129 / 129 | 0 | 0 | 0 | 0 | 0 |
| DeepSeek LoRA | 124 / 124 | 0 | 0 | 0 | 0 | 0 | 134 / 134 | 0 | 0 | 0 | 0 | 0 |
| GPT-3.5 | 97 / 97 | 1 | 1 | 1 | 1 | 1 | 107 / 107 | 1 | 1 | 1 | 1 | 107 |
| GPT-4 | 116 / 116 | 4 | 4 | 4 | 2 | 3 | 124 / 124 | 2 | 2 | 1 | 2 | 79 |
| IR1xOR1 | 72 / 72 | 6 | 6 | 7 | 7 | 7 | 78 / 78 | 6 | 7 | 7 | 7 | 26 |
| IR1xOR3 | 37 / 37 | 9 | 9 | 9 | 9 | 9 | 39 / 39 | 9 | 9 | 9 | 9 | 17 |
| IR1xOR4 | 4 / 4 | 3 | 3 | 3 | 3 | 3 | 5 / 5 | 3 | 3 | 3 | 3 | 5 |
| IR2xOR2 | 108 / 108 | 9 | 9 | 9 | 8 | 8 | 118 / 118 | 8 | 8 | 7 | 7 | 48 |
| IR3xOR2 | 99 / 99 | 3 | 3 | 3 | 3 | 3 | 103 / 103 | 3 | 3 | 3 | 3 | 45 |
| RepairLLaMA IR4xOR2 | 109 / 109 | 8 | 8 | 8 | 0 | 5 | 118 / 118 | 6 | 6 | 0 | 4 | 42 |
| CodeLlama zero-shot IR3 | 103 / 103 | 0 | 0 | 0 | 0 | 0 | 107 / 107 | 0 | 0 | 0 | 0 | 0 |
| CodeLlama zero-shot IR4 | 91 / 91 | 0 | 0 | 0 | 0 | 0 | 95 / 95 | 0 | 0 | 0 | 0 | 0 |
| CodeLlama full FT | 100 / 100 | 0 | 0 | 0 | 0 | 0 | 109 / 109 | 0 | 0 | 0 | 0 | 0 |

### gitbugjava

| Configuration | Semantic: published / computed | + L1 | + L2 | + L3 | + validated | + validated or equivalent | Plausible: published / computed | + L1 | + L3 | + validated | + validated or equivalent | Failing fix-copy candidates (L1) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DeepSeek base | 13 / 13 | 0 | 0 | 0 | 0 | 0 | 21 / 21 | 0 | 0 | 0 | 0 | 0 |
| DeepSeek full FT | 19 / 18 | 0 | 0 | 0 | 0 | 0 | 26 / 26 | 0 | 0 | 0 | 0 | 0 |
| DeepSeek LoRA | 13 / 13 | 0 | 0 | 0 | 0 | 0 | 19 / 19 | 0 | 0 | 0 | 0 | 0 |
| GPT-3.5 | 8 / 8 | 0 | 0 | 0 | 0 | 0 | 9 / 9 | 0 | 0 | 0 | 0 | 0 |
| GPT-4 | 10 / 10 | 0 | 0 | 0 | 0 | 0 | 14 / 14 | 0 | 0 | 0 | 0 | 0 |
| IR1xOR1 | 4 / 4 | 0 | 0 | 0 | 0 | 0 | 10 / 10 | 0 | 0 | 0 | 0 | 0 |
| IR1xOR3 | 1 / 1 | 0 | 0 | 0 | 0 | 0 | 6 / 6 | 0 | 0 | 0 | 0 | 0 |
| IR1xOR4 | 1 / 1 | 0 | 0 | 0 | 0 | 0 | 1 / 1 | 0 | 0 | 0 | 0 | 0 |
| IR2xOR2 | 19 / 19 | 0 | 0 | 0 | 0 | 0 | 23 / 23 | 0 | 0 | 0 | 0 | 0 |
| IR3xOR2 | 13 / 13 | 0 | 0 | 0 | 0 | 0 | 21 / 21 | 0 | 0 | 0 | 0 | 0 |
| RepairLLaMA IR4xOR2 | 20 / 20 | 0 | 0 | 0 | 0 | 0 | 25 / 25 | 0 | 0 | 0 | 0 | 0 |
| CodeLlama zero-shot IR3 | 12 / 12 | 0 | 0 | 0 | 0 | 0 | 17 / 17 | 0 | 0 | 0 | 0 | 0 |
| CodeLlama zero-shot IR4 | 13 / 13 | 0 | 0 | 0 | 0 | 0 | 19 / 19 | 0 | 0 | 0 | 0 | 0 |
| CodeLlama full FT | 13 / 13 | 0 | 0 | 0 | 0 | 0 | 21 / 21 | 0 | 0 | 0 | 0 | 0 |

### Pairwise orderings that change (all 91 pairs per benchmark; computed counts)

| Benchmark | Metric : scenario | Pair | Before | After | Change | Same published table |
|---|---|---|---|---|---|---|
| defects4j | semantic:L1_text | IR1xOR1 vs GPT-3.5 | 45 vs 45 | 47 vs 50 | tie_broken | none |
| defects4j | semantic:L2_ast | IR1xOR1 vs GPT-3.5 | 45 vs 45 | 47 vs 50 | tie_broken | none |
| defects4j | semantic:L3_rename | IR1xOR1 vs GPT-3.5 | 45 vs 45 | 47 vs 50 | tie_broken | none |
| defects4j | semantic:validated | IR1xOR1 vs GPT-3.5 | 45 vs 45 | 47 vs 48 | tie_broken | none |
| defects4j | semantic:validated | IR3xOR2 vs CodeLlama full FT | 102 vs 98 | 102 vs 103 | reversal | none |
| defects4j | semantic:validated_or_equivalent | IR1xOR1 vs GPT-3.5 | 45 vs 45 | 47 vs 49 | tie_broken | none |
| defects4j | semantic:validated_or_equivalent | IR3xOR2 vs CodeLlama full FT | 102 vs 98 | 102 vs 103 | reversal | none |
| defects4j | plausible:L1_text | CodeLlama full FT vs DeepSeek base | 146 vs 147 | 151 vs 149 | reversal | III |
| defects4j | plausible:L2_ast | CodeLlama full FT vs DeepSeek base | 146 vs 147 | 151 vs 149 | reversal | III |
| defects4j | plausible:L3_rename | CodeLlama full FT vs DeepSeek base | 146 vs 147 | 151 vs 149 | reversal | III |
| defects4j | plausible:validated | CodeLlama full FT vs DeepSeek base | 146 vs 147 | 151 vs 149 | reversal | III |
| defects4j | plausible:validated_or_equivalent | CodeLlama full FT vs DeepSeek base | 146 vs 147 | 151 vs 149 | reversal | III |
| humanevaljava | semantic:L1_text | IR2xOR2 vs RepairLLaMA IR4xOR2 | 108 vs 109 | 117 vs 117 | tie_created | II |
| humanevaljava | semantic:L1_text | IR2xOR2 vs DeepSeek base | 108 vs 110 | 117 vs 110 | reversal | none |
| humanevaljava | semantic:L1_text | IR3xOR2 vs CodeLlama full FT | 99 vs 100 | 102 vs 100 | reversal | none |
| humanevaljava | semantic:L1_text | RepairLLaMA IR4xOR2 vs DeepSeek base | 109 vs 110 | 117 vs 110 | reversal | III |
| humanevaljava | semantic:L1_text | DeepSeek full FT vs GPT-4 | 119 vs 116 | 119 vs 120 | reversal | none |
| humanevaljava | semantic:L2_ast | IR2xOR2 vs RepairLLaMA IR4xOR2 | 108 vs 109 | 117 vs 117 | tie_created | II |
| humanevaljava | semantic:L2_ast | IR2xOR2 vs DeepSeek base | 108 vs 110 | 117 vs 110 | reversal | none |
| humanevaljava | semantic:L2_ast | IR3xOR2 vs CodeLlama full FT | 99 vs 100 | 102 vs 100 | reversal | none |
| humanevaljava | semantic:L2_ast | RepairLLaMA IR4xOR2 vs DeepSeek base | 109 vs 110 | 117 vs 110 | reversal | III |
| humanevaljava | semantic:L2_ast | DeepSeek full FT vs GPT-4 | 119 vs 116 | 119 vs 120 | reversal | none |
| humanevaljava | semantic:L3_rename | IR2xOR2 vs RepairLLaMA IR4xOR2 | 108 vs 109 | 117 vs 117 | tie_created | II |
| humanevaljava | semantic:L3_rename | IR2xOR2 vs DeepSeek base | 108 vs 110 | 117 vs 110 | reversal | none |
| humanevaljava | semantic:L3_rename | IR3xOR2 vs CodeLlama full FT | 99 vs 100 | 102 vs 100 | reversal | none |
| humanevaljava | semantic:L3_rename | RepairLLaMA IR4xOR2 vs DeepSeek base | 109 vs 110 | 117 vs 110 | reversal | III |
| humanevaljava | semantic:L3_rename | DeepSeek full FT vs GPT-4 | 119 vs 116 | 119 vs 120 | reversal | none |
| humanevaljava | semantic:validated | IR2xOR2 vs RepairLLaMA IR4xOR2 | 108 vs 109 | 116 vs 109 | reversal | II |
| humanevaljava | semantic:validated | IR2xOR2 vs DeepSeek base | 108 vs 110 | 116 vs 110 | reversal | none |
| humanevaljava | semantic:validated | IR3xOR2 vs CodeLlama full FT | 99 vs 100 | 102 vs 100 | reversal | none |
| humanevaljava | semantic:validated_or_equivalent | IR2xOR2 vs RepairLLaMA IR4xOR2 | 108 vs 109 | 116 vs 114 | reversal | II |
| humanevaljava | semantic:validated_or_equivalent | IR2xOR2 vs DeepSeek base | 108 vs 110 | 116 vs 110 | reversal | none |
| humanevaljava | semantic:validated_or_equivalent | IR3xOR2 vs CodeLlama full FT | 99 vs 100 | 102 vs 100 | reversal | none |
| humanevaljava | semantic:validated_or_equivalent | RepairLLaMA IR4xOR2 vs DeepSeek base | 109 vs 110 | 114 vs 110 | reversal | III |
| humanevaljava | semantic:validated_or_equivalent | DeepSeek full FT vs GPT-4 | 119 vs 116 | 119 vs 119 | tie_created | none |
| humanevaljava | plausible:L1_text | CodeLlama zero-shot IR3 vs GPT-3.5 | 107 vs 107 | 107 vs 108 | tie_broken | none |
| humanevaljava | plausible:L1_text | IR2xOR2 vs RepairLLaMA IR4xOR2 | 118 vs 118 | 126 vs 124 | tie_broken | II |
| humanevaljava | plausible:L1_text | IR2xOR2 vs GPT-4 | 118 vs 124 | 126 vs 126 | tie_created | none |
| humanevaljava | plausible:L2_ast | CodeLlama zero-shot IR3 vs GPT-3.5 | 107 vs 107 | 107 vs 108 | tie_broken | none |
| humanevaljava | plausible:L2_ast | IR2xOR2 vs RepairLLaMA IR4xOR2 | 118 vs 118 | 126 vs 124 | tie_broken | II |
| humanevaljava | plausible:L2_ast | IR2xOR2 vs GPT-4 | 118 vs 124 | 126 vs 126 | tie_created | none |
| humanevaljava | plausible:L3_rename | CodeLlama zero-shot IR3 vs GPT-3.5 | 107 vs 107 | 107 vs 108 | tie_broken | none |
| humanevaljava | plausible:L3_rename | IR2xOR2 vs RepairLLaMA IR4xOR2 | 118 vs 118 | 126 vs 124 | tie_broken | II |
| humanevaljava | plausible:L3_rename | IR2xOR2 vs GPT-4 | 118 vs 124 | 126 vs 126 | tie_created | none |
| humanevaljava | plausible:validated | CodeLlama zero-shot IR3 vs GPT-3.5 | 107 vs 107 | 107 vs 108 | tie_broken | none |
| humanevaljava | plausible:validated | IR2xOR2 vs RepairLLaMA IR4xOR2 | 118 vs 118 | 125 vs 118 | tie_broken | II |
| humanevaljava | plausible:validated | IR2xOR2 vs GPT-4 | 118 vs 124 | 125 vs 125 | tie_created | none |
| humanevaljava | plausible:validated_or_equivalent | CodeLlama zero-shot IR3 vs GPT-3.5 | 107 vs 107 | 107 vs 108 | tie_broken | none |
| humanevaljava | plausible:validated_or_equivalent | IR2xOR2 vs RepairLLaMA IR4xOR2 | 118 vs 118 | 125 vs 122 | tie_broken | II |

### The 23 directions stated in the paper (semantic-match bugs)

| Claim | Reported | Computed | L1 corrected (margin) | L3 corrected (margin) | Validated (margin) | Validated or equivalent (margin) | Margin if only the lower config is corrected (L3) |
|---|---|---|---|---|---|---|---|
| defects4j: RepairLLaMA IR4xOR2 > CodeLlama zero-shot IR3 | 144 vs 83 | 144 vs 83 | 147 vs 89 (+58) | 147 vs 89 (+58) | 146 vs 87 (+59) | 146 vs 89 (+57) | +55 |
| humanevaljava: RepairLLaMA IR4xOR2 > CodeLlama zero-shot IR3 | 109 vs 103 | 109 vs 103 | 117 vs 103 (+14) | 117 vs 103 (+14) | 109 vs 103 (+6) | 114 vs 103 (+11) | +6 |
| gitbugjava: RepairLLaMA IR4xOR2 > CodeLlama zero-shot IR3 | 20 vs 12 | 20 vs 12 | 20 vs 12 (+8) | 20 vs 12 (+8) | 20 vs 12 (+8) | 20 vs 12 (+8) | +8 |
| defects4j: RepairLLaMA IR4xOR2 > CodeLlama zero-shot IR4 | 144 vs 69 | 144 vs 69 | 147 vs 72 (+75) | 147 vs 73 (+74) | 146 vs 73 (+73) | 146 vs 73 (+73) | +71 |
| humanevaljava: RepairLLaMA IR4xOR2 > CodeLlama zero-shot IR4 | 109 vs 91 | 109 vs 91 | 117 vs 91 (+26) | 117 vs 91 (+26) | 109 vs 91 (+18) | 114 vs 91 (+23) | +18 |
| gitbugjava: RepairLLaMA IR4xOR2 > CodeLlama zero-shot IR4 | 20 vs 13 | 20 vs 13 | 20 vs 13 (+7) | 20 vs 13 (+7) | 20 vs 13 (+7) | 20 vs 13 (+7) | +7 |
| defects4j: RepairLLaMA IR4xOR2 > IR2xOR2 | 144 vs 139 | 144 vs 139 | 147 vs 142 (+5) | 147 vs 142 (+5) | 146 vs 141 (+5) | 146 vs 141 (+5) | +2 |
| defects4j: RepairLLaMA IR4xOR2 > CodeLlama full FT | 144 vs 98 | 144 vs 98 | 147 vs 103 (+44) | 147 vs 103 (+44) | 146 vs 103 (+43) | 146 vs 103 (+43) | +41 |
| humanevaljava: RepairLLaMA IR4xOR2 > CodeLlama full FT | 109 vs 100 | 109 vs 100 | 117 vs 100 (+17) | 117 vs 100 (+17) | 109 vs 100 (+9) | 114 vs 100 (+14) | +9 |
| gitbugjava: RepairLLaMA IR4xOR2 > CodeLlama full FT | 20 vs 13 | 20 vs 13 | 20 vs 13 (+7) | 20 vs 13 (+7) | 20 vs 13 (+7) | 20 vs 13 (+7) | +7 |
| defects4j: DeepSeek full FT > DeepSeek base | 138 vs 104 | 138 vs 104 | 139 vs 106 (+33) | 139 vs 106 (+33) | 139 vs 106 (+33) | 139 vs 106 (+33) | +32 |
| humanevaljava: DeepSeek full FT > DeepSeek base | 119 vs 110 | 119 vs 110 | 119 vs 110 (+9) | 119 vs 110 (+9) | 119 vs 110 (+9) | 119 vs 110 (+9) | +9 |
| gitbugjava: DeepSeek full FT > DeepSeek base | 19 vs 13 | 18 vs 13 | 18 vs 13 (+5) | 18 vs 13 (+5) | 18 vs 13 (+5) | 18 vs 13 (+5) | +5 |
| defects4j: DeepSeek LoRA > DeepSeek base | 128 vs 104 | 128 vs 104 | 128 vs 106 (+22) | 128 vs 106 (+22) | 128 vs 106 (+22) | 128 vs 106 (+22) | +22 |
| humanevaljava: DeepSeek LoRA > DeepSeek base | 124 vs 110 | 124 vs 110 | 124 vs 110 (+14) | 124 vs 110 (+14) | 124 vs 110 (+14) | 124 vs 110 (+14) | +14 |
| defects4j: DeepSeek full FT > DeepSeek LoRA | 138 vs 128 | 138 vs 128 | 139 vs 128 (+11) | 139 vs 128 (+11) | 139 vs 128 (+11) | 139 vs 128 (+11) | +10 |
| gitbugjava: DeepSeek full FT > DeepSeek LoRA | 19 vs 13 | 18 vs 13 | 18 vs 13 (+5) | 18 vs 13 (+5) | 18 vs 13 (+5) | 18 vs 13 (+5) | +5 |
| humanevaljava: DeepSeek LoRA > DeepSeek full FT | 124 vs 119 | 124 vs 119 | 124 vs 119 (+5) | 124 vs 119 (+5) | 124 vs 119 (+5) | 124 vs 119 (+5) | +5 |
| defects4j: RepairLLaMA IR4xOR2 > GPT-3.5 | 144 vs 45 | 144 vs 45 | 147 vs 50 (+97) | 147 vs 50 (+97) | 146 vs 48 (+98) | 146 vs 49 (+97) | +94 |
| defects4j: RepairLLaMA IR4xOR2 > GPT-4 | 144 vs 72 | 144 vs 72 | 147 vs 80 (+67) | 147 vs 80 (+67) | 146 vs 79 (+67) | 146 vs 79 (+67) | +64 |
| gitbugjava: RepairLLaMA IR4xOR2 > GPT-3.5 | 20 vs 8 | 20 vs 8 | 20 vs 8 (+12) | 20 vs 8 (+12) | 20 vs 8 (+12) | 20 vs 8 (+12) | +12 |
| gitbugjava: RepairLLaMA IR4xOR2 > GPT-4 | 20 vs 10 | 20 vs 10 | 20 vs 10 (+10) | 20 vs 10 (+10) | 20 vs 10 (+10) | 20 vs 10 (+10) | +10 |
| humanevaljava: GPT-4 > RepairLLaMA IR4xOR2 | 116 vs 109 | 116 vs 109 | 120 vs 117 (+3) | 120 vs 117 (+3) | 118 vs 109 (+9) | 119 vs 114 (+5) | -1 |

Summary: L1_text: 0 reversed, 0 tied, 1 reversed or tied if only the lower configuration were corrected; L3_rename: 0 reversed, 0 tied, 1 reversed or tied if only the lower configuration were corrected; validated: 0 reversed, 0 tied, 0 reversed or tied if only the lower configuration were corrected; validated_or_equivalent: 0 reversed, 0 tied, 0 reversed or tied if only the lower configuration were corrected.

## 6. Caveats

- A fix copy can legitimately fail when the official fix touches code outside the replaced method. JxPath-14 (fix spans 3 methods) is the known case; its copies reproduced their failure under R. Such bugs are excluded here, but the audit only checks the patch footprint, so the measured rates are upper bounds on harness noise unless confirmed by re-execution.
- The rename-aware normaliser removes annotations. Collections-26 is an L3-only match whose candidate adds an `@Override`; it fails to compile under R. L1 and L2 keep annotations; prefer them for headline numbers.
- L1 treats adjacent operator characters as separate tokens (`a + +b` equals `a ++b`). L2 does not.
- R ran the trigger tests; 'not reproduced' means the archived failure did not recur, not that the full suite passed. The cause of the archived failures is not established; call them non-reproducing archived failures.
- The recount assumes that a passing copy would have been flagged as an exact/AST/semantic match. Published counts with the corrections are upper bounds unless the 'validated' column is used.
- Everything here is post hoc, designed after the C1 sensitivity and the R results.

