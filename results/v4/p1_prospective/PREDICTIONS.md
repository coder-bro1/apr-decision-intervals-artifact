# P1 prospective campaign: frozen predictions

Start: final Defects4J evidence (E1+F2+F3+F4+R), decision point 2. Decided at start: 13 of 21.
Targets: 99 untested helpful classes (99 candidates, 70 bugs). Yield prior 0.142 per targeted class.

| Comparison | Start interval (pp) | A0 | Need (pp) | Helpful untested | Min. refutations | P(decide) | Prediction |
|---|---|---|---|---|---|---|---|
| challenger vs correctness_stage | [-1.64, +1.02] | +0.00 | - | - | - | 0.0 | cannot be decided by refutation (A0 = 0) |
| challenger vs codet5_similarity | [-1.69, +6.10] | +4.97 | 1.6896 | 24 | 9 | 0.0037 | open |
| challenger vs prevarank | [+0.00, +7.58] | +6.15 | 0.0 | 44 | 1 | 0.9986 | decided |
| correctness_stage vs codet5_similarity | [-1.79, +6.81] | +4.97 | 1.7921 | 25 | 9 | 0.0027 | open |
| prevarank vs mra | [-5.61, +0.92] | -4.61 | 0.9221 | 38 | 5 | 0.0979 | open |
| prevarank vs occurrence | [-5.66, +2.56] | -3.05 | 2.5649 | 39 | 20 | 0.0 | open |
| appt vs mra | [-8.33, +1.71] | -6.78 | 1.7129 | 39 | 9 | 0.0253 | open |
| appt vs occurrence | [-8.03, +3.02] | -5.22 | 3.0154 | 37 | 15 | 0.0 | open |
