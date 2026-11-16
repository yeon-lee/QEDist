"""Automatic and explicit storage selection, including saved engine identities."""
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
from cssdist.circuit_run import (NATIVE as CIRCUIT_NATIVE, _RECURSIVE_SOURCES,
                                audit_circuit, certify_circuit)
from cssdist.code import digest, json_bytes
from cssdist.engine import (NATIVE_INTEGER_MAX, _FIXED_STORAGE_EXACT, _FIXED_STORAGE_SOURCES,
                            profile_directory, select_code_capacity, source_hashes)


def read_json(path):
    return json.loads(path.read_text())


class CapacitySelectionTests(unittest.TestCase):
    def test_fast_sources_match_released_engines(self):
        for profile in ('css', 'lp'):
            expected = {**_FIXED_STORAGE_SOURCES, 'exact.cpp': _FIXED_STORAGE_EXACT[profile]}
            self.assertEqual(source_hashes(profile_directory(profile, large_capacity=False)), expected)
        self.assertEqual(source_hashes(CIRCUIT_NATIVE / 'fixed'), _RECURSIVE_SOURCES)

    def test_auto_capacity_boundaries_and_explicit_choices(self):
        small = cyclic_lp([[1, 1]])
        self.assertFalse(select_code_capacity(small, 1))
        self.assertFalse(select_code_capacity(small, 1, False))
        self.assertTrue(select_code_capacity(small, 1, True))
        self.assertTrue(select_code_capacity(small, 1, memory_bytes=1024))
        with self.assertRaisesRegex(ValueError, 'requires --large-capacity'):
            select_code_capacity(small, 1, False, memory_bytes=1024)
        for value in (0, 1, 'auto', [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'boolean or None'):
                select_code_capacity(small, 1, value)
        cases = [(small, 65), (CSSCode.from_sparse(8193, [], []), 1),
                 (CSSCode.from_sparse(3, [[0, 1]] * 2049, []), 1),
                 (CSSCode.from_sparse(65, [list(range(65))], []), 1)]
        for code, cutoff in cases:
            with self.subTest(n=code.n, cutoff=cutoff):
                self.assertTrue(select_code_capacity(code, cutoff))
                with self.assertRaisesRegex(ValueError, 'requires --large-capacity'):
                    select_code_capacity(code, cutoff, False)

    def test_css_and_lp_both_variants_and_legacy_resume(self):
        code = cyclic_lp([[1, 1]])
        with tempfile.TemporaryDirectory() as tmp:
            for profile in ('css', 'lp'):
                for selected in (None, False, True):
                    with self.subTest(profile=profile, selected=selected):
                        output = Path(tmp) / f'{profile}-{selected}'
                        certify(code, output, cutoff=2, profile=profile, node_cap=1,
                                large_capacity=selected)
                        campaign_path = output / 'campaign.json'
                        campaign = read_json(campaign_path)
                        expected = selected is True
                        self.assertIs(campaign['config']['large_capacity'], expected)
                        sources = source_hashes(profile_directory(profile, large_capacity=expected))
                        self.assertEqual(campaign['engine']['source_sha256'], sources)
                        result = certify(code, output, cutoff=2, profile=profile, resume=True)
                        self.assertEqual(result['status'], 'WITNESS_FOUND')
                        self.assertEqual(result['distance_upper_bound'], 2)
                        self.assertIsNone(result['exact_distance'])
                        self.assertEqual(audit_run(output)['sector_bounds'], result['sector_bounds'])
                        with self.assertRaisesRegex(ValueError, 'saved capacity'):
                            certify(code, output, cutoff=2, profile=profile, resume=True,
                                    large_capacity=not expected)
                        # Older records lack this field but retain a complete source identity.
                        del campaign['config']['large_capacity']
                        campaign_path.write_bytes(json_bytes(campaign))
                        resumed = certify(code, output, cutoff=2, profile=profile, resume=True)
                        self.assertEqual(resumed['sector_bounds'], result['sector_bounds'])
                        self.assertEqual(read_json(campaign_path)['engine']['source_sha256'], sources)
                        if not expected:
                            with self.assertRaisesRegex(ValueError, 'does not support memory budgets'):
                                certify(code, output, cutoff=2, profile=profile, resume=True,
                                        memory_mib=1)

    def test_auto_expansion_and_rejection_before_creating_campaign(self):
        code = cyclic_lp([[1, 1]])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'large'
            result = certify(code, output, cutoff=65)
            self.assertEqual(result['status'], 'WITNESS_FOUND')
            self.assertEqual(result['distance_upper_bound'], 2)
            self.assertIs(read_json(output / 'campaign.json')['config']['large_capacity'], True)
            rejected = Path(tmp) / 'rejected'
            with self.assertRaisesRegex(ValueError, 'requires --large-capacity'):
                certify(code, rejected, cutoff=65, large_capacity=False)
            self.assertFalse(rejected.exists())

    def test_capacity_configuration_is_audited(self):
        code = cyclic_lp([[1, 1]])
        with tempfile.TemporaryDirectory() as tmp:
            for selected in (False, True):
                output = Path(tmp) / str(selected)
                certify(code, output, cutoff=1, large_capacity=selected)
                path = output / 'campaign.json'
                document = read_json(path)
                document['config']['large_capacity'] = not selected
                path.write_bytes(json_bytes(document))
                with self.assertRaisesRegex(ValueError, 'Capacity setting'):
                    audit_run(output)

    def test_calibration_selects_and_audits_both_variants(self):
        code = cyclic_lp([[1, 1]])
        with tempfile.TemporaryDirectory() as tmp:
            for selected in (None, False, True):
                output = Path(tmp) / str(selected)
                result = calibrate(code, output, cutoff=1, samples=2, large_capacity=selected)
                path = output / 'calibration.json'
                record = read_json(path)
                expected = selected is True
                self.assertIs(record['config']['large_capacity'], expected)
                self.assertEqual(record['config']['branch_end'], NATIVE_INTEGER_MAX if expected else 64)
                self.assertEqual(audit_calibration(output), result)
                record['config']['large_capacity'] = not expected
                path.write_bytes(json_bytes(record))
                with self.assertRaisesRegex(ValueError, 'Capacity setting'):
                    audit_calibration(output)

    def test_circuit_and_window_modes_select_and_audit_capacity(self):
        model = DetectorModel.from_sparse(3, [[0, 1], [1, 2]], [[0]], witnesses=[[0, 1, 2]])
        with tempfile.TemporaryDirectory() as tmp:
            for window in (None, 1):
                for selected in (None, False, True):
                    output = Path(tmp) / f'{window}-{selected}'
                    result = certify_circuit(model, output, cutoff=2, detectors_per_layer=window,
                                             large_capacity=selected)
                    self.assertEqual(result['exact_distance'], 3)
                    self.assertEqual(audit_circuit(output), result)
                    path = output / 'config.json'
                    record = read_json(path)
                    self.assertIs(record['large_capacity'], selected is True)
                    record['large_capacity'] = selected is not True
                    path.write_bytes(json_bytes(record))
                    manifest_path = output / 'SHA256SUMS.json'
                    manifest = read_json(manifest_path)
                    manifest['files']['config.json'] = digest(path.read_bytes())
                    manifest_path.write_bytes(json_bytes(manifest))
                    with self.assertRaisesRegex(ValueError, 'Capacity setting'):
                        audit_circuit(output)
            # The effective search depth respects the number of mechanisms.
            output = Path(tmp) / 'oversized-cutoff'
            certify_circuit(model, output, cutoff=1024, large_capacity=False)
            self.assertIs(read_json(output / 'config.json')['large_capacity'], False)
            self.assertEqual(audit_circuit(output)['distance_upper_bound'], 3)

    def test_cli_flags_and_memory_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = Path(tmp) / 'code.json'
            cyclic_lp([[1, 1]]).save(code)
            for flag in ('--large-capacity', '--no-large-capacity'):
                output = Path(tmp) / flag[2:]
                proc = subprocess.run([sys.executable, '-m', 'cssdist', 'certify', str(code),
                                       '--cutoff', '1', '--out', str(output), flag],
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                selected = read_json(output / 'campaign.json')['config']['large_capacity']
                self.assertIs(selected, flag == '--large-capacity')
            for command in ('certify', 'calibrate', 'certify-circuit'):
                proc = subprocess.run([sys.executable, '-m', 'cssdist', command, '--help'],
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn('--no-large-capacity', proc.stdout)
            output = Path(tmp) / 'memory'
            certify(cyclic_lp([[1, 1]]), output, cutoff=1, memory_mib=1)
            self.assertIs(read_json(output / 'campaign.json')['config']['large_capacity'], True)


if __name__ == '__main__':
    unittest.main()
