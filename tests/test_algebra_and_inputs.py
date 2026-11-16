import itertools
import random
import unittest

from cssdist import CSSCode, cyclic_lp
from cssdist.algebra import basis, kernel_basis, same_span, support
from cssdist.engine import check_limits


def span(rows):
    """Explicit set enumeration, independent of the package's elimination."""
    out = {0}
    for row in rows:
        out |= {v ^ row for v in out}
    return out


def oracle(checks, stabilizers, n):
    stabilizer_space = span(stabilizers)
    candidates = [v for v in range(1, 1 << n)
                  if v not in stabilizer_space and
                  all((v & row).bit_count() % 2 == 0 for row in checks)]
    return min(map(int.bit_count, candidates)) if candidates else None


class AlgebraTests(unittest.TestCase):
    def test_kernel_against_complete_enumeration(self):
        rng = random.Random(261006)
        for n in range(1, 9):
            for _ in range(15):
                rows = [rng.randrange(1 << n) for _ in range(rng.randrange(n + 2))]
                expected = {v for v in range(1 << n)
                            if all((v & r).bit_count() % 2 == 0 for r in rows)}
                self.assertEqual(span(kernel_basis(rows, n)), expected)
                self.assertEqual(span(basis(rows).values()), span(rows))

    def test_invalid_commutation(self):
        with self.assertRaisesRegex(ValueError, 'commutation'):
            CSSCode.from_sparse(2, [[0]], [[0]])

    def test_invalid_coordinates(self):
        for row in ([0, 0], [-1], [3], [True], [0.0]):
            with self.subTest(row=row), self.assertRaises(ValueError):
                CSSCode.from_sparse(3, [row], [])

    def test_invalid_symmetry(self):
        with self.assertRaisesRegex(ValueError, 'cyclic action'):
            CSSCode.from_sparse(4, [[0, 1]], [], cyclic_period=4)
        with self.assertRaisesRegex(ValueError, 'exchange'):
            CSSCode.from_sparse(3, [], [[0, 1], [1, 2]], sector_exchange=[0, 1, 2])

    def test_row_space_symmetry_not_just_row_permutation(self):
        code = CSSCode.from_sparse(3, [[0, 1], [1, 2]], [], cyclic_period=3)
        self.assertEqual(code.period, 3)

    def test_invalid_witness(self):
        for witness in ([0], [0, 1, 2, 3]):
            with self.subTest(witness=witness), self.assertRaisesRegex(ValueError, 'witness'):
                CSSCode.from_sparse(4, [[0, 1, 2, 3]], [[0, 1, 2, 3]],
                                    witnesses={'Z': [witness]})

    def test_dense_and_sparse_agree(self):
        code = CSSCode.from_dense([[1, 1, 1, 1]], [[1, 1, 1, 1]])
        self.assertEqual(code.fingerprint,
                         CSSCode.from_sparse(4, [[0, 1, 2, 3]], [[0, 1, 2, 3]]).fingerprint)
        with self.assertRaises(ValueError):
            CSSCode.from_dense([[1, 0.5]], [])

    def test_capacities_are_explicit(self):
        check_limits(CSSCode.from_sparse(8193, [], []), 65)
        check_limits(CSSCode.from_sparse(66, [list(range(65))], []), 1)
        with self.assertRaisesRegex(ValueError, 'k=0'):
            check_limits(CSSCode.from_sparse(1, [[0]], []), 1)


class ConstructorTests(unittest.TestCase):
    def test_independent_rectangular_hgp(self):
        code = cyclic_lp([[1, 1]], [[1, 1, 0], [0, 1, 1]])
        self.assertEqual((code.n, code.k), (8, 1))
        self.assertIsNone(code.exchange)
        self.assertEqual(oracle(code.hx, code.hz, code.n), 2)
        self.assertEqual(oracle(code.hz, code.hx, code.n), 3)

    def test_rank_deficient_constituents(self):
        a = [[1, 1], [1, 1]]
        code = cyclic_lp(a)
        self.assertEqual((code.n, code.k), (8, 2))
        self.assertEqual(oracle(code.hx, code.hz, code.n), 2)

    def test_polynomial_lp(self):
        code = cyclic_lp([[1, [[0, 1], [1, 1], [3, 1]]]], period=4)
        self.assertEqual((code.n, code.k), (20, 4))
        self.assertIsNotNone(code.exchange)
        from cssdist.algebra import brute_distance
        self.assertEqual(brute_distance(code.hx, code.hz, code.n, cutoff=3)[0], 3)

    def test_general_f4_independent_constituents(self):
        for p in (1, 3, 4):
            a = [[[[0, 1], [1, 2]], 3]]
            c = [[2, 1, [[-1, 3]]], [1, 0, 2]]
            with self.subTest(period=p):
                code = cyclic_lp(a, c, period=p, field=4)
                self.assertEqual(code.n, 16 * p)
                self.assertIsNone(code.exchange)

    def test_f4_presentations_preserve_code(self):
        a = [[1, 2, 3], [2, 3, [[1, 1]]]]
        raw = cyclic_lp(a, period=3, field=4)
        for mode in ('balanced', 'redundant'):
            other = cyclic_lp(a, period=3, field=4, check_basis=mode)
            self.assertTrue(same_span(raw.hx, other.hx))
            self.assertTrue(same_span(raw.hz, other.hz))

    def test_coefficient_cancellation_and_input_rejection(self):
        code = cyclic_lp([[[[0, 1], [3, 1]], 1]], period=3)
        self.assertEqual(code.document['construction']['period'], 3)
        for kwargs in ({'field': 3}, {'field': 2.0}, {'period': 0}, {'field': 2, 'check_basis': 'balanced'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                cyclic_lp([[1]], **kwargs)
        with self.assertRaises(ValueError):
            cyclic_lp([[2]])


if __name__ == '__main__':
    unittest.main()
