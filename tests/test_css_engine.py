"""CSS engine policy, physical results, portable records and profile renaming."""
import copy
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from cssdist import CSSCode, cyclic_lp
from cssdist.cli import load_input
from cssdist.audit import audit_run, check_profile_metadata, command, configuration
from cssdist.calibration import calibrate, audit_calibration
from cssdist.campaign import certify
from cssdist.engine import DEFAULT_PROFILE, profile_directory, profile_options, source_hashes
from cssdist.portable import export_bundle, audit_bundle


def even_code():
    return CSSCode.from_sparse(4, [[0, 1, 2, 3]], [[0, 1, 2, 3]],
                               cyclic_period=4, sector_exchange=list(range(4)))


class CSSEngineTests(unittest.TestCase):
    def test_default_profile_and_recorded_policy(self):
        self.assertEqual(DEFAULT_PROFILE, 'css')
        code = even_code()
        new = configuration(code, 1, 1, 1)
        self.assertEqual(new['native_profile'], 'css')
        self.assertEqual(command(new, 'Z', 0, 1, 100)[-3:], profile_options('css'))
        self.assertEqual(set(source_hashes(profile_directory('css'))),
                         {'exact.cpp', 'common.hpp', 'even_methods.inc', 'symmetry.hpp'})

    def test_native_policy_metadata_cannot_change(self):
        cfg = {'native_profile': 'css'}
        good = {'fractional_mode': 2, 'repair_depth': 8, 'even_repair_cap': 4,
                'fractional_placement': 'before_mis'}
        check_profile_metadata(good, cfg)
        for field in good:
            bad = copy.deepcopy(good)
            bad[field] = False
            with self.assertRaisesRegex(ValueError, 'weighted profile settings'):
                check_profile_metadata(bad, cfg)

    def test_parity_calibration_portable_and_include_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = certify(even_code(), root/'run', cutoff=1, shards=3)
            self.assertEqual(result['exact_distance'], 2)
            self.assertEqual(result['nodes_in_recorded_attempts'], 0)
            bundle = root/'bundle.tar.gz'
            export_bundle(root/'run', bundle)
            self.assertEqual(audit_bundle(bundle)['result']['exact_distance'], 2)
            with tarfile.open(bundle) as archive:
                self.assertIn('checker/cssdist/native_css/even_methods.inc', archive.getnames())
                self.assertIn('evidence/engine/even_methods.inc', archive.getnames())
            cal = calibrate(even_code(), root/'cal', cutoff=1, samples=1)
            self.assertEqual(cal, audit_calibration(root/'cal'))
            self.assertIsNone(cal['distance_claim'])
            include = root/'run/engine/even_methods.inc'
            include.write_text(include.read_text()+'\n// changed\n')
            with self.assertRaisesRegex(ValueError, 'source differs'):
                audit_run(root/'run')

    def test_former_profile_name_audits_and_resumes_without_rewriting_records(self):
        cases = [(even_code(), 'css', 'weighted8192'),
                 (cyclic_lp([[1, 1]]), 'lp', 'lpblocks8192')]
        for code, profile, former in cases:
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)/'old'
                certify(code, root, cutoff=1, profile=profile)
                manifest = root / 'campaign.json'
                data = json.loads(manifest.read_text())
                data['config']['native_profile'] = former
                manifest.write_text(json.dumps(data))
                before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(audit_run(root)['exact_distance'], 2)
                result = certify(code, root, cutoff=1, resume=True, profile=profile)
                self.assertEqual(result['last_invocation']['jobs_run'], 0)
                before.pop('result.json')
                self.assertEqual(before, {str(p.relative_to(root)): p.read_bytes()
                                         for p in root.rglob('*') if p.is_file() and p.name != 'result.json'})

    def test_weighted_cuts_and_recorded_search_tree(self):
        fixture = Path(__file__).resolve().parents[1]/'examples/catalogue/lp-f2-320-64-10.json'
        code = load_input(fixture)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = certify(code, root/'css', cutoff=9, split_weight=1,
                             profile='css', seconds_per_shard=5, proposed_additions=False)
            self.assertEqual(result['exact_distance'], 10)
            receipt = json.loads(next((root/'css').glob('jobs/*/*/attempt-*/receipt.json')).read_text())
            final = receipt['terminal']
            self.assertGreater(final['even_prunes'], 0)
            self.assertGreater(final['fractional_prunes'], 0)
            self.assertGreater(final['repair_changes'], 0)
            self.assertEqual(final['nodes'], 34622)
            self.assertEqual(final['frontier_digest'], '8232597154302800249')
            self.assertEqual(set(receipt['source_sha256']),
                             {'exact.cpp', 'common.hpp', 'even_methods.inc', 'symmetry.hpp'})


if __name__ == '__main__':
    unittest.main()
