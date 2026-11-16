"""Check physical LP layouts on independently expanded S3 constructions."""
import copy
from contextlib import redirect_stdout
import io
from itertools import combinations
import json
from pathlib import Path
import tempfile
import unittest

from cssdist import CSSCode, cyclic_lp
from cssdist.algebra import basis, remainder, support
from cssdist.audit import audit_run, configuration
from cssdist.campaign import certify
from cssdist.cli import load_input, main
from cssdist.lp_blocks import layout, search_problems
from cssdist.portable import audit_bundle, export_bundle


def s3_multiply(g, h):
    """Index r^a s^b by 2a+b, with r^3=s^2=1 and srs=r^-1."""
    a, b = divmod(g, 2)
    c, d = divmod(h, 2)
    return 2 * ((a + (-1)**b * c) % 3) + (b + d) % 2


def s3_lp(a, c, field=2):
    """Expand small test inputs by forming left/right permutation matrices."""
    rho = {1: ((1, 0), (0, 1)), 2: ((0, 1), (1, 1)), 3: ((1, 1), (1, 0))}
    components = 1 if field == 2 else 2
    size = 6 * components
    ra, sa, rc, sc = len(a), len(a[0]), len(c), len(c[0])

    def operator(terms, left):
        matrix = [[0] * size for _ in range(size)]
        for group_element, coefficient in terms:
            for g in range(6):
                image = s3_multiply(group_element, g) if left else s3_multiply(g, group_element)
                for alpha in range(components):
                    for beta in range(components):
                        value = coefficient if field == 2 else rho[coefficient][alpha][beta]
                        matrix[alpha * 6 + image][beta * 6 + g] ^= value
        return matrix

    left = [[operator(entry, True) for entry in row] for row in a]
    right = [[operator(entry, False) for entry in row] for row in c]
    hx = [0] * (ra * sc * size)
    hz = [0] * (sa * rc * size)

    def place(rows, row_block, column_block, matrix, transposed=False):
        for i in range(size):
            for j in range(size):
                value = matrix[j][i] if transposed else matrix[i][j]
                if value:
                    rows[row_block * size + i] ^= 1 << (column_block * size + j)

    for i in range(ra):
        for b in range(sc):
            for x in range(sa):
                place(hx, i * sc + b, x * sc + b, left[i][x])
            for j in range(rc):
                place(hx, i * sc + b, sa * sc + i * rc + j, right[j][b], True)
    for x in range(sa):
        for j in range(rc):
            for b in range(sc):
                place(hz, x * rc + j, x * sc + b, right[j][b])
            for i in range(ra):
                place(hz, x * rc + j, sa * sc + i * rc + j, left[i][x], True)
    return CSSCode.from_sparse((sa * sc + ra * rc) * size, list(map(support, hx)),
                               list(map(support, hz)),
                               lp_layout={'A_shape': [ra, sa], 'C_shape': [rc, sc], 'block_size': size})


def small_distances(code, maximum=4):
    distances = {}
    for weight in range(1, maximum + 1):
        for sites in combinations(range(code.n), weight):
            word = sum(1 << q for q in sites)
            for sector in ('X', 'Z'):
                if sector not in distances and code.is_logical(word, sector):
                    distances[sector] = weight
            if len(distances) == 2:
                return distances
    raise AssertionError('Test fixture needs a larger independent enumeration cutoff')


class NonAbelianLPTests(unittest.TestCase):
    def test_example_matches_left_right_construction_and_exact_search(self):
        fixture = Path(__file__).resolve().parents[1] / 'examples/nonabelian_lp.json'
        code = load_input(fixture)
        reference = s3_lp([[[(0, 1), (2, 1)], [(1, 1)]]],
                          [[[(0, 1), (1, 1)], [(2, 1)]]])
        self.assertEqual((code.hx, code.hz), (reference.hx, reference.hz))
        self.assertEqual(code.period, 1)
        self.assertEqual(layout(code), (2, 2, 6))
        distances = small_distances(code)
        with tempfile.TemporaryDirectory() as directory:
            for profile in ('css', 'lp'):
                for cutoff in sorted({max(1, min(distances.values()) - 1), max(distances.values())}):
                    result = certify(code, Path(directory) / f'{profile}-{cutoff}', cutoff=cutoff,
                                     profile=profile, shards=2, workers=2)
                    for sector, distance in distances.items():
                        bound = result['sector_bounds'][sector]
                        self.assertEqual(bound['lower'] > cutoff, distance > cutoff)
                        self.assertLessEqual(bound['lower'], distance)
                        self.assertGreaterEqual(bound['upper'], distance)

    def test_noncommuting_generators_and_no_symmetry(self):
        code = s3_lp([[[(0, 1)], [(0, 1)]]], [[[(0, 1), (1, 1)], [(2, 1)]]])
        document = copy.deepcopy(code.document)
        generators = [[6 * (q // 6) + s3_multiply(h, q % 6) for q in range(code.n)]
                      for h in (2, 1)]
        first, second = generators
        self.assertNotEqual([first[second[q]] for q in range(code.n)],
                            [second[first[q]] for q in range(code.n)])
        document['symmetry_generators'] = generators
        code = CSSCode(document)
        parts = search_problems(code, configuration(code, 1, 2, 1, profile='lp'))
        for sector in ('X', 'Z'):
            self.assertEqual(len(parts[sector + '-anchor'].roots(1)), 1)
            self.assertEqual(len(parts[sector + '-stripe'].roots(1)), 2)
        distance = min(small_distances(code).values())
        with tempfile.TemporaryDirectory() as directory:
            for symmetry in (False, True):
                result = certify(code, Path(directory) / str(symmetry), cutoff=max(1, distance - 1),
                                 profile='lp', shards=2, workers=2, use_symmetry=symmetry)
                self.assertEqual(result['exact_distance'], distance)

    def test_quaternary_physical_blocks_and_local_stabilizers(self):
        code = s3_lp([[[(0, 2), (2, 2)]]], [[[(0, 3), (1, 3)]]], field=4)
        self.assertEqual(layout(code), (1, 1, 12))
        parts = search_problems(code, configuration(code, 1, 1, 1, profile='lp'))
        for sector in ('X', 'Z'):
            local = parts[sector + '-stripe']
            stabilizers = basis(local.stabilizers)
            for word in range(1 << local.n):
                if all((row & word).bit_count() % 2 == 0 for row in local.checks):
                    self.assertEqual(bool(remainder(word, stabilizers)), code.is_logical(word, sector))
        distances = small_distances(code)
        with tempfile.TemporaryDirectory() as directory:
            for cutoff in (min(distances.values()) - 1, max(distances.values())):
                result = certify(code, Path(directory) / str(cutoff), cutoff=cutoff, profile='lp')
                for sector, distance in distances.items():
                    bound = result['sector_bounds'][sector]
                    self.assertEqual(bound['lower'] > cutoff, distance > cutoff)
                    self.assertLessEqual(bound['lower'], distance)
                    self.assertGreaterEqual(bound['upper'], distance)

    def test_unequal_and_rank_deficient_constituents(self):
        identity = [(0, 1)]
        cases = [s3_lp([[identity, []]], [[[]]]),
                 s3_lp([[identity], [identity]], [[[]]]),
                 s3_lp([[[]]], [[[]]])]
        with tempfile.TemporaryDirectory() as directory:
            for index, code in enumerate(cases):
                distances = small_distances(code)
                result = certify(code, Path(directory) / str(index), cutoff=max(distances.values()),
                                 profile='lp', shards=2, workers=2)
                self.assertEqual(result['exact_distance'], min(distances.values()))

    def test_invalid_layout_and_cyclic_alignment(self):
        code = s3_lp([[[(0, 1)], [(0, 1)]]], [[[(0, 1)], [(0, 1)]]])
        valid = code.document['lp_layout']
        invalid = [None, [], {}, {**valid, 'extra': 1}]
        for shape in ([], [1], [1, 2, 3], [0, 2], [True, 2], [1, '2']):
            invalid.append({**valid, 'A_shape': shape})
            invalid.append({**valid, 'C_shape': shape})
        for size in (0, -1, True, '6', 5):
            invalid.append({**valid, 'block_size': size})
        for declaration in invalid:
            with self.subTest(declaration=declaration):
                document = copy.deepcopy(code.document)
                document['lp_layout'] = declaration
                with self.assertRaises(ValueError):
                    layout(CSSCode(document))
        misaligned = CSSCode.from_sparse(30, [], [], cyclic_period=10, lp_layout=valid)
        with self.assertRaisesRegex(ValueError, 'divisible'):
            search_problems(misaligned, configuration(misaligned, 1, 1, 1, profile='lp'))
        parts = search_problems(misaligned, configuration(misaligned, 1, 1, 1,
                                                          use_symmetry=False, profile='lp'))
        self.assertEqual(len(parts), 4)

    def test_physical_stripe_checks_and_cyclic_metadata_agreement(self):
        declaration = {'A_shape': [1, 2], 'C_shape': [1, 2], 'block_size': 6}
        for checks, message in (([[0, 6]], 'couple'), ([[0]], 'different')):
            with self.subTest(checks=checks):
                code = CSSCode.from_sparse(30, checks, [], lp_layout=declaration)
                with self.assertRaisesRegex(ValueError, message):
                    search_problems(code, configuration(code, 1, 1, 1, profile='lp'))
        cyclic = cyclic_lp([[1, 1]], period=3)
        document = copy.deepcopy(cyclic.document)
        document['lp_layout'] = {**declaration, 'block_size': 3}
        self.assertEqual(layout(CSSCode(document)), layout(cyclic))
        document['lp_layout'] = {'A_shape': [2, 1], 'C_shape': [2, 1], 'block_size': 3}
        with self.assertRaisesRegex(ValueError, 'disagrees'):
            layout(CSSCode(document))

    def test_cli_resume_and_portable_evidence(self):
        fixture = Path(__file__).resolve().parents[1] / 'examples/nonabelian_lp.json'
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(['inspect', str(fixture), '--profile', 'lp']), 0)
        inspected = json.loads(output.getvalue())
        self.assertEqual(inspected['verified_cyclic_period'], 1)
        self.assertEqual(set(inspected['lp_search_tasks']),
                         {'X-anchor', 'X-stripe', 'Z-anchor', 'Z-stripe'})
        code = load_input(fixture)
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / 'run'
            initial = certify(code, run, cutoff=2, profile='lp', shards=2, node_cap=1)
            self.assertEqual(initial['status'], 'INCOMPLETE')
            completed = certify(code, run, cutoff=2, profile='lp', shards=2, workers=2, resume=True)
            self.assertEqual(audit_run(run)['sector_bounds'], completed['sector_bounds'])
            archive = Path(directory) / 'evidence.tar.gz'
            export_bundle(run, archive)
            self.assertEqual(audit_bundle(archive)['status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
