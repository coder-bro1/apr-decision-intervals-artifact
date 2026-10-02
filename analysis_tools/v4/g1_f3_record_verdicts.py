"""Record the G1-F3 relevance-review verdicts (ADDENDUM_V4_G1_F3.md -> relevance rule of ADDENDUM_V4_F3_DIFFTEST.md)
into results/g1/f3_difftest/relevance_review.json. Every counterexample was read with f3_review_view.py
(--review results/g1/f3_difftest/relevance_review.json --cases results/g1/f3_package_v1/cases). Two candidates are
witnesses under the frozen rule but flagged BORDERLINE in the reason (they do not change any conclusion: P1 stays
open even if every counterexample counts)."""
import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RR = ROOT / "results/g1/f3_difftest/relevance_review.json"

REASONS = {
    "1b9af71d0c06": "getLine past the last line: fix returns null, candidate returns \"\" (dropped the pos >= length check); "
                    "different return value (the EvoSuite mock file only supplies an empty file to both versions)",
    "ab4c6d83d874": "getLine past the last line: fix returns null, candidate returns \"\" (dropped the pos >= length check); "
                    "different return value (the EvoSuite mock file only supplies an empty file to both versions)",
    "997e075f05cb": "isCachable() returns true where the fix returns false: candidate drops the _keyDeserializer and "
                    "_valueTypeDeserializer null checks; different return value (the Mockito JsonDeserializer mock is only a "
                    "non-null argument)",
    "25f2894f435b": "getNumericalMean() drops the getSampleSize() factor (returns successes/population); different return "
                    "value. Where a random generator appears, the failing assertion is on the deterministic mean",
    "0b7e4a4af86d": "translate() skips the character after every translated escape (pos += consumed followed by pos++), "
                    "so escaped/unescaped strings lose characters; different return value",
    "f67957f31dd8": "BORDERLINE (witness under the frozen rule): candidate replaces the fix's bounded 6-level ancestor loop "
                    "with unbounded recursion; on a cyclic tree (node appended to itself via public appendTo, or parent "
                    "fields written by the test) it throws StackOverflowError where the fix returns. Throw vs no-throw; not an "
                    "environment failure. The candidate also differs from the fix for ancestors deeper than 6 levels",
    "b8c5eab3cd91": "BORDERLINE (witness under the frozen rule): candidate always rehashes a copied table (_needRehash = true) "
                    "instead of _verifyNeedForRehash(); public table statistics (bucketCount, spilloverCount, primaryCount, "
                    "tertiaryCount) differ, and with internal fields written by the test the rehash throws where the fix does "
                    "not. A 'valid but different' fix under the strict rubric; no name-lookup difference was observed",
}


def main():
    items = json.loads(RR.read_text())
    backup = RR.with_name("relevance_review.pre_review.json")
    if not backup.exists():
        shutil.copyfile(RR, backup)
    for it in items:
        it["verdict"], it["reason"] = "witness", REASONS[it["candidate_id"][len("obscand_"):][:12]]
    RR.write_text(json.dumps(items, indent=1))
    print(Counter(i["verdict"] for i in items), len({i["candidate_id"] for i in items}), "candidates")


if __name__ == "__main__":
    main()
