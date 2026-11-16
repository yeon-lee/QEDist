import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cssdist import CSSCode, cyclic_lp
from cssdist.audit import audit_run
from cssdist.calibration import calibrate, audit_calibration, root_schedule, summarize_roots
from cssdist.campaign import certify
from cssdist.engine import PROFILES, check_limits, source_hashes, profile_directory


def steane():
    rows = [[0,2,4,6], [1,2,5,6], [3,4,5,6]]
    return CSSCode.from_sparse(7, rows, rows, sector_exchange=list(range(7)))


class ProfileTests(unittest.TestCase):
    def test_css_capacity_and_audit(self):
        code = CSSCode.from_sparse(4097, [], [], sector_exchange=list(range(4097)))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'css'
            result = certify(code, out, cutoff=1, profile='css')
            self.assertEqual(result['exact_distance'], 1)
            self.assertEqual(audit_run(out)['exact_distance'], 1)
            m = json.loads((out/'campaign.json').read_text())
            self.assertEqual(m['config']['native_profile'], 'css')

    def test_invalid_profile_types_are_rejected(self):
        for invalid in (None, [], {}, True, 'unknown', 'preserved4096', 'expanded8192',
                        'optimized8192', 'refined8192'):
            with self.assertRaisesRegex(ValueError, 'Unknown native profile'):
                profile_directory(invalid)

    def test_only_current_sources_are_registered(self):
        self.assertEqual(set(PROFILES), {'css', 'lp'})
        self.assertEqual({path.name for path in profile_directory().parent.glob('native*')},
                         {'native_css', 'native_lp', 'native_circuit'})
        self.assertEqual(source_hashes()['common.hpp'],
                         source_hashes(profile_directory('lp'))['common.hpp'])
        self.assertNotEqual(source_hashes()['exact.cpp'],
                            source_hashes(profile_directory('lp'))['exact.cpp'])

    def test_boundary_and_independent_audit(self):
        for profile in PROFILES:
            check_limits(CSSCode.from_sparse(8192, [], []), 1, profile)
            check_limits(CSSCode.from_sparse(8193, [], []), 65, profile)
            with self.assertRaisesRegex(ValueError, '2147483647'):
                check_limits(steane(), 2**31, profile)

    def test_both_profiles_match_small_css_distances(self):
        codes = [cyclic_lp([[1,1]]), cyclic_lp([[1,1]], [[1,1,0],[0,1,1]])]
        with tempfile.TemporaryDirectory() as tmp:
            for i,code in enumerate(codes):
                results = [certify(code, Path(tmp)/f'{i}_{profile}', cutoff=2,
                                   profile=profile, seconds_per_shard=2)
                           for profile in ('css', 'lp')]
                for result in results[1:]:
                    for key in ('status','distance_lower_bound','distance_upper_bound','sector_bounds'):
                        self.assertEqual(results[0][key], result[key])

    def test_missing_profile_cannot_select_an_engine_implicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'old'
            certify(steane(), out, cutoff=2, seconds_per_shard=2)
            path = out/'campaign.json'
            campaign = json.loads(path.read_text())
            del campaign['config']['native_profile']
            path.write_text(json.dumps(campaign))
            with self.assertRaisesRegex(ValueError, 'Unknown native profile'):
                audit_run(out)


class CalibrationTests(unittest.TestCase):
    def test_sampling_is_reproducible_and_sector_aware(self):
        code = steane()
        period, schedule = root_schedule(code, 4, 17)
        self.assertEqual((period,schedule), root_schedule(code,4,17))
        self.assertEqual(set(schedule), {'Z'})
        self.assertEqual(len(set(schedule['Z'])), 4)
        _, both = root_schedule(code, 99, 17, use_symmetry=False)
        self.assertEqual(set(both), {'X','Z'})
        self.assertTrue(all(set(roots)==set(range(7)) for roots in both.values()))

    def test_censoring_and_small_samples_have_no_finite_forecast(self):
        good = {'status':'excluded','wall_seconds':1.1,'native_seconds':1.0}
        bad = {'status':'incomplete','wall_seconds':1.1,'native_seconds':1.0}
        censored = summarize_roots([good]*4+[bad], 20)
        self.assertEqual(censored['status'], 'CENSORED')
        self.assertIsNone(censored['estimated_total_native_seconds'])
        few = summarize_roots([good]*3, 20)
        self.assertEqual(few['status'], 'INSUFFICIENT_SAMPLE')
        self.assertIsNone(few['estimated_total_native_seconds'])
        allroots = summarize_roots([good]*4, 4)
        self.assertEqual(allroots['status'], 'ALL_ROOTS_MEASURED')
        self.assertEqual(allroots['estimated_total_native_seconds'], 4)
        self.assertIsNone(allroots['distance_claim'])

    def test_empirical_forecast_is_explicitly_not_a_bound(self):
        records = [{'status':'excluded','wall_seconds':t,'native_seconds':t} for t in (1,2,3,4)]
        result = summarize_roots(records, 20, 13)
        self.assertEqual(result['status'], 'EMPIRICAL_ESTIMATE')
        self.assertEqual(result['estimated_total_native_seconds'], 50)
        self.assertIn('not a confidence', result['uncertainty_note'])
        self.assertEqual(result, summarize_roots(records,20,13))

    def test_native_complete_and_node_censored_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'complete'
            result = calibrate(steane(), out, cutoff=2, samples=7, seconds_per_root=1)
            self.assertEqual(result['sectors']['Z']['status'], 'ALL_ROOTS_MEASURED')
            self.assertEqual(result['sectors']['Z']['completed_roots'],7)
            self.assertIsNone(result['distance_claim'])
            self.assertEqual(audit_calibration(out), result)
            limited = calibrate(steane(), Path(tmp)/'limited', cutoff=3, samples=7,
                                seconds_per_root=1, node_cap=1)
            self.assertEqual(limited['sectors']['Z']['status'], 'CENSORED')
            self.assertIsNone(limited['sectors']['Z']['estimated_total_native_seconds'])

    def test_witness_is_physically_checked_without_exclusion_credit(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'witness'
            result = calibrate(steane(), out, cutoff=3, samples=7, seconds_per_root=1)
            self.assertEqual(result['sectors']['Z']['status'], 'WITNESS_FOUND')
            self.assertIsNone(result['sectors']['Z']['estimated_total_native_seconds'])
            self.assertIsNone(result['distance_claim'])
            self.assertTrue(any(r['witnesses'] for r in result['records']))

    def test_corrupt_record_and_false_summary_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'run'
            original = calibrate(steane(),out,cutoff=2,samples=4)
            (out/'result.json').write_text('{"status":"EXACT_DISTANCE","d":99}')
            self.assertEqual(audit_calibration(out),original)
            transcript = next(out.glob('roots/*/*/stdout.jsonl'))
            transcript.write_bytes(transcript.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'transcript changed'):
                audit_calibration(out)

    def test_wrong_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run'
            calibrate(steane(),out,cutoff=2,samples=4)
            m=json.loads((out/'calibration.json').read_text())
            m['config']['native_profile']='lp'
            (out/'calibration.json').write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,'LP block roots'):
                audit_calibration(out)

    def test_cli_and_optimized_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            code=Path(tmp)/'code.json';steane().save(code)
            out=Path(tmp)/'run'
            result=subprocess.run([sys.executable,'-m','cssdist','calibrate',str(code),'--cutoff','2',
                                   '--samples','4','--out',str(out)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'],'CALIBRATION_COMPLETE')
            bad=subprocess.run([sys.executable,'-O','-m','cssdist','calibrate',str(code),'--cutoff','2',
                                '--samples','0','--out',str(Path(tmp)/'bad')],capture_output=True,text=True)
            self.assertEqual(bad.returncode,2)
            self.assertIn('positive integer',bad.stderr)


if __name__=='__main__': unittest.main()
