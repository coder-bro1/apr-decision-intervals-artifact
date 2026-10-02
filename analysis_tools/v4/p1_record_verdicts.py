"""Record the P1 relevance-review verdicts (ADDENDUM_V4_P1_PROSPECTIVE.md; relevance rule of ADDENDUM_V4_F3_DIFFTEST.md)
into results/v4/p1_prospective/difftest/relevance_review.json. Every counterexample was read (test source + failure)
against the candidate-vs-developer-fix diff with f3_review_view.py; Lang-45's 233 items were read in a compact listing
of their abbreviate(...) call and failure, and the three items whose call the listing could not extract were opened
individually. Review by Claude (AI assistant) at the author's request, 2026-10-02; disclosed in the AI-use statement.
No item met exclusions a-d, so every verdict is "witness"."""
import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RR = ROOT / "results/v4/p1_prospective/difftest/relevance_review.json"

REASONS = {
    "298514c4e0d8": "Cli-17 flatten returns 9 tokens instead of 8: the candidate adds '-' + ch after every character "
                    "it processes; different return value",
    "ac19e2096055": "Cli-25 renderWrappedText: when nextLineTabStop >= width the candidate recurses instead of resetting "
                    "the tab stop; the rendered text has a different length (718 vs 41), the candidate overflows the "
                    "stack where the fix returns, and two Randoop tests see a different exception or none; different "
                    "return value / throw vs no-throw / different exception type",
    "8b2deca3a269": "Closure-129 annotateCalls on a call node without children: the fix throws NullPointerException, the "
                    "candidate returns early (first == null); throw vs no-throw",
    "cffedb6cb441": "Closure-57 extractClassNameIfProvide/Require with a null parent: the fix throws "
                    "NullPointerException, the candidate's added null check returns normally; throw vs no-throw",
    "2bf01ad091f4": "Math-27 percentageValue computes numerator * 100.0 / denominator instead of 100 * doubleValue(); "
                    "the result differs in the last digit (509.99999999999994 vs 510.0); different return value",
    "f924ae186e88": "Math-82 SimplexSolver: the candidate's >= 0 and abs(ratio) pivot rule ends in "
                    "NoSuchElementException ('iterator exhausted') where the fix throws its no-feasible-solution "
                    "exception; different exception type (the Mockito constraint mocks only supply the input)",
    "caa5b3ae37fb": "Lang-45 abbreviate: the candidate maps lower > length (and lower == -1) to 0 instead of the "
                    "string length, so it returns a different string, or does not throw StringIndexOutOfBoundsException "
                    "where the fix does; different return value / throw vs no-throw",
}


def main():
    items = json.loads(RR.read_text())
    shutil.copy(RR, RR.with_name("relevance_review.pre_review.json"))
    missing = set()
    for it in items:
        key = it["candidate_id"][len("obscand_"):len("obscand_") + 12]
        if key not in REASONS:
            missing.add(key)
            continue
        it["verdict"], it["reason"] = "witness", REASONS[key]
    if missing:
        raise SystemExit(f"no reason recorded for {sorted(missing)}")
    RR.write_text(json.dumps(items, indent=1))
    print(Counter(i["verdict"] for i in items), len({i["candidate_id"] for i in items}), "candidates")


if __name__ == "__main__":
    main()
