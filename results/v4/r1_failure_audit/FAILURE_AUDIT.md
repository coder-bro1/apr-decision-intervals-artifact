# R1 failure audit

Sampled 160; outcomes {'compile_command_failed_twice': 70, 'controlled_trigger_failure': 77, 'admissible_triggers_pass_semantics_unknown': 5, 'unresolved_placement_or_repetition': 2, 'unresolved_no_admissible_trigger': 1, 'unresolved_setup_or_controls': 5}.

| Configuration | Reproduced | Not reproduced | Unresolved | Rate | 95% CI |
|---|---|---|---|---|---|
| all | 147 | 5 | 8 | 0.0329 | [0.0108, 0.0751] |
| repairllama_ir1_or3 | 28 | 2 | 2 | 0.0667 | [0.0082, 0.2207] |
| gpt35_gpt-zero-shot | 30 | 0 | 2 | 0.0 | [0.0, 0.1157] |
| gpt4_gpt-zero-shot | 30 | 2 | 0 | 0.0625 | [0.0077, 0.2081] |
| repairllama_ir1_or4 | 30 | 0 | 2 | 0.0 | [0.0, 0.1157] |
| repairllama_ir1_or1 | 29 | 1 | 2 | 0.0333 | [0.0008, 0.1722] |

Population 15641 labels; each withdrawn with the upper CI of its configuration.

| Comparison | L (pp) | Classes at risk | Expected withdrawals | P(decided) | Withdrawals to reopen (worst case) |
|---|---|---|---|---|---|
| mra | 9.27 | 1181 | 173.28 | 1.0 | 299 |
| best_config_top1 | 1.23 | 0 | 0.0 | 1.0 | None |
| first_global | 5.94 | 3 | 0.62 | 1.0 | None |
| borda | 7.99 | 49 | 1.91 | 1.0 | 39 |
| rrf | 7.79 | 51 | 1.6 | 1.0 | 38 |
| mean_norm_position | 13.00 | 841 | 140.75 | 1.0 | 103 |
| occurrence | 8.09 | 86 | 6.6 | 1.0 | 40 |
| mra_then_occurrence | 7.41 | 53 | 2.08 | 1.0 | 37 |
| testability | 0.41 | 1 | 0.21 | 1.0 | None |
| one_stage | 0.41 | 2 | 0.25 | 0.9914 | 2 |
| source_agnostic | 1.84 | 66 | 10.91 | 0.9596 | 9 |
| token_similarity | 11.41 | 663 | 109.34 | 1.0 | 328 |
| codet5_similarity | 12.26 | 29 | 3.23 | 1.0 | None |
| naturalness | 10.86 | 158 | 21.4 | 1.0 | 53 |
| entropy_delta | 11.27 | 229 | 33.57 | 0.9999 | 55 |
| uniform | 12.47 | 12451 | 2030.63 | 1.0 | 3803 |
