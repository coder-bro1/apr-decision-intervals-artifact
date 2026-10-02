# Upstream Sources and Provenance

## RepairLLaMA

- Repository: `https://github.com/ASSERT-KTH/repairllama`
- Pinned commit: `b7e22bf1632d6df9a718f2498a5cf29a39ba7d87`
- Redistribution decision: not bundled because no license file was present in
  the checked-out repository.
- Review-skipping path:
  `src/patch_analysis/manual_patch_analysis_martin.py`, lines 172--187 and
  239--244 at the pinned commit. A bug is skipped after an exact, AST, or
  semantic match; within manual review, later patches are skipped after an
  equivalent patch is found.
- Label initialization/mapping path:
  `src/patch_analysis/convert_format.py`, lines 83--122. The conversion initializes
  `semantical_match` to false and maps `Plausible` to false before the later
  manual-review flow.

These locations explain the provenance audit. They do not by themselves prove
the final label of an individual candidate; the paper joins them with archived
candidate-level evidence.

## Practical POD Benchmark

- Repository: `https://github.com/SOLAR-group/apr-overfitting-benchmark`
- Pinned commit: `029a0dc53bb78c5286b32c8e558c623b3705f345`
- Redistribution decision: not bundled because the pinned repository had no
  open-source license.
- The five detector outputs are represented only by derived aggregate results
  and checksums. Retrieve the exact commit independently to inspect source data.

## Defects4J

- Version used by the controlled census: 3.0.1.
- Official project: `https://github.com/rjust/defects4j`
- The package contains interpreted test evidence and hashes, not Defects4J
  project repositories or third-party project source trees.

## Label Consumption in This Study

The detector-benchmark loader of the earlier analysis verifies
generation/evaluation alignment and maps the archived boolean
`semantical_match` field to correct/incorrect for the released-label analysis.
The same output separately records the reviewed-only and all-Unknown-correct
sensitivity treatments. The latter is a scenario, not asserted ground truth.
