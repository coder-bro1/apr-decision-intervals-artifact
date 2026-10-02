# Target-aware pre-flight check (post hoc, read-only)

Outcome per comparison open at the start of each refuting campaign. 'ceil' = reach of the evidence type (first listed rule is the optimistic one); 'targeted' = reach restricted to the campaign's target classes under its own update rule; k = minimum refutations; helpful = targeted / all helpful classes under the rule; refuted = helpful targeted classes that ended refuted.

## Defects4J: Census (E0 -> E1; rule candidate; 280 candidates in 274 classes; 16.0 h)

| Comparison | A0 | ceil candidate | ceil execution | targeted (k) | helpful | refuted | outcome |
|---|---|---|---|---|---|---|---|
| best_config_top1 | +0.00 | not reachable (anchor = 0) (None) | not reachable (anchor = 0) (None) | not reachable (anchor = 0) (None) | 0/0 | 0 | type cannot decide |
| testability | +1.02 | not reachable (locked or non-refutable mass keeps 0 inside) (None) | not reachable (locked or non-refutable mass keeps 0 inside) (None) | not reachable (targets leave 0 inside) (None) | 0/0 | 0 | type cannot decide |
| one_stage | +1.84 | reachable + (1) | not reachable (locked or non-refutable mass keeps 0 inside) (None) | not reachable (targets leave 0 inside) (None) | 0/3 | 0 | type could, targets not |
| source_agnostic | +3.11 | reachable + (8) | reachable + (8) | reachable + (8) | 17/22 | 12 | decided |

## Defects4J: Top-up (E1 -> F2; rule candidate; 179 candidates in 179 classes; 5.699 h)

| Comparison | A0 | ceil candidate | ceil execution | targeted (k) | helpful | refuted | outcome |
|---|---|---|---|---|---|---|---|
| best_config_top1 | +0.00 | not reachable (anchor = 0) (None) | not reachable (anchor = 0) (None) | not reachable (anchor = 0) (None) | 0/0 | 0 | type cannot decide |
| testability | +1.02 | not reachable (locked or non-refutable mass keeps 0 inside) (None) | not reachable (locked or non-refutable mass keeps 0 inside) (None) | not reachable (targets leave 0 inside) (None) | 0/0 | 0 | type cannot decide |
| one_stage | +1.84 | reachable + (1) | not reachable (locked or non-refutable mass keeps 0 inside) (None) | not reachable (targets leave 0 inside) (None) | 0/3 | 0 | type could, targets not |

## Defects4J: Generated tests (F2 -> F3; rule class; 165 candidates in 165 classes; 13.011 h)

| Comparison | A0 | ceil class | ceil candidate | targeted (k) | helpful | refuted | outcome |
|---|---|---|---|---|---|---|---|
| best_config_top1 | +0.00 | not reachable (anchor = 0) (None) | not reachable (anchor = 0) (None) | not reachable (anchor = 0) (None) | 0/0 | 0 | type cannot decide |
| testability | +1.02 | reachable + (1) | not reachable (locked or non-refutable mass keeps 0 inside) (None) | not reachable (targets leave 0 inside) (None) | 0/5 | 0 | type could, targets not |
| one_stage | +1.84 | reachable + (1) | reachable + (1) | reachable + (1) | 4/9 | 1 | decided |

Strict variant (conflict classes locked): best_config_top1: not reachable (anchor = 0) (None); testability: not reachable (targets leave 0 inside) (None); one_stage: reachable + (1)

## Fresh campaign G-E0 -> G-E1 (tier P {'targeted_candidates': 299, 'targeted_classes': 299, 'hours': 4.626}; tier S {'targeted_candidates': 1219, 'targeted_classes': 1219, 'hours': 15.399})

| Comparison | A0 | ceil candidate (k) | targeted (k) | helpful | refuted | outcome |
|---|---|---|---|---|---|---|
| challenger_frozen vs occurrence | +0.05 | reachable + (157) | reachable + (157) | 159/159 | 133 | targets could, too few failed |
| occurrence vs uniform | +0.03 | reachable + (1218) | reachable + (1218) | 1219/1219 | 1052 | targets could, too few failed |
| challenger_frozen vs uniform | +0.08 | reachable + (1275) | reachable + (1275) | 1278/1278 | 1099 | targets could, too few failed |
| codet5_similarity vs uniform | +0.70 | reachable + (1259) | reachable + (1259) | 1292/1292 | 1109 | targets could, too few failed |
| naturalness vs uniform | +0.08 | reachable + (1176) | reachable + (1176) | 1179/1179 | 1021 | targets could, too few failed |
