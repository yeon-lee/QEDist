"""Joint-orbit coverage, independent audits and physical subgroup comparisons."""
import copy
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from cssdist import CSSCode, cyclic_lp, product_translation_generators
from cssdist.algebra import permute, support
from cssdist.audit import audit_run, configuration
from cssdist.calibration import audit_calibration, calibrate, root_schedule
from cssdist.campaign import certify
from cssdist.code import digest, json_bytes
from cssdist.lp_blocks import search_problems
from cssdist.portable import audit_bundle, export_bundle
from cssdist.symmetry import orbit_representatives, symmetry_text
from test_algebra_and_inputs import oracle


def toric_three():
    def site(axis, x, y):
        return axis * 9 + (x % 3) * 3 + y % 3
    hx, hz = [], []
    for x in range(3):
        for y in range(3):
            hx.append([site(0, x, y), site(0, x-1, y), site(1, x, y), site(1, x, y-1)])
            hz.append([site(0, x, y), site(0, x, y+1), site(1, x, y), site(1, x+1, y)])
    return CSSCode.from_sparse(18, hx, hz,
        symmetry_generators=product_translation_generators((3, 3), blocks=2))


class ProductSymmetryTests(unittest.TestCase):
    def test_independent_axes_and_diagonal(self):
        generators = product_translation_generators((2, 3, 4), blocks=2)
        self.assertEqual(orbit_representatives(48, generators), [0, 24])
        diagonal = [generators[0][generators[1][generators[2][j]]] for j in range(48)]
        self.assertEqual(len(orbit_representatives(48, [diagonal])), 4)
        for a in generators:
            for b in generators:
                self.assertEqual([a[b[j]] for j in range(48)], [b[a[j]] for j in range(48)])
        for factors in ([], [0, 2], [True], [1.5]):
            with self.assertRaises(ValueError):
                product_translation_generators(factors)
        with self.assertRaises(ValueError):
            product_translation_generators([2], blocks=0)

    def test_generator_validation_and_row_spaces(self):
        # The translated last row is a sum of rows in this presentation.
        code = CSSCode.from_sparse(3, [[0, 1], [1, 2]], [],
                                   symmetry_generators=[[1, 2, 0], [1, 0, 2]])
        self.assertEqual(code.inspect()['symmetry_orbit_representatives'], [0])
        for generators in (None, [None], [[0, 0, 2]], [[True, 0, 2]], [[0, 1]], [[0, 1, 3]]):
            with self.subTest(generators=generators), self.assertRaises(ValueError):
                CSSCode.from_sparse(3, [[0, 1]], [], symmetry_generators=generators)
        with self.assertRaisesRegex(ValueError, 'both check spaces'):
            CSSCode.from_sparse(3, [[0, 1]], [], symmetry_generators=[[1, 2, 0]])

    def test_cyclic_action_combines_with_extra_generators(self):
        data = toric_three().document
        data['cyclic_period'] = 3
        data['symmetry_generators'] = data['symmetry_generators'][:1]
        code = CSSCode(data)
        self.assertEqual(code.inspect()['symmetry_orbit_representatives'], [0, 9])
        _, schedule = root_schedule(code, 99, 5, use_symmetry=False)
        self.assertTrue(all(set(roots) == set(range(18)) for roots in schedule.values()))

    def test_fixed_point_logical_is_searched(self):
        data = toric_three().document
        data['n'] = 19
        data['symmetry_generators'] = [g + [18] for g in data['symmetry_generators']]
        code = CSSCode(data)
        self.assertEqual(code.inspect()['symmetry_orbit_representatives'], [0, 9, 18])
        with tempfile.TemporaryDirectory() as tmp:
            result = certify(code, Path(tmp)/'fixed', cutoff=1)
            self.assertTrue(all(job['status'] == 'witness' for job in result['jobs']))
            self.assertEqual(result['sector_bounds']['X']['witness'], [18])
            self.assertEqual(result['sector_bounds']['Z']['witness'], [18])

    def test_noncontiguous_orbits_and_exhaustive_oracle(self):
        original = toric_three()
        distances = {s: oracle(*original.sector(s)[:2], original.n) for s in ('X', 'Z')}
        self.assertEqual(distances, {'X': 3, 'Z': 3})
        relabel = list(range(original.n))
        random.Random(812).shuffle(relabel)
        inverse = [relabel.index(j) for j in range(original.n)]
        generators = [[relabel[g[inverse[j]]] for j in range(original.n)]
                      for g in original.symmetry_generators]
        code = CSSCode.from_sparse(original.n,
            [support(permute(row, relabel)) for row in original.hx],
            [support(permute(row, relabel)) for row in original.hz], symmetry_generators=generators)
        with tempfile.TemporaryDirectory() as tmp:
            for enabled in (False, True):
                run = Path(tmp)/str(enabled)
                result = certify(code, run, cutoff=2, use_symmetry=enabled, shards=3, workers=2)
                self.assertEqual(result['exact_distance'], 3)
                self.assertEqual(audit_run(run)['exact_distance'], 3)
            witness = certify(code, Path(tmp)/'witness', cutoff=3)
            self.assertEqual(witness['distance_upper_bound'], 3)
            self.assertEqual(witness['status'], 'WITNESS_FOUND')

    def test_resume_calibration_and_portable(self):
        code = toric_three()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root/'run'
            certify(code, run, cutoff=2, shards=2)
            shutil.rmtree(run/'jobs/Z/000001')
            self.assertEqual(audit_run(run)['status'], 'INCOMPLETE')
            self.assertEqual(certify(code, run, cutoff=2, shards=2, resume=True)['exact_distance'], 3)
            export_bundle(run, root/'proof.tar.gz')
            self.assertEqual(audit_bundle(root/'proof.tar.gz')['result']['exact_distance'], 3)
            period, schedule = root_schedule(code, 99, 5)
            self.assertEqual(period, 1)
            self.assertTrue(all(set(roots) == {0, 1} for roots in schedule.values()))
            result = calibrate(code, root/'cal', cutoff=2, samples=99)
            self.assertEqual(audit_calibration(root/'cal'), result)
            self.assertTrue(all(s['population_roots'] == 2 for s in result['sectors'].values()))
            (root/'cal/inputs/X.symmetry').write_text('18 0\n')
            with self.assertRaisesRegex(ValueError, 'symmetry input changed'):
                audit_calibration(root/'cal')

    def test_tampered_roots_and_permutations(self):
        code = toric_three()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'run'
            certify(code, root, cutoff=2)
            receipt_path = next(root.glob('jobs/X/*/attempt-*/receipt.json'))
            receipt = json.loads(receipt_path.read_text())
            receipt['terminal']['root_representatives'] = [0]
            stdout = (json.dumps(receipt['terminal']) + '\n').encode()
            receipt['stdout_sha256'] = digest(stdout)
            receipt_path.write_bytes(json_bytes(receipt))
            (receipt_path.parent/'stdout.jsonl').write_bytes(stdout)
            with self.assertRaisesRegex(ValueError, 'verified joint orbits'):
                audit_run(root)
            # Native validation is independent of the Python input checks.
            bad = list(range(code.n))
            bad[0], bad[1] = bad[1], bad[0]
            (root/'bad.symmetry').write_text(symmetry_text(code.n, [bad]))
            proc = subprocess.run([str(root/'engine/exact'), 'inputs/X.mat', '1', '2', '5',
                '--shard', '0', '1', '2', '1000000', 'symmetry-file=bad.symmetry'],
                cwd=root, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertIn('does not preserve', proc.stderr)
            # Preserving the syndrome space alone is insufficient.
            stabilizer_only = CSSCode.from_sparse(4, [], [[0, 1]])
            (root/'stabilizer.mat').write_text(stabilizer_only.native_text('Z'))
            (root/'bad.symmetry').write_text(symmetry_text(4, [[1, 2, 3, 0]]))
            proc = subprocess.run([str(root/'engine/exact'), 'stabilizer.mat', '1', '1', '5',
                '--shard', '0', '1', '1', '1000000', 'symmetry-file=bad.symmetry'],
                cwd=root, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertIn('stabilizer space', proc.stderr)

    def test_input_audit_reconstructs_generators(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'run'
            certify(toric_three(), root, cutoff=2)
            altered = b'18 0\n'
            (root/'inputs/X.symmetry').write_bytes(altered)
            campaign_path = root/'campaign.json'
            campaign = json.loads(campaign_path.read_text())
            campaign['symmetry_sha256']['X'] = digest(altered)
            campaign_path.write_bytes(json_bytes(campaign))
            with self.assertRaisesRegex(ValueError, 'verified physical symmetries'):
                audit_run(root)

    def test_lp_product_action_with_nonzero_search(self):
        constituent = [[1, 1, 0], [0, 1, 1], [1, 0, 1]]
        for field in (2, 4):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                code = cyclic_lp(constituent, period=2, field=field)
                fiber = 2 if field == 2 else 4
                generators = []
                for axis in (0, 1):
                    permutation = []
                    for q in range(code.n):
                        block, offset = divmod(q, fiber)
                        half, local = divmod(block, 9)
                        a, b = divmod(local, 3)
                        a = (a + (axis == 0)) % 3
                        b = (b + (axis == 1)) % 3
                        permutation.append((half * 9 + a * 3 + b) * fiber + offset)
                    generators.append(permutation)
                data = dict(code.document, symmetry_generators=generators)
                product = CSSCode(data)
                for profile in ('css', 'lp'):
                    result = certify(product, Path(tmp)/profile, cutoff=2, profile=profile, shards=2)
                    self.assertEqual(result['exact_distance'], 3)
                    self.assertGreater(result['nodes_in_recorded_attempts'], 0)

    def test_lp_induced_actions_and_rejected_block_mixing(self):
        code = cyclic_lp([[1, 1]], period=2)
        # Exchange either tensor index independently, fixing the second block.
        generators = []
        for mask in (1, 2):
            generators.append([(q // 2 ^ mask) * 2 + q % 2 if q < 8 else q for q in range(10)])
        code = cyclic_lp([[1, 1]], period=2, symmetry_generators=generators)
        config = configuration(code, 1, 1, 1, profile='lp')
        parts = search_problems(code, config)
        self.assertEqual(parts['Z-stripe'].roots(code.period), [0])
        self.assertEqual(parts['Z-anchor'].roots(code.period), [8])
        with tempfile.TemporaryDirectory() as tmp:
            result = certify(code, Path(tmp)/'lp', cutoff=1, profile='lp', shards=2)
            self.assertEqual(result['exact_distance'], 2)
        # An unconstrained code admits this physical action, but the declared
        # LP partition is incompatible with it and must be rejected explicitly.
        zero = cyclic_lp([[0, 0]], period=2)
        data = copy.deepcopy(zero.document)
        data['symmetry_generators'] = [[8, *range(1, 8), 0, 9]]
        mixed = CSSCode(data)
        with self.assertRaisesRegex(ValueError, 'both tensor blocks'):
            search_problems(mixed, configuration(mixed, 1, 1, 1, profile='lp'))


if __name__ == '__main__':
    unittest.main()
