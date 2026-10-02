"""Simple F4/F5 review packet: one Markdown file to read + one CSV per reviewer to fill in (no browser needed).
Same 104 items and ids as the HTML packet (items are read from it), so the private key and scorer are unchanged."""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "results/v4/annotation/packet_annotator_2.html"
OUT = ROOT / "results/v4/annotation_simple"

HEAD = """# Patch review: 104 items

## What to do

Each item shows one Java method from a real project:
- the **buggy** version,
- the **developer's fix**,
- a **candidate fix** written by an AI tool. The candidate already passes the project's tests.

Decide whether the candidate is really correct, then write your answer in the CSV file (one row per item):

| column | what to write |
|---|---|
| verdict | `correct`, `incorrect` or `unsure` |
| confidence | `low`, `medium` or `high` |
| reason | one short line, e.g. "misses the null case" or "same logic, renamed variable" |

**What the verdicts mean**
- **correct**: the candidate behaves the same as the developer fix for every input that can reach this method.
  Different names, formatting, comments, or an equivalent way of writing the same logic are fine.
- **incorrect**: some input makes the candidate behave differently from the developer fix. For example, it only handles
  the tested case, skips real work, changes a condition or value, or throws/swallows an exception differently.
  If the candidate is a *different but valid* fix, still mark it `incorrect` and write "valid but different" as the reason.
- **unsure**: you really cannot decide. That is a fine answer; please don't guess.

**How to read an item.** Start with "Candidate vs developer fix". If it is empty or only formatting, the candidate is
almost certainly correct. Lines starting with `-` are removed and lines starting with `+` are added.

Please don't discuss the items with anyone until you have sent the CSV back. It takes about 5-8 hours in total and can
be split over several sittings. Open the CSV in Excel or any text editor and save it as CSV.

---
"""


def main():
    html = SRC.read_text(encoding="utf-8")
    items = json.loads(re.search(r"const ITEMS = (\[.*?\]);\n", html, re.S).group(1).replace("<\\/", "</"))
    OUT.mkdir(parents=True, exist_ok=True)
    parts = [HEAD]
    for it in items:
        parts.append(f"## {it['id']}  (bug: {it['bug']})\n")
        parts.append("**Candidate vs developer fix** (`-` = only in developer fix, `+` = only in candidate)\n")
        parts.append("```diff\n" + (it["cand_vs_fix"] or "(no difference)") + "\n```\n")
        parts.append("**What the developer changed**\n")
        parts.append("```diff\n" + (it["fix_diff"] or "(no difference)") + "\n```\n")
        parts.append("**What the candidate changed**\n")
        parts.append("```diff\n" + (it["cand_diff"] or "(no difference)") + "\n```\n")
        parts.append("<details><summary>Full methods (buggy / developer fix / candidate)</summary>\n\n"
                     "```java\n// BUGGY\n" + it["buggy"] + "\n```\n```java\n// DEVELOPER FIX\n" + it["fix"] +
                     "\n```\n```java\n// CANDIDATE\n" + it["candidate"] + "\n```\n</details>\n\n---\n")
    (OUT / "REVIEW_ITEMS.md").write_text("\n".join(parts), encoding="utf-8")
    for who in ("reviewer1", "reviewer2"):
        with open(OUT / f"ANSWERS_{who}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["id", "bug", "verdict", "confidence", "reason"])
            for it in items:
                w.writerow([it["id"], it["bug"], "", "", ""])
    print(f"{len(items)} items -> {OUT}")


if __name__ == "__main__":
    main()
