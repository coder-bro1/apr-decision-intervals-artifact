"""Brute-force check of pod.diff_bounds on random small instances."""
import itertools
import random
import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pod  # noqa: E402


def ba(y, pred):
    p = sum(y)
    n = len(y) - p
    tp = sum(1 for a, b in zip(y, pred) if a == 1 and b == 1)
    tn = sum(1 for a, b in zip(y, pred) if a == 0 and b == 0)
    return Fraction(tp, p) / 2 + Fraction(tn, n) / 2


class T(unittest.TestCase):
    def test_random(self):
        rng = random.Random(3)
        for _ in range(500):
            nk, nu = rng.randint(2, 6), rng.randint(0, 6)
            ky = [rng.randint(0, 1) for _ in range(nk)]
            ka = [rng.randint(0, 1) for _ in range(nk)]
            kb = [rng.randint(0, 1) for _ in range(nk)]
            ua = [rng.randint(0, 1) for _ in range(nu)]
            ub = [rng.randint(0, 1) for _ in range(nu)]
            vals = []
            for comp in itertools.product([0, 1], repeat=nu):
                y = ky + list(comp)
                if 0 < sum(y) < len(y):
                    vals.append(ba(y, ka + ua) - ba(y, kb + ub))
            if not vals:
                continue
            self.assertEqual(pod.diff_bounds(ky, ka, kb, ua, ub), (min(vals), max(vals)))


if __name__ == "__main__":
    unittest.main()
