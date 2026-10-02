"""Run BatchMethodNormalize over every unique method text (candidates and buggy anchors) of the noop parser input."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "results/noop_filter/v1/parser_input.tsv"
JAVA = ROOT / "execution_tools/BatchMethodNormalize.java"
OUT = ROOT / "results/v4/normalize"
OUT.mkdir(parents=True, exist_ok=True)
EXPORTS = [f"--add-exports=jdk.compiler/com.sun.tools.javac.{p}=ALL-UNNAMED" for p in ("tree", "util", "api")]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


with open(SRC, "rb") as fin, open(OUT / "normalized.tsv", "wb") as fout, open(OUT / "stderr.log", "wb") as ferr:
    rc = subprocess.run(["java", "-Xmx2g", *EXPORTS, str(JAVA)], stdin=fin, stdout=fout, stderr=ferr).returncode
counts = {}
with open(OUT / "normalized.tsv", encoding="utf-8") as f:
    n = 0
    for line in f:
        n += 1
        st = line.split("\t")[1]
        counts[st] = counts.get(st, 0) + 1
manifest = {"returncode": rc, "rows": n, "status_counts": counts, "input_sha256": sha(SRC),
            "tool_sha256": sha(JAVA), "output_sha256": sha(OUT / "normalized.tsv"),
            "java": subprocess.run(["java", "-version"], capture_output=True, text=True).stderr.strip()}
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
print(json.dumps(manifest, indent=1))
sys.exit(rc)
