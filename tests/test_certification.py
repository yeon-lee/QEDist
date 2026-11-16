import copy
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

from cssdist import CSSCode, cyclic_lp
from cssdist.algebra import support
from cssdist.audit import audit_run
from cssdist.campaign import certify
from cssdist.code import digest, json_bytes
from test_algebra_and_inputs import oracle


def steane():
    rows = [[0, 2, 4, 6], [1, 2, 5, 6], [3, 4, 5, 6]]
    return CSSCode.from_sparse(7, rows, rows, sector_exchange=list(range(7)), name='Steane')


class CertificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cssdist-test-')
        self.root = Path(self.temp.name)
        self.counter = 0

    def tearDown(self):
        self.temp.cleanup()

    def run_code(self, code, cutoff, **kwargs):
        self.counter += 1
        path = self.root / str(self.counter)
        result = certify(code, path, cutoff=cutoff, seconds_per_shard=5, **kwargs)
        return result, path

    def test_steane_exact_and_known_witness(self):
        result, root = self.run_code(steane(), 2, shards=3, workers=3)
        self.assertEqual(result['exact_distance'], 3)
        self.assertEqual(audit_run(root)['exact_distance'], 3)
        result, _ = self.run_code(steane(), 3)
        self.assertEqual(result['distance_upper_bound'], 3)
        self.assertEqual(result['status'], 'WITNESS_FOUND')
        self.assertEqual(result['distance_lower_bound'], 1)

    def test_asymmetric_sectors_are_both_searched(self):
        code = cyclic_lp([[1, 1]], [[1, 1, 0], [0, 1, 1]])
        result, _ = self.run_code(code, 2)
        self.assertEqual({job['sector'] for job in result['jobs']}, {'X', 'Z'})
        self.assertEqual(result['sector_bounds']['Z']['upper'], 2)
        self.assertEqual(result['sector_bounds']['Z']['lower'], 1)
        self.assertEqual(result['sector_bounds']['X']['lower'], 3)
        self.assertIsNone(result['exact_distance'])
        result, _ = self.run_code(code, 1)
        self.assertEqual(result['exact_distance'], 2)

    def test_random_css_against_direct_sets(self):
        rng = random.Random(104006)
        for case in range(14):
            n = rng.randrange(4, 9)
            x = [rng.randrange(1 << n) for _ in range(rng.randrange(1, 4))]
            orthogonal = [v for v in range(1 << n) if all((v & row).bit_count() % 2 == 0 for row in x)]
            z = [rng.choice(orthogonal) for _ in range(rng.randrange(3))]
            code = CSSCode.from_sparse(n, list(map(support, x)), list(map(support, z)))
            if code.k == 0:
                continue
            dx, dz = oracle(z, x, n), oracle(x, z, n)
            d = min(dx, dz)
            with self.subTest(case=case, distance=d):
                if d > 1:
                    result, _ = self.run_code(code, d - 1)
                    self.assertTrue(result['all_required_shards_excluded'])
                    self.assertEqual(result['distance_lower_bound'], d)
                result, _ = self.run_code(code, d, coset_pruning=case % 2 == 0)
                self.assertEqual(result['distance_upper_bound'], d)
                self.assertFalse(result['all_required_shards_excluded'])

    def test_no_checks_and_degenerate_stabilizers(self):
        for code in (CSSCode.from_sparse(3, [], []),
                     CSSCode.from_sparse(3, [], [[0, 1], [1, 2], [0, 1], []])):
            result, _ = self.run_code(code, 1)
            self.assertEqual(result['exact_distance'], 1)

    def test_symmetry_shards_and_pruning_agree(self):
        code = cyclic_lp([[1, [[0, 1], [1, 1], [3, 1]]]], period=4)
        for symmetry, pruning, shards in ((True, True, 1), (True, False, 3), (False, True, 2)):
            with self.subTest(symmetry=symmetry, pruning=pruning, shards=shards):
                result, _ = self.run_code(code, 2, use_symmetry=symmetry,
                                          coset_pruning=pruning, shards=shards, workers=2)
                self.assertTrue(result['all_required_shards_excluded'])
                self.assertEqual(result['distance_lower_bound'], 3)

    def test_toric_code_without_declared_symmetry(self):
        # Vertices and faces of a periodic L x L square lattice; edge qubits.
        for length in (3, 4):
            edge = lambda x, y, axis: axis * length * length + (x % length) * length + y % length
            hx, hz = [], []
            for x in range(length):
                for y in range(length):
                    hx.append([edge(x, y, 0), edge(x - 1, y, 0),
                               edge(x, y, 1), edge(x, y - 1, 1)])
                    hz.append([edge(x, y, 0), edge(x, y + 1, 0),
                               edge(x, y, 1), edge(x + 1, y, 1)])
            code = CSSCode.from_sparse(2 * length * length, hx, hz)
            self.assertEqual(code.k, 2)
            result, _ = self.run_code(code, length - 1, shards=2, workers=2)
            self.assertEqual(result['exact_distance'], length)

    def test_no_credit_from_altered_engine_source(self):
        _, root = self.run_code(steane(), 2)
        source = root / 'engine/exact.cpp'
        source.write_text(source.read_text() + '\n// changed\n')
        with self.assertRaisesRegex(ValueError, 'source differs'):
            audit_run(root)

    def test_all_shipped_inputs_validate(self):
        from cssdist.cli import load_input
        from cssdist.circuit import DetectorModel
        from cssdist.stabilizer import StabilizerCode
        root = Path(__file__).resolve().parents[1]
        for path in sorted((root / 'examples').rglob('*.json')):
            if path.name in ('IMPORT_REPORT.json', 'paper.json'):
                continue
            with self.subTest(path=path.name):
                schema = json.loads(path.read_text()).get('schema')
                if schema == 'qedist.stabilizer.v1':
                    code = StabilizerCode.load(path)
                    self.assertGreater(code.k, 0)
                    self.assertEqual(len(code.logical_basis()), 2 * code.k)
                    for witness in code.document['witnesses']:
                        self.assertGreater(code.check_witness(witness)['weight'], 0)
                    continue
                if schema == 'qedist.detector.v1':
                    model = DetectorModel.load(path)
                    self.assertGreater(model.n, 0)
                    for witness in model.document['witnesses']:
                        self.assertGreater(model.check_witness(witness)['weight'], 0)
                    continue
                code = load_input(path)
                self.assertGreater(code.k, 0)
                for sector, word in code.upper_witnesses().items():
                    self.assertTrue(code.is_logical(word, sector))

    def test_incomplete_then_resume_keeps_evidence(self):
        code = steane()
        result, root = self.run_code(code, 2, shards=2, workers=2, node_cap=1)
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['distance_lower_bound'], 1)
        old = {p: p.read_bytes() for p in root.glob('jobs/*/*/attempt-*/receipt.json')}
        complete = certify(code, root, cutoff=2, shards=2, workers=2, resume=True, seconds_per_shard=5)
        self.assertEqual(complete['exact_distance'], 3)
        for path, contents in old.items():
            self.assertEqual(path.read_bytes(), contents)
        reused = certify(code, root, cutoff=2, shards=2, resume=True)
        self.assertEqual(reused['last_invocation']['jobs_run'], 0)
        self.assertEqual(reused['last_invocation']['jobs_reused'], 2)
        with self.assertRaisesRegex(ValueError, 'same code'):
            certify(code, root, cutoff=1, shards=2, resume=True)

    def test_missing_shard_never_credits_exclusion(self):
        result, root = self.run_code(steane(), 2, shards=2)
        shutil.rmtree(root / 'jobs/Z/000001')
        incomplete = audit_run(root)
        self.assertEqual(incomplete['distance_lower_bound'], 1)
        self.assertEqual(incomplete['status'], 'INCOMPLETE')

    def test_tampered_input_transcript_and_summary(self):
        _, root = self.run_code(steane(), 2)
        (root / 'result.json').write_text('{"exact_distance":999}')
        self.assertEqual(audit_run(root)['exact_distance'], 3)
        transcript = next(root.glob('jobs/*/*/attempt-*/stdout.jsonl'))
        original = transcript.read_bytes()
        transcript.write_bytes(original + b'\n')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            audit_run(root)
        transcript.write_bytes(original)
        matrix = root / 'inputs/Z.mat'
        matrix.write_text(matrix.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'Native matrix'):
            audit_run(root)

    def test_incomplete_root_and_frontier_records_rejected(self):
        for change in ('roots_completed', 'frontier_owned'):
            _, root = self.run_code(steane(), 2, shards=2)
            path = next(root.glob('jobs/*/*/attempt-*/receipt.json'))
            receipt = json.loads(path.read_text())
            result = copy.deepcopy(receipt['terminal'])
            result[change] = 0 if change == 'roots_completed' else result[change] + 1
            transcript = json_bytes(result)
            (path.parent / 'stdout.jsonl').write_bytes(transcript)
            receipt['stdout_sha256'] = digest(transcript)
            receipt['terminal'] = result
            path.write_bytes(json_bytes(receipt))
            with self.subTest(change=change), self.assertRaises(ValueError):
                audit_run(root)

    def test_validation_survives_python_optimization(self):
        path = self.root / 'bad.json'
        path.write_text(json.dumps({'schema': 'cssdist.code.v1', 'n': 2, 'hx': [[0]], 'hz': [[0]]}))
        result = subprocess.run([sys.executable, '-O', '-m', 'cssdist', 'inspect', str(path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('commutation', result.stderr)

    def test_cli_roundtrip(self):
        path = self.root / 'code.json'
        steane().save(path)
        result = subprocess.run([sys.executable, '-m', 'cssdist', 'certify', str(path),
                                 '--out', str(self.root / 'cli-run'), '--cutoff', '2'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['exact_distance'], 3)


if __name__ == '__main__':
    unittest.main()
