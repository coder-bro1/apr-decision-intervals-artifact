# Addendum to Protocol v4: D1 naturalness and entropy-delta baselines

Frozen 2026-09-29, before any naturalness or entropy-delta score was computed.
Parent protocol: `PROTOCOL_V4_BUG_LEVEL.md` (SHA-256 `1a274b28…`). This addendum
only defines two additional content-aware baselines at decision point 1. It
changes no other definition.

## Model

- `Qwen/Qwen2.5-Coder-1.5B`, the base model, not the instruct model.
- The revision hash is recorded in `models/model_revisions.json`; the files
  live in `models/hf_cache`.
- Settings: fp16 on the local RTX 3060, no prompt and no file context. Each
  Java method is scored on its own.
- Texts longer than 2,048 tokens are truncated to their first 2,048 tokens. The
  number of truncated texts is reported.
- The model is used zero-shot. Nothing is tuned on our labels.

## Per-token surprisal

For a method text, the surprisal of token t is −log p(t | preceding tokens of
the same text). The first token has no preceding token and is skipped. Each
token belongs to the source line in which its first character lies.

## Naturalness

`naturalness(c)` is the mean log-probability over all scored tokens of the
candidate method, which is the negative of the mean surprisal. Higher means
more natural.

## Entropy delta

This is a method-level adaptation of Yang et al., "Revisiting unnaturalness for
automated program repair in the era of large language models". It looks only
at the changed code:

- Take a line-level diff between the buggy method and the candidate, using
  `difflib.SequenceMatcher` on the lines with trailing whitespace removed.
- **R** is the mean surprisal of the tokens on the removed buggy lines, scored
  within the buggy method.
- **A** is the mean surprisal of the tokens on the added candidate lines, scored
  within the candidate.
- `entropy_delta(c) = R − A`. Higher means the patch replaced less natural code
  with more natural code.

Edge cases:

- A pure deletion has no added lines. It uses A = the candidate's mean surprisal
  over the whole method.
- A pure insertion has no removed lines. It uses R = the buggy method's mean
  surprisal over the whole method.
- A text-identical patch, or a diff with no scored tokens on either side, gets
  delta 0.

Whole-method entropy delta is **not** used. Within one buggy method it ranks
candidates exactly like naturalness, so it would add nothing.

## Use

- Both scores enter `analysis_tools/v4/baselines.py` like CodeT5+: the class
  score is the maximum over the class's members.
- They are reported with the same bug-level primary specification, E0 and E1,
  and top-k.
- Both are descriptive baselines ("challenger vs naturalness/entropy-delta" in
  Protocol v4, Section 4). No threshold is tuned.
