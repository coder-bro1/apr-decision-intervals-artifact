# D3: Can ComPass, Invalidator and LLM4PatchCorrect run on our data?

Date: 2026-09-29. Scope: facts only. Nothing large was downloaded and no model was run. The biggest files fetched were the three paper PDFs (0.8 to 2.4 MB) and ComPass's `Data/2274_ori.jsonl` (2.1 MB).

**Our data**: about 55k LLM-generated patches, each changing one Java method, on Defects4J bugs. For each patch we have the buggy method and the candidate method. Separately we have the developer-fixed method, Defects4J checkouts in Docker (Java 8/11), and a 12 GB RTX 3060.

**Decision points used below**
- **DP1 (before tests)**: the tool sees only the patch plus facts about the *bug* that exist before any candidate is run: the buggy code, the trigger-test names and bodies, the buggy version's stack trace, and the buggy version's coverage.
- **DP2 (after tests)**: the tool also knows how the *candidate* did when run: pass/fail, and anything collected by executing it.
- **Information advantage**: the tool needs the developer fix, or labeled data containing it, for the same bug.

---

## 1. ComPass (Zhang et al., EMSE 2026; arXiv 2602.07561)

### Is the artifact reachable?
- **The anonymous link is dead.**
  - `https://anonymous.4open.science/r/ComPass-7EF1` renders only an empty "Anonymous Github" shell.
  - Its API `https://anonymous.4open.science/api/repo/ComPass-7EF1/files/` returns HTTP 410 `{"error":"repository_expired"}`.
- **There is a public GitHub release.** The paper's Data Availability Statement (arXiv v2, 6 Apr 2026) says "Our code and dataset are available on the repository https://github.com/iSEngLab/ComPass". The repo description reads "[EMSE 2026] ComPass: …".
  - Repo facts: created 2024-06-08. Last commit `e140adab` on 2025-09-03 ("Update README.md"). No GitHub releases. The GitHub API reports **no license** (`license: None`), and there is no LICENSE file in the tree.
  - **Zenodo: not found.** The paper and README mention none.

### Weights
- **No trained weights are released.** The README says "Due to the huge model size, we are unable to upload models to github." The tree has no `.bin`, `.pt` or `.safetensors` files.
- **Only training code and data are provided.**
  - `CL_pretrain/` holds the contrastive pre-training code. `ComPass/` holds fine-tune and test code.
  - `Data/2274_ori.jsonl` (2.2 MB) and `Data/2274_DA.jsonl` (24 MB, augmented).
  - Five-fold and cross-project splits (about 17 to 23 MB each).
  - `Data/methods_with_DA.tar.gz2` (9.1 MB).
  - `Data/CL_pretrain_data.jsonl` is only a Git-LFS pointer. The real file is 649,609,425 bytes.
- **Base model**: `google-bert/bert-base-uncased` (110M parameters). There is also a CodeBERT variant for RQ2.3.
- **Training settings (paper)**: batch 16, max length 512, 50 epochs, learning rate 5e-5, 5-fold cross-validation, two Tesla V100-SXM2 GPUs.

### Inputs needed at inference
Confirmed in `ComPass/test.py` and `DataLoader.py`:
- **Only two strings per patch plus a label**: `buggy_code`, `fixed_code` (the patched snippet), and `label`.
  - No tests, traces, coverage or developer fix go into the model.
  - Label convention: 1 = correct, 0 = overfitting. I verified this on `2274_ori.jsonl`: all 834 `Developer` rows have label 1.
- **The texts are hunk-context snippets, not whole methods.** They are space-tokenized, and some are wrapped as `public class test { … }`.
  - Median length is 63 whitespace tokens; the longest is 2,088.
  - Each side is truncated to 512 BERT tokens.
  - The model encodes buggy and patched text separately. It combines the two vectors using concatenation, add, subtract, multiply, cosine and Euclidean distance. The code also builds an LSTM layer that `forward` never uses; the combined vector goes to a linear layer and a sigmoid.

### Python and library versions
- **Not pinned.** There is no `requirements.txt` or `environment.yml`.
- The code imports `transformers` (`AutoModel`, and `AdamW` from `transformers`), `torch`, `sklearn` and `pandas`. `transformers.AdamW` was removed in recent transformers releases, so an older transformers version is implied; the exact version was not found.

### Other facts that matter
- **Training data includes developer fixes for the same bugs.**
  - The labeled set has 2,274 patches from Defects4J v2.0, 17 projects. 834 of them are Defects4J *developer* patches labeled correct (the paper's Table 2 says 965 before de-duplication).
  - The contrastive pre-training corpus is 485,106 production methods from the earliest commit of each Defects4J v2.0 project.
  - So a model trained on the released data has seen the developer fix for most Defects4J bugs as a "correct" example. That leaks into scoring *our* candidates for those same bugs.
- **Script quirks (from code reading).**
  - `train.py` loads the contrastive-pretrained checkpoint only when `--start_epoch > 0`. `RQ1/ComPass.sh` passes `--start_epoch 0`, so as written RQ1 skips the pre-trained checkpoint. `ComPass/train_DACL.sh` uses `--start_epoch 10`.
  - Each fold's best checkpoint is picked by accuracy on the *test* fold.

### Verdict
- **Input-wise it fits DP1**: it needs only buggy and patched code.
- **But there are no weights, so it must be retrained.**
  - For a fair DP1 run, first remove the developer patches, or do leave-bug-out training. Otherwise it is an information-advantage setup.
  - Also convert our method pairs into its snippet format.
- **Effort**: medium, roughly 2 to 4 days of engineering plus GPU time.
  - Fine-tuning bert-base (two encoder passes, 512 tokens, batch 16) on about 11k augmented patches for up to 50 epochs should fit 12 GB with fp16 or gradient accumulation (my estimate; not tested).
  - The optional contrastive pre-training needs the 650 MB LFS corpus.
  - Inference on 55k patches with bert-base is cheap.

---

## 2. Invalidator (Le-Cong et al., IEEE TSE 49(6), 2023; arXiv 2301.01113)

### Where the artifact lives
- **GitHub**: https://github.com/thanhlecongg/Invalidator, **MIT license**. Last commit `3ccd3030` on 2025-09-17. No GitHub releases.
- **Zenodo**: https://doi.org/10.5281/zenodo.7699142, record dated 2022-12-23, MIT, contains `invalidator.zip` (128,447,634 bytes). Both links are cited in the paper's §9.
- **Figshare: not found.**
- **Repo contents**
  - `data/raw.zip` (80.8 MB) and `data/processed.zip` (47.4 MB). These hold precomputed Daikon invariants for *their* dataset, split into buggy, developer-fixed and patched programs, plus CodeBERT/BERT/ODS feature pickles.
  - `model/*.joblib`: trained logistic-regression classifiers of 13 to 73 KB. These are `model.joblib` (with developer fix) and `model_nogt.joblib` / `model_wo_gt.joblib` (without developer fix), plus BERT and ODS variants.
  - Python code.

### What it needs at inference
- **Semantic part** (Daikon rules; paper §4.1 and Algorithm 1). Invariants on six program runs:
  - the candidate program's passing and failing tests;
  - the buggy program's passing and failing tests;
  - the **developer-fixed program's** passing and failing tests.
  - It builds a correct specification (invariants of buggy ∩ developer-fixed on passing tests) and an error specification (buggy-failing minus developer-fixed-failing).
  - Before Daikon it selects the passing tests that cover the modified methods (Algorithm 2), then compares invariants syntactically and with Z3.
  - So **the developer fix is mandatory**, and the candidate must be executed.
- **Syntactic part** (default "combine" mode):
  - CodeBERT (`microsoft/codebert-base`, first-token vector, run on CPU) embeds the buggy, patched and **developer** code.
  - Each text is the diff hunk with context, cut to the first 512 characters.
  - Features are the distances D(P,B) and D(P,G), where P is the patch, B the buggy program and G the developer fix. They feed a logistic regression, and the README default threshold is T=0.975.
- **A "w/o ground truth" variant exists** (`src/classifier/syntactic_classifier_wo_gt.py` with the shipped `model_nogt.joblib`).
  - It uses only D(P,B), so buggy and patched code only.
  - The paper's Table 5 shows it is much weaker: CodeBERT_wo-gt gets accuracy 0.46 and AUC 0.83, versus 0.73 and 0.89 with ground truth, on 139 patches.
  - Its training data (Wang et al. ASE20 patches plus 223 Defects4J developer patches for Chart/Time/Lang/Math) overlaps our bugs.
- **Trained weights**: yes, but only the tiny logistic-regression joblibs. CodeBERT is off the shelf.
- **Missing pipeline**
  - **The repo has no Daikon or Defects4J invocation scripts.** `invalidator.py` only reads already-inferred invariant text files, such as `data/processed_data/invariants/b/Math/88/result_passing.txt`. `src/utils.py` has only parsing and Z3 helpers.
  - `invalidator.py` returns `NotImplementedError("We currently only support semantic checking")` for `--c >= 1`. The syntactic results come from `experiment.py` and the `src.classifier.*` modules.
- **Environment**: `environment.yml` pins Python 3.6.13, transformers 4.18.0, scikit-learn 0.24.2, z3-solver 4.11.2.0 and numpy 1.19.5.
- **Java, Daikon and Defects4J versions: not found** in the paper text or the repo. The paper evaluates on Chart, Time, Lang and Math only: 139 patches from Xiong et al. for evaluation, and 666 from Wang et al. plus 223 developer patches for training.

### Runtime
- Invariant inference is capped at 5 hours per patch. The 139 evaluation patches took 15.5 hours, about 7 minutes per patch (paper §6.1). The LLM4PatchCorrect paper cites the same numbers.
- **Scaled to our data**: 55k × 7 min ≈ 6,400 CPU-hours. That is only feasible on a subsample.

### Verdict
- **Invalidator as published needs an information advantage** (the developer fix), and it runs at DP2 (the candidate is executed under Daikon).
  - We have the developer fix, so it *can* run, but only as an oracle-assisted comparator.
  - Effort: high, 1 to 2 weeks. Someone must write the Daikon (Chicory) plus Defects4J harness, whose versions are unspecified, and pay about 7 minutes per patch.
- **The ground-truth-free syntactic variant fits DP1** and uses only buggy and patched code.
  - It is not Invalidator proper; it is an ablation baseline with weak accuracy.
  - Effort: low, about half a day to 1 day. Build hunk texts, run CodeBERT, then apply `model_nogt.joblib`, whose training data overlaps Chart/Time/Lang/Math bugs, or retrain it.

---

## 3. LLM4PatchCorrect (Zhou et al., IEEE TSE 2024; arXiv 2303.00202 "PatchZero", v3 22 Mar 2024)

The clone checked is `external_artifacts/sota/LLM4PatchCorrectness` at `0aaef538` (2024-11-29, "Add files via upload"). GitHub shows 2 open issues and **no license**.

### Base model and memory
- **Model**: `bigcode/starcoderbase-7b`, set in `run_pipeline.sh` (`--gpt2 bigcode/starcoderbase-7b`).
  - The Hugging Face page says it is **gated**: you must accept the BigCode OpenRAIL-M v1 agreement and share contact info.
  - Context is 8,192 tokens. Stored weights are F32. The page gives no file size; about 28 GB is my estimate from 7B params × 4 bytes.
- **The code already quantizes to 4-bit**: `model_util.load_checkpoint` calls `AutoModelForCausalLM.from_pretrained(gpt2, device_map="auto", load_in_4bit=True, trust_remote_code=True)`.
  - The paper (§3.4.2) says that with int8 quantization "we are able to use any LLM within 7B parameters using a 12GB GPU (… 2080-Ti)".
  - **So a 12 GB RTX 3060 should fit.** About 4 to 5 GB of 4-bit weights plus activations for `--max_length 4000` at batch 1 is my estimate; not tested.
- **Setup gaps**
  - `install_library.sh` does not install `bitsandbytes`, which 4-bit loading requires.
  - `model_util.py` imports `deepspeed` at the top, which is awkward on Windows, so use WSL or Docker.
  - Pins: torch 2.1.0 cu121, transformers 4.28.1, huggingface_hub 0.25.2, Python 3.10+. Issue #1 reports NumPy 2.x incompatibility, so pin numpy<2.
- **Speed and cost**
  - The paper reports 2.4 s per patch (hardware for that figure not recorded here).
  - The code runs one forward pass per label ("correct"/"wrong"), so 2 passes of up to 4k tokens per patch.
  - Scoring 55k patches ≈ 37 GPU-hours at the paper's rate; slower on a 3060 is likely.
- **Missing retriever weights**
  - `data.py` always loads `SentenceTransformer('./pretrained_model/best/')`, the contrastive-learning retriever, from the README's Google Drive folder.
  - **That Drive link returns HTTP 404** (`https://drive.google.com/drive/folders/1MryWp2iqXAVo4UHxnN-bTspQkysM7Fpy?usp=sharing`), both via curl and WebFetch. So the retriever weights are **not obtainable**.
  - They can be retrained with `cl_pretrain/SimCSE`: base `microsoft/codebert-base-mlm`, data `cl_pretrain/sstub_data.zip` (12 MB, in the repo), env torch 1.12.1 and transformers 4.24.0.

### Guiding information: mandatory vs optional
Based on `data.py` `prepare_data` and the `--enhancement_option` string:
- **Every piece of guiding information is optional in principle.**
  - The prompt is built by looping over dash-separated options: `similar`, `bug`, `trace`, `testcase`, `coverage`. The default is `bug-trace-testcase-coverage-similar`.
  - Missing `bug` or `coverage` values fall back to "not available" text.
- **Hard dependencies even when an option is off**
  - The script always loads `data_checked/patch_cor/<Tool>_test_v1_enhanced.pkl`. It asserts the pkl has as many rows as the test CSV.
  - It always loads the SentenceTransformer and embeds the training corpus.
  - A code-only run therefore needs a dummy pkl and a retriever path; both are trivial code edits.
- **What each option means in this repo**
  - `bug` is the *exception message* (for example `java.lang.ArrayIndexOutOfBoundsException: -1`), not a natural-language issue text.
  - `trace` is the buggy version's stack trace, cut to 30 lines.
  - `testcase` is the names and method bodies of the trigger tests.
  - `coverage` is the Defects4J line and condition coverage summary.
  - `similar` is labeled patches from *other APR tools* retrieved by cosine similarity above 0.9, top 10.
- **The prompt text presumes the patch already passed the tests (DP2 framing).**
  - Test cases are introduced with "Originally the buggy code cannot pass some failing test cases and now the patched code can pass them."
  - Coverage is introduced with "Although this patch can pass available test cases, the available test cases only cover limited coverages".
- **Patch format**: a flattened diff with context and `-`/`+` markers on one line, not a method pair. The labels in the CSVs are 0 = correct, 1 = wrong.
- **Ablation (paper Table 7, average over tools)**

  | Configuration | Accuracy | F1 | AUC |
  |---|---|---|---|
  | LLM only, patch code only | 75.4 | 83.1 | 41.8 |
  | + bug information | 75.7 | 83.5 | 45.8 |
  | + test information | 76.0 | 83.7 | 43.3 |
  | + retrieved labeled patches | 84.0 | 86.3 | 77.2 |
  | Full | 84.4 | 86.5 | 80.4 |

  - Almost all of the gain comes from the retrieved labeled patches.
  - Issue #2 (open, no reply) reports that `bug-trace-testcase-coverage` without `similar` "drops extremely" when reproduced.
  - The repo's `evaluate()` computes AUC from hard 0/1 predictions.

### Can it run with only buggy/patched code plus optional failing-test names?
- **Yes, mechanically, after small code edits.**
  - Build a CSV and a matching pkl for a new `--task`, and add the task to `N_LABELS_DICT` and `get_prompts`.
  - Convert our method pairs to the flattened-diff format.
  - Point to any SentenceTransformer, or drop `similar`.
- **But the code-only setting is the weak one** (AUC 41.8 in the paper's own ablation).

### Precomputed Defects4J inputs in the repo (reusable)
- **The data**: `data_checked/patch_cor/*_test_v1_enhanced.pkl` hold, per patch, a tuple of: labels, patch text, bug id, failing-test names, failing-test method bodies, coverage text, exception message(s), and stack trace(s).
  - I loaded them with a restricted unpickler that blocks all class imports; they are plain Python types.
- **They are per-bug, not per-patch.** Across all 23 tool files there are **195 distinct bugs**, and for every bug the coverage, bug info, trace and test fields are identical across all its patches (0 of 195 bugs vary).
  - Bugs covered (all Defects4J v1.2): Math 69, Closure 62, Lang 33, Chart 22, Time 9.
  - So this data is **reusable for our candidates on those 195 bugs**. Other bugs need `defects4j export -p tests.trigger`, a buggy-version test run for the trace, and `defects4j coverage`, about 1 run per bug in our Docker.
  - A few entries are empty (for example Arja: 54 of 57 have test data).
- **The retrieval corpus contains developer fixes.**
  - Each `<Tool>_train_cross_v1.csv` (about 1,000 to 1,120 labeled rows) includes **314 to 354 Defects4J developer patches labeled correct**. I found them by exact text match against `defects4j-developer_test_v1.csv`, which has 354 rows, all label 0.
  - The APR-tool patches with bug ids total 825 (179 correct / 646 wrong) over the 195 bugs, and 84 of those bugs have at least one correct-labeled APR patch.
  - So `similar` retrieval on our Defects4J candidates can surface the **developer fix, or a correct patch, for the same bug** as a labeled "correct" example. That is an information advantage.

### Verdict
- **DP1 (code-only, or plus bug-level test names, bodies, trace and coverage from the buggy version)**: runnable with small edits, but the prompt must be reworded, because the stock wording asserts the patch passes the tests. Expect weak discrimination (paper AUC 41.8 to 45.8 without retrieval).
- **DP2**: its native framing. Use the stock prompt for plausible patches, reusing the precomputed per-bug data for the 195 v1.2 bugs.
- **With `similar` retrieval as shipped: information advantage.**
  - The corpus contains the developer patches, and correct labeled patches for the same bugs.
  - A fair run must strip developer patches and same-bug patches from the corpus, and retrain the retriever, because the Drive weights are 404.
- **Effort**
  - About 1 day to adapt the data format and code, plus accepting the StarCoderBase gate and a roughly 28 GB (estimated) model download.
  - About 0.5 to 1 day to retrain the SimCSE retriever if `similar` is wanted.
  - About 37+ GPU-hours to score 55k patches (or subsample).

---

## Summary table

| Tool | Artifact / weights | Inputs at inference | DP1 | DP2 | Info advantage? | Effort |
|---|---|---|---|---|---|---|
| ComPass | GitHub iSEngLab/ComPass, no license, **no weights**; anonymous link expired (410) | buggy snippet + patched snippet | Yes, after retraining without developer patches | n/a (no test signal used) | Released training data holds 834 developer patches for Defects4J v2.0 bugs, so leakage unless removed | Medium (retrain) |
| Invalidator | GitHub (MIT) + Zenodo 7699142; LR joblibs only; **no Daikon harness** | Daikon invariants on buggy + **developer-fixed** + patched programs (pass/fail tests); CodeBERT of buggy, patched, **developer** code | Only the "w/o ground truth" syntactic ablation (weak) | Full tool, and it needs the developer fix | **Yes (developer fix mandatory)** | High (about 7 min/patch; harness to write) |
| LLM4PatchCorrect | GitHub, no license; StarCoderBase-7B (gated); retriever weights **Drive 404** | Flattened diff; optional exception, trace, trigger tests, coverage, retrieved labeled patches | Code-only/bug-info mode with edits (weak) | Native framing; per-bug inputs precomputed for 195 v1.2 bugs | Retrieval corpus includes developer fixes and same-bug labels | Low to medium (4-bit fits 12 GB) |

## URLs opened
- https://arxiv.org/abs/2602.07561 ; https://arxiv.org/pdf/2602.07561v2
- https://anonymous.4open.science/r/ComPass-7EF1 ; https://anonymous.4open.science/api/repo/ComPass-7EF1/files/ (HTTP 410 `repository_expired`)
- https://api.github.com/repos/iSEngLab/ComPass (+ `/git/trees/HEAD?recursive=1`, `/commits`, `/releases`); raw.githubusercontent.com/iSEngLab/ComPass/main/{README.md, .gitattributes, Data/CL_pretrain_data.jsonl, Data/2274_ori.jsonl, ComPass/{test,train,Config,DataLoader,Model}.py, RQ1/ComPass.sh, ComPass/train_DACL.sh, CL_pretrain/{train.sh,Config.py}}
- https://arxiv.org/abs/2301.01113 ; https://arxiv.org/pdf/2301.01113
- https://api.github.com/repos/thanhlecongg/Invalidator (+ tree, commits, releases); raw.githubusercontent.com/thanhlecongg/Invalidator/main/{README.md, overview.md, environment.yml, invalidator.py, experiments/README.md, src/classifier/semantic_classifier.py, src/classifier/syntactic_classifier_wo_gt.py, src/feature/codeBERT.py, src/utils.py, experiment.py}
- https://zenodo.org/api/records/7699142
- https://arxiv.org/abs/2303.00202 ; https://arxiv.org/pdf/2303.00202v3
- https://github.com/Xin-Zhou-smu/LLM4PatchCorrectness ; https://api.github.com/repos/Xin-Zhou-smu/LLM4PatchCorrectness/issues (and /issues/2)
- https://drive.google.com/drive/folders/1MryWp2iqXAVo4UHxnN-bTspQkysM7Fpy?usp=sharing (HTTP 404); https://drive.google.com/embeddedfolderview?id=1MryWp2iqXAVo4UHxnN-bTspQkysM7Fpy (HTTP 404)
- https://huggingface.co/bigcode/starcoderbase-7b
- Web search results pages for Invalidator and LLM4PatchCorrect (used only to locate the above).

Local files read: `README.md`, `run_pipeline.sh`, `install_library.sh`, `main.py`, `data.py`, `model_util.py`, `util.py` (prompts), `cl_pretrain/README.md`, `cl_pretrain/SimCSE/{train.py,train_bash.sh}`, `cl_pretrain/environment.yml`, `data_checked/patch_cor/*` (CSVs and pickles, inspected with scratch scripts; nothing executed from the repo).
