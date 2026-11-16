"""Small exhaustive controls for optional complete-signature window pruning."""
from itertools import combinations
import random
import unittest

from cssdist.circuit_windows import window_relations


class WindowRelationsTests(unittest.TestCase):
    def test_three_location_replacement_and_baseline_deduplication(self):
        rows, records, counts = window_relations([1, 2, 3], [[0], [1], [2]], [[0, 1, 2]])
        self.assertEqual(rows, [(0, 1, 2)])
        self.assertGreater(counts['strict_replacements'], 0)
        self.assertGreater(len(records[0]['heavier']), len(records[0]['cheaper']))
        rows, _, _ = window_relations([1, 2, 3], [[0], [1], [2]], [[0, 1, 2]], [[0, 1, 2]])
        self.assertEqual(rows, [])

    def test_observable_bit_must_be_preserved(self):
        # First two bits are detectors; third is an observable. The apparent
        # detector relation 0+1+2 is logical, so it must never be used to prune.
        rows, _, _ = window_relations([1, 2, 7], [[0], [1], [2]], [[0, 1, 2]])
        self.assertEqual(rows, [])

    def test_equal_weight_replacements_not_added(self):
        rows, _, _ = window_relations([1, 2, 4, 7], [[0, 2], [1, 3]], [[0, 1]])
        self.assertEqual(rows, [])

    def test_invalid_data(self):
        for locations, windows, baseline in [([[3]], [[0]], []), ([[0]], [[0, 0]], []),
                ([[0]], [[1]], []), ([[0]], [[0]], [[0]]), ([[True]], [[0]], [])]:
            with self.subTest((locations, windows, baseline)), self.assertRaises(ValueError):
                window_relations([1], locations, windows, baseline)

    def test_budget_only_weakens_optional_relation_set(self):
        rows, _, stats = window_relations([1, 2, 3], [[0], [1], [2]], [[0, 1, 2]],
                                          max_configurations_per_window=7)
        self.assertEqual(rows, [])
        self.assertEqual(stats['windows_skipped_budget'], 1)
        self.assertEqual(stats['configurations'], 0)

    def test_minimum_weight_for_every_signature_is_preserved(self):
        # Exhaustive support validation on random tiny problems, not merely an
        # implementation echo: every signature's optimum survives all pruning.
        rng = random.Random(81832)
        for _ in range(60):
            n = 7
            cols = rng.sample(range(1, 16), n)
            locations = [rng.sample(range(n), 3) for _ in range(4)]
            rows, _, _ = window_relations(cols, locations, combinations(range(4), 3))
            neutrals = [sum(1 << j for j in row) for row in rows]
            before, after = {}, {}
            for word in range(1 << n):
                signature = 0
                for j, col in enumerate(cols):
                    if word >> j & 1:
                        signature ^= col
                weight = word.bit_count()
                before[signature] = min(before.get(signature, n + 1), weight)
                if all(2 * (word & g).bit_count() <= g.bit_count() for g in neutrals):
                    after[signature] = min(after.get(signature, n + 1), weight)
            self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
