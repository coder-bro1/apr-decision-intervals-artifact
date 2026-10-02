# D3 Information-Compatibility Notes (in progress, 2026-09-29)

Each tool was checked against its public artifact. The table records what the
tool needs, whether it can run at decision point 1 (before any test runs) or
decision point 2 (plausible patches, after tests), and its status here.

| Tool | Artifact | Needs | DP1 | DP2 | Status |
|---|---|---|---|---|---|
| APPT (TSE 2024) | github.com/iSEngLab/APPT @ 7a254a22; model on Google Drive | buggy + patched code tokens (BERT + BiLSTM) | yes | yes | To run. Caveat: trained on Defects4J patches from classic APR tools, so bug overlap must be reported |
| LLM4PatchCorrect (TSE 2024) | github.com/Xin-Zhou-smu/LLM4PatchCorrectness @ 0aaef538; model on Google Drive; StarCoder-7B | labeled patches of other tools, bug description, execution traces, failing tests, coverage | no (needs execution information) | partial | Check a reduced-guidance option; traces and coverage are not in our data |
| ComPass (EMSE 2026; arXiv 2602.07561) | anonymous.4open.science/r/ComPass-7EF1 | buggy + patched code (contrastive pre-trained encoder) | likely | likely | To fetch and check |
| Invalidator (TSE 2023) | repository not yet located | the developer-fixed program, plus invariants from executions | no (uses the developer fix) | no (information advantage) | Report as an information-advantaged tool |
| PrevaRank (JSS 2026) | outputs already exist for 4,180 of 4,200 plausible LLM patches | plausible patches, historical database | no | yes | D2 baseline |
| CodeT5+ similarity | local model | buggy + patch code | yes | yes | Computed (v4/content_scores) |
| Naturalness / entropy-delta | Qwen2.5-Coder-1.5B (downloading) | buggy + patch code | yes | yes | To run |

## Agent check, 2026-09-29 (details in D3_AGENT_FINDINGS.md)

None of the three tools runs on our data as shipped.

- **ComPass.** The anonymous artifact has expired (HTTP 410). The GitHub repo at iSEngLab/ComPass has no weights and no license. Retraining is required, and the labeled set contains 834 Defects4J developer fixes, which is a leakage risk. Decision point 1 only after retraining, 2 to 4 days of effort.
- **Invalidator.** It needs the developer fix plus Daikon invariants from executions. There is no pipeline script, and it takes about 7 minutes per patch. It is an information-advantaged tool at decision point 2. A weak ground-truth-free syntactic variant exists.
- **LLM4PatchCorrect.** It needs the gated StarCoderBase-7B model, and the retriever weights link is dead (404). Its retrieval corpus contains developer fixes, a leakage risk. Code-only mode gives AUC 41.8 in its own paper. Decision point 2 is its native setting.
- **Runnable now.** APPT (released checkpoint), with the caveat that its training set overlaps our bugs.
