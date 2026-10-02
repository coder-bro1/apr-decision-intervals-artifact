"""Gate A: the v4 library must reproduce the reviewed draft exactly, and bounds must equal brute force."""
import itertools
import random
import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402

DATA = None


def data():
    global DATA
    if DATA is None:
        DATA = V.load(hash_inputs=False)
    return DATA


class TestReproduceDraft(unittest.TestCase):
    """Context unit + per-context exact identity + filter (N-b) + uniform ties = the reviewed draft."""

    def run_pair(self, ev_name, pol_b="mra"):
        d = data()
        pools = V.build_pools(d, "context", "occ")
        units, _ = V.evaluate_pair(d, pools, d.evidence(ev_name), "challenger", pol_b, noop="N-b")
        return units

    def test_primary_pre_census(self):
        u = self.run_pair("E0")
        eb = V.aggregate(u, "bug", 488)
        ec = V.aggregate(u, "unit")
        self.assertAlmostEqual(float(eb["lo"]), -0.0008720389355635257, places=15)
        self.assertAlmostEqual(float(eb["hi"]), 0.08934881432319956, places=15)
        self.assertAlmostEqual(float(ec["lo"]), 0.0026137389459188766, places=15)
        self.assertAlmostEqual(float(ec["hi"]), 0.08591251437272199, places=15)
        self.assertEqual(V.relevant_unknowns(u), 359)

    def test_primary_post_census(self):
        u = self.run_pair("E1")
        eb = V.aggregate(u, "bug", 488)
        self.assertEqual(round(V.pp(eb["lo"]), 2), 2.61)
        self.assertEqual(round(V.pp(eb["hi"]), 2), 8.48)
        ec = V.aggregate(u, "unit")
        self.assertEqual(round(V.pp(ec["lo"]), 2), 2.84)
        self.assertEqual(round(V.pp(ec["hi"]), 2), 8.28)
        self.assertEqual(V.relevant_unknowns(u), 174)

    def test_scenarios_pre_census(self):
        eb = V.aggregate(self.run_pair("E0"), "bug", 488)
        self.assertEqual(round(V.pp(eb["all0"]), 2), 5.02)
        self.assertEqual(round(V.pp(eb["all1"]), 2), 3.83)

    def test_occurrence_row(self):
        eb = V.aggregate(self.run_pair("E1", "occurrence"), "bug", 488)
        self.assertEqual((round(V.pp(eb["lo"]), 2), round(V.pp(eb["hi"]), 2)), (-3.09, 10.48))


class TestBoundsBruteForce(unittest.TestCase):
    """Sharpness: for random small pools, [lo, hi] equals min/max over every completion of unknown labels."""

    def test_random_pools(self):
        rng = random.Random(20260929)
        for _ in range(1500):
            n = rng.randint(1, 7)
            pa = [Fraction(rng.randint(0, 3)) for _ in range(n)]
            pb = [Fraction(rng.randint(0, 3)) for _ in range(n)]
            sa, sb = sum(pa) or 1, sum(pb) or 1
            pa = [x / sa for x in pa]
            pb = [x / sb for x in pb]
            labels = [rng.choice([0, 1, None]) for _ in range(n)]
            unk = [i for i in range(n) if labels[i] is None]
            vals = []
            for comp in itertools.product([0, 1], repeat=len(unk)):
                y = list(labels)
                for i, v in zip(unk, comp):
                    y[i] = v
                vals.append(sum((pa[i] - pb[i]) * y[i] for i in range(n)))
            lo = sum((pa[i] - pb[i]) * labels[i] if labels[i] is not None else min(Fraction(0), pa[i] - pb[i])
                     for i in range(n))
            hi = sum((pa[i] - pb[i]) * labels[i] if labels[i] is not None else max(Fraction(0), pa[i] - pb[i])
                     for i in range(n))
            self.assertEqual((lo, hi), (min(vals), max(vals)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
