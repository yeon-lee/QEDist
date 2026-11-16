"""Pauli symmetry coverage, disjoint shards, restart safety and read-only audits."""
import copy
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cssdist import StabilizerCode, product_translation_generators
from cssdist.campaign import campaign_lock
from cssdist.code import digest, json_bytes
from cssdist.portable import audit_bundle, export_bundle
from cssdist.stabilizer_campaign import search_plan, root_ranges
from cssdist.stabilizer_run import audit_stabilizer, certify_stabilizer

FIVE = ['XZZXI', 'IXZZX', 'XIXZZ', 'ZXIXZ']


def four_copies():
    rows = []
    for copy_index in range(4):
        for row in FIVE:
            rows.append(''.join(row[q // 4] if q % 4 == copy_index else 'I'
                                for q in range(20)))
    return StabilizerCode.from_paulis(rows,
        symmetry_generators=product_translation_generators((2, 2), blocks=5))


def hashes(root):
    return {p.relative_to(root).as_posix(): digest(p.read_bytes())
            for p in root.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.json'}


def rehash(root):
    (root / 'SHA256SUMS.json').write_bytes(json_bytes({'files': hashes(root)}))


class StabilizerSymmetryTests(unittest.TestCase):
    def test_cyclic_symmetry_preserves_span_with_dependent_translates(self):
        code = StabilizerCode.from_paulis(FIVE, cyclic_period=5)
        self.assertEqual(code.inspect()['symmetry_root_qubits'], [0])
        model, coverage = search_plan(code, True)
        self.assertEqual(coverage['roots_required'], 3)
        self.assertEqual(model.n, 15)
        self.assertEqual(search_plan(code, False)[1]['roots_required'], 15)

    def test_invalid_permutations_and_non_symmetries(self):
        for generators in (None, [None], [[0, 0]], [[True, 0]], [[0]], [[0, 2]]):
            with self.subTest(generators=generators), self.assertRaises(ValueError):
                StabilizerCode.from_paulis(['XI'], symmetry_generators=generators)
        for fields in ({'symmetry_generators': [[1, 0]]}, {'cyclic_period': 2}):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, 'full stabilizer space'):
                StabilizerCode.from_paulis(['XI'], **fields)
        for period in (True, 0, -1, 3, 1.5):
            with self.subTest(period=period), self.assertRaises(ValueError):
                StabilizerCode.from_paulis(['XX'], cyclic_period=period)

    def test_full_product_orbits_and_column_map(self):
        code = four_copies()
        model, coverage = search_plan(code, True)
        self.assertEqual(coverage['root_qubits'], [0, 4, 8, 12, 16])
        self.assertEqual(coverage['roots_required'], 15)
        a, b = code.symmetry_generators
        diagonal = dict(code.document, symmetry_generators=[[a[b[j]] for j in range(code.n)]])
        self.assertEqual(search_plan(StabilizerCode(diagonal), True)[1]['roots_required'], 30)
        original = code.detector_model()
        order = coverage['column_order']
        self.assertEqual(sorted(order), list(range(model.n)))
        for field in ('detector_rows', 'observable_rows', 'neutral_rows', 'witnesses'):
            restored = [sorted(order[i] for i in row) for row in model.document[field]]
            self.assertEqual(restored, original.document[field])

    def test_noncontiguous_relabeling_and_witness_mapping(self):
        code = four_copies()
        permutation = list(range(code.n))
        random.Random(4723).shuffle(permutation)
        inverse = [permutation.index(q) for q in range(code.n)]
        doc = copy.deepcopy(code.document)
        doc['stabilizers'] = [''.join(row[inverse[q]] for q in range(code.n)) for row in doc['stabilizers']]
        doc['symmetry_generators'] = [[permutation[g[inverse[q]]] for q in range(code.n)]
                                      for g in code.symmetry_generators]
        relabeled = StabilizerCode(doc)
        with tempfile.TemporaryDirectory() as tmp:
            for enabled in (False, True):
                run = Path(tmp) / str(enabled)
                result = certify_stabilizer(relabeled, run, cutoff=2, use_symmetry=enabled,
                                            shards=5, workers=2)
                self.assertEqual(result['exact_distance'], 3)
                self.assertEqual(result['roots_required'], 15 if enabled else 60)
                self.assertEqual(audit_stabilizer(run), result)
            result = certify_stabilizer(relabeled, Path(tmp) / 'witness', cutoff=3, shards=5, workers=2)
            self.assertEqual(result['distance_upper_bound'], 3)
            self.assertEqual(relabeled.check_witness(result['witness']['pauli']), result['witness'])

    def test_fixed_point_remains_in_coverage(self):
        code = StabilizerCode.from_paulis([row + 'I' for row in FIVE],
                                         symmetry_generators=[[1, 2, 3, 4, 0, 5]])
        self.assertEqual(search_plan(code, True)[1]['root_qubits'], [0, 5])
        with tempfile.TemporaryDirectory() as tmp:
            result = certify_stabilizer(code, Path(tmp) / 'run', cutoff=1, shards=6, workers=2)
            self.assertEqual(result['exact_distance'], 1)
            self.assertEqual(result['witness']['support'], [5])

    def test_noncommuting_generators_and_combined_actions(self):
        code = four_copies()
        swap = [4 * (q // 4) + {0: 1, 1: 0, 2: 2, 3: 3}[q % 4] for q in range(20)]
        cycle = [4 * (q // 4) + (q + 1) % 4 for q in range(20)]
        self.assertNotEqual([swap[cycle[q]] for q in range(20)], [cycle[swap[q]] for q in range(20)])
        explicit = StabilizerCode(dict(code.document, symmetry_generators=[swap, cycle]))
        combined = StabilizerCode(dict(code.document, symmetry_generators=[swap], cyclic_period=4))
        self.assertEqual(search_plan(explicit, True)[1], search_plan(combined, True)[1])
        self.assertEqual(search_plan(explicit, True)[1]['roots_required'], 15)


class StabilizerShardTests(unittest.TestCase):
    def test_shards_partition_roots_exactly(self):
        for roots in range(1, 20):
            for shards in (1, 2, 3, 8, 32):
                intervals = root_ranges(roots, shards)
                self.assertTrue(all(a < b for a, b in intervals))
                self.assertEqual([q for a, b in intervals for q in range(a, b)], list(range(roots)))
        for shards in (False, 0, -1, 1.5):
            with self.assertRaises(ValueError):
                root_ranges(10, shards)

    def test_serial_parallel_and_capacity_results_agree(self):
        code = StabilizerCode.from_paulis(FIVE, cyclic_period=5)
        counts = []
        with tempfile.TemporaryDirectory() as tmp:
            for expanded in (False, True):
                for shards, workers in ((1, 1), (3, 2), (99, 3)):
                    run = Path(tmp) / f'{expanded}-{shards}'
                    result = certify_stabilizer(code, run, cutoff=2, shards=shards, workers=workers,
                                                large_capacity=expanded)
                    self.assertEqual(result['exact_distance'], 3)
                    self.assertEqual(result['roots_excluded'], 3)
                    self.assertEqual(audit_stabilizer(run), result)
                    counts.append(result['nodes_in_recorded_attempts'])
        self.assertEqual(counts, [counts[0]] * len(counts))

    def test_interrupted_shards_resume_with_saved_options(self):
        code = StabilizerCode.from_paulis(FIVE, cyclic_period=5)
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / 'run'
            first = certify_stabilizer(code, run, cutoff=2, node_cap=0, shards=3, workers=2,
                                       weighted=False, neutral=False, use_symmetry=False,
                                       large_capacity=True)
            self.assertEqual(first['status'], 'INCOMPLETE')
            self.assertEqual(first['distance_lower_bound'], 1)
            old = {p: p.read_bytes() for p in run.glob('search/jobs/*/attempt-*.json')}
            result = certify_stabilizer(code, run, cutoff=2, resume=True, workers=3)
            self.assertEqual(result['exact_distance'], 3)
            self.assertEqual(result['roots_required'], 15)
            self.assertTrue(all(job['attempts'] == 2 for job in result['jobs']))
            for path, data in old.items():
                self.assertEqual(path.read_bytes(), data)
            before = hashes(run)
            with patch('cssdist.stabilizer_campaign._native_receipt', side_effect=AssertionError('reran complete job')):
                again = certify_stabilizer(code, run, cutoff=2, resume=True)
            self.assertEqual(again, result)
            self.assertEqual(hashes(run), before)

    def test_resume_only_retries_incomplete_shards_and_survives_relocation(self):
        from cssdist.stabilizer_campaign import _attempt
        code = StabilizerCode.from_paulis(FIVE, cyclic_period=5)
        def bounded(root, config, model, build, shard, seconds, node_cap, memory_bytes):
            return _attempt(root, config, model, build, shard, seconds,
                            0 if shard == 1 else node_cap, memory_bytes)
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / 'run'
            with patch('cssdist.stabilizer_campaign._attempt', side_effect=bounded):
                result = certify_stabilizer(code, run, cutoff=2, shards=3, workers=2)
            self.assertEqual(result['distance_lower_bound'], 1)
            self.assertEqual(result['roots_excluded'], 2)
            moved = Path(tmp) / 'moved'
            shutil.move(run, moved)
            # A process can stop after saving an attempt but before updating its summary.
            (moved / 'result.json').write_text('{}')
            resumed = certify_stabilizer(code, moved, cutoff=2, resume=True, workers=2)
            self.assertEqual(resumed['exact_distance'], 3)
            self.assertEqual([job['attempts'] for job in resumed['jobs']], [1, 2, 1])
            with patch('subprocess.Popen', side_effect=AssertionError('audit executed code')):
                self.assertEqual(audit_stabilizer(moved), resumed)
                export_bundle(moved, Path(tmp) / 'proof.tar.gz')
                self.assertEqual(audit_bundle(Path(tmp) / 'proof.tar.gz')['result'], resumed)

    def test_resume_rejects_changed_problem_and_controls(self):
        code = StabilizerCode.from_paulis(FIVE, cyclic_period=5)
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / 'run'
            certify_stabilizer(code, run, cutoff=2, shards=3, node_cap=0)
            changes = [{'shards': 2}, {'use_symmetry': False}, {'weighted': False},
                       {'neutral': False}, {'large_capacity': True}]
            for options in changes:
                with self.subTest(options=options), self.assertRaisesRegex(ValueError, 'Resume requires'):
                    certify_stabilizer(code, run, cutoff=2, resume=True, **options)
            with self.assertRaisesRegex(ValueError, 'Resume requires'):
                certify_stabilizer(code, run, cutoff=3, resume=True)
            with self.assertRaises(ValueError):
                certify_stabilizer(StabilizerCode.from_paulis(FIVE), run, cutoff=2, resume=True)
            with self.assertRaisesRegex(ValueError, 'already exists'):
                certify_stabilizer(code, run, cutoff=2)
            with self.assertRaisesRegex(ValueError, 'missing'):
                certify_stabilizer(code, Path(tmp) / 'missing', cutoff=2, resume=True)

    def test_lock_prevents_two_writers_and_export(self):
        code = StabilizerCode.from_paulis(FIVE)
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / 'run'
            certify_stabilizer(code, run, cutoff=2, node_cap=0)
            with campaign_lock(run):
                with self.assertRaisesRegex(ValueError, 'locked'):
                    certify_stabilizer(code, run, cutoff=2, resume=True)
                with self.assertRaisesRegex(ValueError, 'locked'):
                    export_bundle(run, Path(tmp) / 'busy.tar.gz')

    def test_memory_limited_shards_resume_with_more_memory(self):
        code = StabilizerCode.from_paulis(FIVE, cyclic_period=5)
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / 'run'
            first = certify_stabilizer(code, run, cutoff=2, shards=3, workers=2, memory_mib=0.0001)
            self.assertEqual(first['status'], 'INCOMPLETE')
            self.assertEqual(first['roots_excluded'], 0)
            result = certify_stabilizer(code, run, cutoff=2, resume=True, memory_mib=16)
            self.assertEqual(result['exact_distance'], 3)
            self.assertTrue(all(job['attempts'] == 2 for job in result['jobs']))
            self.assertEqual(audit_stabilizer(run), result)

    def test_missing_or_tampered_shard_cannot_certify(self):
        code = StabilizerCode.from_paulis(FIVE, cyclic_period=5)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            certify_stabilizer(code, source, cutoff=2, shards=3)
            for corruption in ('missing', 'range', 'roots_completed', 'coverage', 'duplicated'):
                run = Path(tmp) / corruption
                shutil.copytree(source, run)
                attempt = run / 'search/jobs/000001/attempt-000001.json'
                if corruption == 'missing':
                    attempt.unlink()
                elif corruption == 'coverage':
                    path = run / 'search/coverage.json'
                    data = json.loads(path.read_text())
                    data['roots_required'] -= 1
                    path.write_bytes(json_bytes(data))
                    metadata_path = run / 'stabilizer_run.json'
                    metadata = json.loads(metadata_path.read_text())
                    metadata['files']['search/coverage.json'] = digest(path.read_bytes())
                    metadata_path.write_bytes(json_bytes(metadata))
                elif corruption == 'duplicated':
                    shutil.copyfile(run / 'search/jobs/000000/attempt-000001.json', attempt)
                else:
                    record = json.loads(attempt.read_text())
                    event = json.loads(record['receipt']['stdout'])
                    if corruption == 'range':
                        event['root_begin'] = 0
                    else:
                        event['roots_completed'] = 0
                    record['receipt']['stdout'] = json.dumps(event) + '\n'
                    record['receipt_sha256'] = digest(json_bytes(record['receipt']))
                    attempt.write_bytes(json_bytes(record))
                rehash(run)
                with self.subTest(corruption=corruption), self.assertRaises(ValueError):
                    audit_stabilizer(run)

    def test_cli_parallel_resume_and_disable_symmetry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = root / 'code.json'
            StabilizerCode.from_paulis(FIVE, cyclic_period=5).save(code)
            command = [sys.executable, '-m', 'cssdist', 'certify-stabilizer', str(code),
                       '--cutoff', '2', '--out', str(root / 'run')]
            first = subprocess.run(command + ['--shards', '3', '--workers', '2', '--node-cap', '0',
                                             '--no-symmetry', '--no-weighted-pruning'],
                                   capture_output=True, text=True)
            self.assertEqual(first.returncode, 75, first.stderr)
            self.assertEqual(json.loads(first.stdout)['status'], 'INCOMPLETE')
            again = subprocess.run(command + ['--resume', '--workers', '3', '--seconds-per-shard', '30'],
                                   capture_output=True, text=True)
            self.assertEqual(again.returncode, 0, again.stderr)
            result = json.loads(again.stdout)
            self.assertEqual(result['exact_distance'], 3)
            self.assertEqual(result['roots_required'], 15)


if __name__ == '__main__':
    unittest.main()
