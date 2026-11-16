"""Deep traversal, multiword check masks, and bounded allocation failures."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cssdist import CSSCode, cyclic_lp
from cssdist.audit import audit_run
from cssdist.calibration import calibrate, audit_calibration
from cssdist.campaign import certify
from cssdist.circuit import DetectorModel
from cssdist.circuit_run import certify_circuit, audit_circuit
from cssdist.engine import memory_budget_bytes
from cssdist.portable import export_bundle, audit_bundle


class DynamicCapacityTests(unittest.TestCase):
    def test_archived_bb144_records_with_current_engine(self):
        result = subprocess.run([sys.executable, '-m', 'cssdist.benchmarks.bb144'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('recorded exclusion through 9', result.stdout)

    def test_deep_sector_and_oversized_cutoff(self):
        n = 512
        code = CSSCode.from_sparse(n, [[i, (i + 1) % n] for i in range(n)], [],
                                   cyclic_period=n)
        with tempfile.TemporaryDirectory() as tmp:
            for cutoff in (n - 1, n, n + 100):
                out = Path(tmp) / str(cutoff)
                result = certify(code, out, cutoff=cutoff, seconds_per_shard=5)
                self.assertEqual(result['sector_bounds']['Z']['upper'], n)
                if cutoff < n:
                    self.assertEqual(result['sector_bounds']['Z']['lower'], n)
                else:
                    self.assertTrue(any(j['sector'] == 'Z' and j['status'] == 'witness'
                                        for j in result['jobs']))
                self.assertEqual(audit_run(out)['sector_bounds'], result['sector_bounds'])

    def test_large_inputs_and_more_than_64_root_branches(self):
        # The only Z logical is {0,129}. Reaching it requires the last entry
        # of a 130-site check, after rejecting its first 128 possible partners.
        wide = CSSCode.from_sparse(130, [list(range(130))] + [[i] for i in range(1, 129)], [])
        many = CSSCode.from_sparse(9001, [[0, 1]] * 2050, [], witnesses={'Z': [[2]]})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'wide'
            result = certify(wide, out, cutoff=2, shards=3, split_weight=2,
                             seconds_per_shard=5)
            self.assertEqual(result['sector_bounds']['Z']['witness'], [0, 129])
            self.assertTrue(any(j['sector'] == 'Z' and j['status'] == 'witness'
                                for j in result['jobs']))
            self.assertEqual(audit_run(out)['sector_bounds'], result['sector_bounds'])
            cal = Path(tmp) / 'calibration'
            measured = calibrate(wide, cal, cutoff=2, samples=130, seconds_per_root=1)
            first = next(r for r in measured['records'] if r['sector'] == 'Z' and r['root'] == 0)
            self.assertEqual(first['status'], 'witness')
            self.assertEqual(first['witnesses'][0]['support'], [0, 129])
            self.assertEqual(audit_calibration(cal), measured)
            self.assertEqual(certify(many, Path(tmp) / 'large', cutoff=1,
                                     seconds_per_shard=5)['exact_distance'], 1)

    def test_memory_limit_is_incomplete_and_resumable(self):
        code = cyclic_lp([[1, 1]])
        with tempfile.TemporaryDirectory() as tmp:
            for profile in ('css', 'lp'):
                out = Path(tmp) / profile
                limited = certify(code, out, cutoff=1, profile=profile, memory_mib=0.0001)
                self.assertEqual(limited['status'], 'INCOMPLETE')
                self.assertEqual(limited['distance_lower_bound'], 1)
                self.assertTrue(all(j['resource_limit'] == 'memory' for j in limited['jobs']))
                self.assertTrue(all(j['nodes'] is None for j in limited['jobs']))
                self.assertEqual(audit_run(out)['status'], 'INCOMPLETE')
                archive = Path(tmp) / f'{profile}.tar.gz'
                export_bundle(out, archive)
                self.assertEqual(audit_bundle(archive)['result']['status'], 'INCOMPLETE')
                complete = certify(code, out, cutoff=1, profile=profile, resume=True)
                self.assertEqual(complete['exact_distance'], 2)
                self.assertEqual(audit_run(out)['exact_distance'], 2)
            cal = Path(tmp) / 'calibration'
            limited = calibrate(code, cal, cutoff=1, samples=1, memory_mib=0.0001)
            self.assertTrue(all(r['status'] == 'incomplete' for r in limited['records']))
            self.assertEqual(audit_calibration(cal), limited)

    def test_circuit_deep_traversal_and_memory_budget(self):
        n = 1024
        model = DetectorModel.from_sparse(n, [[i, i + 1] for i in range(n - 1)], [[0]],
                                          witnesses=[list(range(n))])
        with tempfile.TemporaryDirectory() as tmp:
            for cutoff in (n - 1, n, n + 100):
                out = Path(tmp) / str(cutoff)
                result = certify_circuit(model, out, cutoff=cutoff, seconds=15)
                self.assertEqual(result['distance_upper_bound'], n)
                self.assertEqual(result['status'], 'EXCLUDED' if cutoff < n else 'WITNESS_FOUND')
                if cutoff < n:
                    self.assertEqual(result['exact_distance'], n)
                self.assertEqual(audit_circuit(out), result)
            for window in (None, 1):
                out = Path(tmp) / f'memory-{window}'
                result = certify_circuit(model, out, cutoff=2, memory_mib=0.0001,
                                         detectors_per_layer=window)
                self.assertEqual(result['status'], 'INCOMPLETE')
                self.assertIsNone(result['distance_lower_bound'])
                self.assertEqual(audit_circuit(out), result)
                archive = Path(tmp) / f'circuit-{window}.tar.gz'
                export_bundle(out, archive)
                self.assertEqual(audit_bundle(archive)['result']['status'], 'INCOMPLETE')

    def test_memory_option_validation_and_cli(self):
        for invalid in (True, 0, -1, float('nan'), float('inf'), '1', 10**1000):
            with self.subTest(value=repr(invalid)[:20]), self.assertRaises(ValueError):
                memory_budget_bytes(invalid)
        self.assertEqual(memory_budget_bytes(1.5), 1572864)
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / 'code.json'
            cyclic_lp([[1, 1]]).save(input_path)
            proc = subprocess.run([sys.executable, '-m', 'cssdist', 'certify', str(input_path),
                                   '--cutoff', '1', '--memory-mib', '0.0001',
                                   '--out', str(Path(tmp) / 'run')], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 75, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)['status'], 'INCOMPLETE')


if __name__ == '__main__':
    unittest.main()
