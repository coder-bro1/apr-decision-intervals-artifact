"""Download the v4 model weights into the project drive (never C:). Records revisions for reproducibility."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "models" / "hf_cache"
os.environ["HF_HOME"] = str(CACHE)
os.environ["HF_HUB_CACHE"] = str(CACHE / "hub")
os.environ["HF_HUB_DISABLE_XET"] = "1"  # the Xet backend stalled on this machine; plain HTTPS works
from huggingface_hub import HfApi, snapshot_download  # noqa: E402

MODELS = {
    "naturalness_lm": "Qwen/Qwen2.5-Coder-1.5B",
    "g1_generator": "Qwen/Qwen2.5-Coder-7B-Instruct",
}
record = {}
for role, repo in MODELS.items():
    info = HfApi().model_info(repo)
    path = snapshot_download(repo, revision=info.sha, allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "merges.txt", "vocab.json"])
    record[role] = {"repo": repo, "revision": info.sha, "path": path}
    print(role, repo, info.sha, flush=True)
(ROOT / "models" / "model_revisions.json").write_text(json.dumps(record, indent=1))
