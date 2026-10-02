"""Brute-force checks for refutation_limit.py on small random pools (no project data needed).

A pool is a list of identity classes, each with a coefficient d (its weight in A - B), member labels in {0, 1, None},
an N-a no-op flag and per-member archived test-pass flags. The brute force re-labels members and recomputes every
class label with v4core.class_label (known-wins) independently of refutation_limit.classify. Checked:
  * L <= A0 <= H, and L, H, A0, A1 equal the min / max / all-0 / all-1 completions;
  * A0 is invariant under any admissible refute-only sequence (candidate-level and class-level steps), A1 under any
    admissible confirm-only sequence, and a refutation that hits a known-correct class is exactly the hazard case;
  * the greedy minimum number of refutations / confirmations equals the brute-force minimum, and the reachable
    interval equals the brute-force best, for the class, candidate (conflict-locked) and execution modes;
  * conflict-locked classes: member-level refutation can never resolve them, class-level refutation can.
"""
import itertools
import random
import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import refutation_limit as R  # noqa: E402

N_POOLS = 1000


def class_y(members, noop):
    """Independent label: v4core.class_label (known-wins) + the N-a rule."""
    y, conflict = V.class_label(list(range(len(members))), dict(enumerate(members)), "known_wins")
    if noop and y is None:
        y = 0
    return y, conflict


def value_bounds(pool):
    """Brute force over every completion of the unknown classes: (min, max, all-0, all-1)."""
    known, unk = Fraction(0), []
    for c in pool:
        y, _ = class_y(c["m"], c["noop"])
        if y is None:
            unk.append(c["d"])
        else:
            known += c["d"] * y
    vals = [known + sum((d for d, z in zip(unk, bits) if z), Fraction(0))
            for bits in itertools.product((0, 1), repeat=len(unk))]
    return min(vals), max(vals), known, known + sum(unk, Fraction(0))


def fast_bounds(pool):
    """(L, H) from v4core labels, using the per-class min/max (equal to value_bounds; checked in the first test)."""
    L = H = Fraction(0)
    for c in pool:
        y, _ = class_y(c["m"], c["noop"])
        L += c["d"] * y if y is not None else min(Fraction(0), c["d"])
        H += c["d"] * y if y is not None else max(Fraction(0), c["d"])
    return L, H


def rows(pool):
    out = []
    for c in pool:
        y, conflict = R.classify(c["m"], c["noop"])
        out.append({"d": c["d"], "y": y, "conflict": conflict and y is None,
                    "exec_ok": any(not t for t in c["tp"]), "key": id(c)})
    return [r for r in out if r["d"] != 0]


def random_pool(rng, conflict_rate=0.25):
    pool, n_none = [], 0
    for _ in range(rng.randint(1, 6)):
        k = rng.randint(1, 3)
        m = [rng.choice((None, None, 0, 1)) for _ in range(k)]
        if rng.random() < conflict_rate:
            m = [0, 1] + m[:1]
        if n_none + m.count(None) > 9:
            m = [x if x is not None else rng.choice((0, 1)) for x in m]
        n_none += m.count(None)
        pool.append({"d": Fraction(rng.randint(-4, 4), rng.choice((1, 2, 3, 6))), "m": m,
                     "noop": rng.random() < 0.15, "tp": [rng.random() < 0.4 for _ in m]})
    return pool


def apply(pool, actions, val):
    """actions: ('member', ci, mi) sets one member, ('class', ci) sets every member of a class."""
    new = [dict(c, m=list(c["m"])) for c in pool]
    for a in actions:
        if a[0] == "member":
            new[a[1]]["m"][a[2]] = val
        else:
            new[a[1]]["m"] = [val] * len(new[a[1]]["m"])
    return new


def actions_for(pool, mode, val=0):
    """Admissible one-sided actions: a refutation (val 0) never touches a known-correct class and a confirmation
    (val 1) never touches an incorrect class (archived or N-a); those hits are the hazard, tested separately."""
    if mode == "class":
        return [("class", ci) for ci, c in enumerate(pool) if class_y(c["m"], c["noop"])[0] is None]
    return [("member", ci, mi) for ci, c in enumerate(pool) for mi, v in enumerate(c["m"])
            if v is None and class_y(c["m"], c["noop"])[0] != 1 - val
            and (mode != "execution" or not c["tp"][mi])]


def brute_force(pool, val, mode):
    """Minimum number of actions that decide the comparison, and the best reachable [L, H] over all action sets."""
    acts = actions_for(pool, mode, val)
    k_min, best_L, best_H = None, None, None
    for size in range(len(acts) + 1):
        for sub in itertools.combinations(acts, size):
            L, H = fast_bounds(apply(pool, sub, val))
            best_L = L if best_L is None else max(best_L, L)
            best_H = H if best_H is None else min(best_H, H)
            if k_min is None and (L > 0 or H < 0):
                k_min = size
    return k_min, best_L, best_H


class TestRefutationLimit(unittest.TestCase):
    def test_bounds_and_completions(self):
        rng = random.Random(1)
        for _ in range(N_POOLS):
            pool = random_pool(rng)
            L, H, A0, A1 = R.bounds(rows(pool))
            self.assertEqual((L, H, A0, A1), value_bounds(pool))
            self.assertEqual((L, H), fast_bounds(pool))
            self.assertTrue(L <= A0 <= H and L <= A1 <= H)

    def test_a0_invariant_under_refutation(self):
        rng = random.Random(2)
        hazards = 0
        for _ in range(N_POOLS):
            pool = random_pool(rng)
            _, _, A0, _ = value_bounds(pool)
            for _ in range(rng.randint(1, 6)):
                if rng.random() < 0.5:   # candidate-level refutation of one unknown member
                    cands = [(ci, mi) for ci, c in enumerate(pool) for mi, v in enumerate(c["m"]) if v is None]
                    if not cands:
                        break
                    ci, mi = rng.choice(cands)
                    new = apply(pool, [("member", ci, mi)], 0)
                    hz = R.hazard(pool[ci]["m"], new[ci]["m"], pool[ci]["noop"])
                    self.assertEqual(hz, class_y(pool[ci]["m"], pool[ci]["noop"])[0] == 1)
                else:                    # class-level refutation of one unknown class (F3 rule; never a known 1)
                    cl = actions_for(pool, "class")
                    if not cl:
                        break
                    new, hz = apply(pool, [rng.choice(cl)], 0), False
                L2, H2, A0_2, _ = value_bounds(new)
                if hz:
                    hazards += 1
                    # touching a known-correct class: A0 changes exactly when the class matters (d != 0)
                    self.assertEqual(A0_2 != A0, pool[ci]["d"] != 0)
                    break
                self.assertEqual(A0_2, A0)
                self.assertTrue(L2 <= A0 <= H2)
                pool = new
        self.assertGreater(hazards, 0)

    def test_a1_invariant_under_confirmation(self):
        rng = random.Random(3)
        for _ in range(N_POOLS):
            pool = random_pool(rng)
            _, _, _, A1 = value_bounds(pool)
            for _ in range(rng.randint(1, 6)):
                if rng.random() < 0.5:   # candidate-level confirmation of any unknown member (may be a hazard)
                    cands = [(ci, mi) for ci, c in enumerate(pool) for mi, v in enumerate(c["m"]) if v is None]
                    if not cands:
                        break
                    ci, mi = rng.choice(cands)
                    new = apply(pool, [("member", ci, mi)], 1)
                    hz = R.hazard(pool[ci]["m"], new[ci]["m"], pool[ci]["noop"], "confirm")
                    if hz:
                        self.assertEqual(value_bounds(new)[3] != A1, pool[ci]["d"] != 0)
                        break
                else:
                    cl = actions_for(pool, "class")
                    if not cl:
                        break
                    new = apply(pool, [rng.choice(cl)], 1)
                pool = new
                L2, H2, _, A1_2 = value_bounds(pool)
                self.assertEqual(A1_2, A1)
                self.assertTrue(L2 <= A1 <= H2)

    def check_mode(self, polarity, mode, seed, n=N_POOLS):
        rng = random.Random(seed)
        reach = 0
        for _ in range(n):
            pool = random_pool(rng)
            res = R.limit(rows(pool), polarity, mode)
            k_bf, bL, bH = brute_force(pool, 0 if polarity == "refute" else 1, mode)
            self.assertEqual(res["k_min"], k_bf, (polarity, mode, pool))
            self.assertEqual((res["L_best"], res["H_best"]), (bL, bH), (polarity, mode, pool))
            if polarity == "refute":
                self.assertTrue(res["L_best"] <= res["A0"] <= res["H_best"])
                if res["k_min"] is not None and res["k_min"] > 0:
                    self.assertEqual(res["direction"], "+" if res["A0"] > 0 else "-")
                if res["A0"] == 0:
                    self.assertTrue(res["status"].startswith(("decided", "not reachable")))
            reach += res["k_min"] is not None and res["k_min"] > 0
        self.assertGreater(reach, 0)

    def test_greedy_refute_class(self):
        self.check_mode("refute", "class", 4)

    def test_greedy_refute_candidate(self):
        self.check_mode("refute", "candidate", 5)

    def test_greedy_refute_execution(self):
        self.check_mode("refute", "execution", 6)

    def test_greedy_confirm_class(self):
        self.check_mode("confirm", "class", 7)

    def test_greedy_confirm_candidate(self):
        self.check_mode("confirm", "candidate", 8)

    def test_conflict_locked_example(self):
        # known correct +2; conflict class {0, 1} with d = -3; plain unknown d = -1. L = -2, A0 = +2.
        pool = [{"d": Fraction(2), "m": [1], "noop": False, "tp": [False]},
                {"d": Fraction(-3), "m": [0, 1], "noop": False, "tp": [False, False]},
                {"d": Fraction(-1), "m": [None], "noop": False, "tp": [False]}]
        cand, cls = R.limit(rows(pool), "refute", "candidate"), R.limit(rows(pool), "refute", "class")
        self.assertEqual((cand["L"], cand["A0"]), (Fraction(-2), Fraction(2)))
        self.assertTrue(cand["status"].startswith("not reachable"))
        self.assertEqual((cand["L_best"], cand["H_best"]), (Fraction(-1), Fraction(2)))
        self.assertEqual(cand["locked_conflict_classes"], 1)
        self.assertEqual(cls["k_min"], 1)
        self.assertEqual(brute_force(pool, 0, "candidate")[0], None)
        self.assertEqual(brute_force(pool, 0, "class")[0], 1)
        # a no-op conflict class is already incorrect under N-a, so it is not locked (L = 2 + 0 - 1 > 0: decided)
        pool[1]["noop"] = True
        res = R.limit(rows(pool), "refute", "candidate")
        self.assertEqual((res["k_min"], res["status"], res["locked_classes"]), (0, "decided +", 0))

    def test_conflict_never_resolved_by_members(self):
        rng = random.Random(9)
        for _ in range(300):
            pool = random_pool(rng, conflict_rate=0.6)
            for ci, c in enumerate(pool):
                if class_y(c["m"], c["noop"])[1] and not c["noop"]:
                    sub = [a for a in actions_for(pool, "candidate") if a[1] == ci]
                    for val in (0, 1):
                        self.assertIsNone(class_y(apply(pool, sub, val)[ci]["m"], False)[0])
                    self.assertEqual(class_y(apply(pool, [("class", ci)], 0)[ci]["m"], False)[0], 0)

    def test_anchor_zero_never_decidable(self):
        pool = [{"d": Fraction(1), "m": [None], "noop": False, "tp": [False]},
                {"d": Fraction(-1), "m": [None], "noop": False, "tp": [False]}]
        for mode in R.MODES:
            res = R.limit(rows(pool), "refute", mode)
            self.assertEqual(res["A0"], 0)
            self.assertIsNone(res["k_min"])
            self.assertIn("anchor = 0", res["status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
