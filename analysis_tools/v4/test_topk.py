"""Brute-force verification of topk.bug_bounds on random small pools with ties (exact Fractions)."""
import itertools
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import topk as T  # noqa: E402


def order_blocks(scores, elig):
    out, covered = [], 0
    for v in sorted({scores[i] for i in elig}, reverse=True):
        blk = [i for i in sorted(elig) if scores[i] == v]
        out.append(blk)
        covered += len(blk)
        if covered >= T.K_MAX:
            break
    return out


def metric_full(scores, elig, y):
    bl = order_blocks(scores, elig)
    return T.metrics([len(b) for b in bl], [sum(y[i] for i in b) for b in bl])


class TestTopK(unittest.TestCase):
    def test_random(self):
        rng = random.Random(7)
        for _ in range(400):
            n = rng.randint(1, 8)
            sp = [rng.randint(0, 3) for _ in range(n)]
            sq = [rng.randint(0, 3) for _ in range(n)]
            labels = [rng.choice([0, 1, None]) for _ in range(n)]
            elig = set(range(n))
            bp, bq = order_blocks(sp, elig), order_blocks(sq, elig)
            got = T.bug_bounds(bp, bq, labels)
            unk = [i for i in range(n) if labels[i] is None]
            vals = {k: [] for k in ("s1", "s3", "s5", "e5")}
            for comp in itertools.product([0, 1], repeat=len(unk)):
                y = list(labels)
                for i, v in zip(unk, comp):
                    y[i] = v
                mp, mq = metric_full(sp, elig, y), metric_full(sq, elig, y)
                for k in vals:
                    vals[k].append(mp[k] - mq[k])
            for k in vals:
                self.assertEqual(got[k], (min(vals[k]), max(vals[k])), (k, sp, sq, labels))


if __name__ == "__main__":
    unittest.main(verbosity=1)
