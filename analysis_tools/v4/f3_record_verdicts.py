"""Record the F3 relevance-review verdicts (ADDENDUM_V4_F3_DIFFTEST.md, relevance rule) into
results/v4/f3_difftest/relevance_review.json. Every counterexample was read (test source + failure) against the
candidate-vs-developer-fix diff, using f3_review_view.py. Verdict per item: "witness" or "not_relevant:a|b|c|d".
Reasons are per candidate (and per behaviour where a candidate's counterexamples differ in kind)."""
import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RR = ROOT / "results/v4/f3_difftest/relevance_review.json"

# candidate-id prefix (after "obscand_") -> reason; all verdicts are "witness" (no item met exclusions a-d)
REASONS = {
    "ee93424fcad4": "null dataset: fix returns an empty legend collection, candidate throws NullPointerException "
                    "(calls dataset.getRowCount() on null); throw vs no-throw",
    "86a2f4836c3e": "null zone: fix throws IllegalArgumentException (Null 'zone' argument), candidate ignores the zone "
                    "argument (uses TimeZone.getDefault()) and throws nothing; throw vs no-throw. Where EvoSuite mock "
                    "dates appear they only supply the input; Randoop tests without mocks show the same difference",
    "14f2995ac2d8": "flatten returns 4 tokens instead of 3: candidate adds an extra '--' token after bursting a "
                    "non-option; different return value",
    "38edeadefcf0": "stopAtNonOption=false: fix keeps processing the remaining tokens (and throws NullPointerException on "
                    "the null argument), candidate stops at the first unknown option and returns; throw vs no-throw",
    "70776b39efa0": "fix throws IOException (unexpected end of input), candidate throws NullPointerException in "
                    "findSymbol after consuming the character early; different exception type (the Mockito ObjectCodec "
                    "mock plays no part in the difference)",
    "6795302d2c3c": "empty input file: fix returns an empty Document, candidate returns null (the test then fails with "
                    "NullPointerException); different return value. The EvoSuite mock file only supplies the same "
                    "empty input to both versions; a real empty file behaves the same",
    "104291e19bac": "isNumber(\"L\") / isNumber(\"l\"): fix returns false (no digit), candidate returns true; "
                    "different return value",
    "4bb7d0750955": "linearCombination on empty arrays: fix throws ArrayIndexOutOfBoundsException, candidate returns 0; "
                    "throw vs no-throw",
    "3852f671c78d": "abbreviate returns a different string (or does not throw StringIndexOutOfBoundsException where the "
                    "fix does): candidate maps lower == -1 to the string length; different return value / throw vs "
                    "no-throw",
    "441e0eb3bf7f": "abbreviate returns a different string: when lower > length the candidate clamps lower to "
                    "length - 1 instead of length; different return value",
    "9aacd8b5b626": "abbreviate returns a different string: when lower >= length the candidate clamps lower to "
                    "length - 1 instead of length; different return value",
    "cf65d75b45db": "abbreviate returns a different string (or does not throw StringIndexOutOfBoundsException where the "
                    "fix does): candidate resets lower to 0 when lower < 0 or lower > length; different return value / "
                    "throw vs no-throw",
}
MATH85 = ("bracket() on a function with no sign change once both bounds are reached: fix throws ConvergenceException, "
          "candidate returns the non-bracketing interval because its throw condition also requires the iteration "
          "limit; throw vs no-throw")
MATH72 = {"test18": "solve returns 0.0 instead of the min endpoint -589.87 (candidate drops setResult for the endpoints); "
                    "different return value",
          "test04": "same root but getIterationCount() is 31 instead of 0 (fix returns the min endpoint at once, "
                    "candidate runs full Brent iterations); different observable state, not toString/hashCode"}


def main():
    items = json.loads(RR.read_text())
    backup = RR.with_name("relevance_review.pre_review.json")
    if not backup.exists():
        shutil.copyfile(RR, backup)
    for it in items:
        cid, test = it["candidate_id"][len("obscand_"):], it["test"].split("::")[-1]
        if it["bug"] == "Math-85":
            reason = MATH85
        elif it["bug"] == "Math-72":
            reason = MATH72[test]
        else:
            reason = REASONS[cid[:12]]
        it["verdict"], it["reason"] = "witness", reason
    RR.write_text(json.dumps(items, indent=1))
    print(Counter(i["verdict"] for i in items), len({i["candidate_id"] for i in items}), "candidates")


if __name__ == "__main__":
    main()
