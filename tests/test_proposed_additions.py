"""Exercise the parent-bound test, including its symmetry and audit boundaries."""
import json
from contextlib import redirect_stdout, redirect_stderr
import io
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from cssdist import CSSCode, cyclic_lp
from cssdist.algebra import kernel_basis, support
from cssdist.audit import audit_run, check_profile_metadata
from cssdist.calibration import calibrate, audit_calibration
from cssdist.campaign import certify
from cssdist.cli import load_input, main
from cssdist.engine import profile_options
from cssdist.portable import export_bundle, audit_bundle


def exact_distance(code):
    return min(word.bit_count() for word in range(1, 1 << code.n)
               if code.is_logical(word, 'X') or code.is_logical(word, 'Z'))


class ProposedAdditionTests(unittest.TestCase):
    def test_random_css_against_exhaustive_supports(self):
        rng = random.Random(17031)
        with tempfile.TemporaryDirectory() as directory:
            for index in range(24):
                n = 5 + index % 4
                hx = [rng.randrange(1, 1 << n) for _ in range(1 + index % 3)]
                kernel = kernel_basis(hx, n)
                hz = rng.sample(kernel, min(len(kernel), index % 3))
                code = CSSCode.from_sparse(n, list(map(support, hx)), list(map(support, hz)))
                if code.k == 0:
                    continue
                distance = exact_distance(code)
                for cutoff in sorted({max(1, distance - 1), distance}):
                    for enabled in (False, True):
                        run = Path(directory) / f'{index}-{cutoff}-{enabled}'
                        result = certify(code, run, cutoff=cutoff, shards=2, workers=2,
                                         split_weight=min(cutoff, 2),
                                         coset_pruning=index % 2 == 0,
                                         proposed_additions=enabled)
                        self.assertEqual(result['all_required_shards_excluded'], cutoff < distance)
                        self.assertLessEqual(result['distance_lower_bound'], distance)
                        self.assertGreaterEqual(result['distance_upper_bound'], distance)
                        self.assertEqual(audit_run(run)['sector_bounds'], result['sector_bounds'])

    def test_lp_binary_and_quaternary_with_shards(self):
        cases = [cyclic_lp([[1, 1]], [[1, 0]], period=2),
                 cyclic_lp([[1, 2]], [[1, 3]], field=4),
                 cyclic_lp([[1, 1], [1, 1]], [[1], [1]])]
        with tempfile.TemporaryDirectory() as directory:
            for index, code in enumerate(cases):
                distance = exact_distance(code)
                for profile in ('css', 'lp'):
                    for cutoff in sorted({max(1, distance - 1), distance}):
                        result = certify(code, Path(directory) / f'{index}-{profile}-{cutoff}',
                                         cutoff=cutoff, profile=profile, proposed_additions=True,
                                         shards=3, workers=2, split_weight=min(2, cutoff))
                        self.assertEqual(result['all_required_shards_excluded'], cutoff < distance)

    def test_product_symmetry_and_real_pruning(self):
        root = Path(__file__).resolve().parents[1]
        cases = [('examples/symmetry/bb144.json', 5, 'css'),
                 ('examples/catalogue/lp-f2-320-64-10.json', 9, 'lp')]
        skipped = 0
        with tempfile.TemporaryDirectory() as directory:
            for index, (filename, cutoff, profile) in enumerate(cases):
                code = load_input(root / filename)
                results = []
                for enabled in (False, True):
                    run = Path(directory) / f'{index}-{enabled}'
                    results.append(certify(code, run, cutoff=cutoff, profile=profile,
                                           proposed_additions=enabled, shards=2, workers=2,
                                           seconds_per_shard=30))
                    for receipt in run.glob('jobs/*/*/attempt-*/receipt.json'):
                        terminal = json.loads(receipt.read_text())['terminal']
                        self.assertIs(terminal['proposed_additions'], enabled)
                        skipped += terminal['proposed_prunes']
                self.assertEqual(results[0]['sector_bounds'], results[1]['sector_bounds'])
                self.assertTrue(results[1]['all_required_shards_excluded'])
        self.assertGreater(skipped, 0)

    def test_resume_and_portable_evidence_keep_option(self):
        code = cyclic_lp([[1, 1]])
        with tempfile.TemporaryDirectory() as directory:
            for profile in ('css', 'lp'):
                for enabled in (False, True):
                    run = Path(directory) / f'{profile}-{enabled}'
                    certify(code, run, cutoff=1, profile=profile, proposed_additions=enabled)
                    original = {p.relative_to(run): p.read_bytes() for p in run.rglob('*')
                                if p.is_file() and p.name != 'result.json'}
                    config = json.loads((run / 'campaign.json').read_text())['config']
                    self.assertIs(config.get('proposed_additions', False), enabled)
                    if not enabled:
                        self.assertNotIn('proposed_additions', config)
                    result = certify(code, run, cutoff=1, profile=profile, resume=True)
                    self.assertEqual(result['last_invocation']['jobs_run'], 0)
                    result = certify(code, run, cutoff=1, profile=profile, resume=True,
                                     proposed_additions=enabled)
                    self.assertEqual(result['last_invocation']['jobs_run'], 0)
                    with self.assertRaisesRegex(ValueError, 'Resume requires'):
                        certify(code, run, cutoff=1, profile=profile, resume=True,
                                proposed_additions=not enabled)
                    self.assertEqual(original, {p.relative_to(run): p.read_bytes() for p in run.rglob('*')
                                               if p.is_file() and p.name != 'result.json'})
                    archive = Path(directory) / f'{profile}-{enabled}.tar.gz'
                    export_bundle(run, archive)
                    self.assertEqual(audit_bundle(archive)['status'], 'PASS')

    def test_default_matches_explicit_on_in_both_engines(self):
        root = Path(__file__).resolve().parents[1]
        code = load_input(root / 'examples/catalogue/lp-f2-320-64-10.json')
        with tempfile.TemporaryDirectory() as directory:
            for profile in ('css', 'lp'):
                default_run = Path(directory) / f'{profile}-default'
                result = certify(code, default_run, cutoff=9, profile=profile)
                explicit = certify(code, Path(directory) / f'{profile}-on', cutoff=9,
                                   profile=profile, proposed_additions=True)
                self.assertEqual(result['sector_bounds'], explicit['sector_bounds'])
                self.assertEqual(result['nodes_in_recorded_attempts'], explicit['nodes_in_recorded_attempts'])
                config = json.loads((default_run / 'campaign.json').read_text())['config']
                self.assertIs(config['proposed_additions'], True)
                for receipt in default_run.glob('jobs/*/*/attempt-*/receipt.json'):
                    data = json.loads(receipt.read_text())
                    self.assertIn('proposed-additions=on', data['command'])
                    self.assertIs(data['terminal']['proposed_additions'], True)

    def test_unfinished_resume_runs_with_saved_policy(self):
        root = Path(__file__).resolve().parents[1]
        code = load_input(root / 'examples/steane.json')
        with tempfile.TemporaryDirectory() as directory:
            for enabled in (False, True):
                run = Path(directory) / str(enabled)
                initial = certify(code, run, cutoff=2, shards=2, node_cap=1,
                                  proposed_additions=enabled)
                self.assertEqual(initial['status'], 'INCOMPLETE')
                original = {p.relative_to(run): p.read_bytes() for p in run.glob('jobs/*/*/attempt-*/*')}
                result = certify(code, run, cutoff=2, shards=2, resume=True)
                self.assertTrue(result['all_required_shards_excluded'])
                self.assertGreater(result['last_invocation']['jobs_run'], 0)
                for path, contents in original.items():
                    self.assertEqual((run / path).read_bytes(), contents)
                for receipt in run.glob('jobs/*/*/attempt-*/receipt.json'):
                    terminal = json.loads(receipt.read_text())['terminal']
                    self.assertIs(terminal['proposed_additions'], enabled)

    def test_cli_defaults_opt_out_and_resume(self):
        source = Path(__file__).resolve().parents[1] / 'examples/steane.json'
        with tempfile.TemporaryDirectory() as directory:
            for action, metadata in (('certify', 'campaign.json'), ('calibrate', 'calibration.json')):
                for enabled in (False, True):
                    run = Path(directory) / f'{action}-{enabled}'
                    args = [action, str(source), '--cutoff', '2', '--out', str(run)]
                    if not enabled:
                        args.append('--no-proposed-additions')
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        self.assertEqual(main(args), 0)
                    config = json.loads((run / metadata).read_text())['config']
                    self.assertIs(config.get('proposed_additions', False), enabled)
                    if action == 'certify':
                        resume_args = ['certify', str(source), '--cutoff', '2', '--out', str(run), '--resume']
                        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                            self.assertEqual(main(resume_args), 0)
                            opposite = '--no-proposed-additions' if enabled else '--proposed-additions'
                            self.assertEqual(main(resume_args + [opposite]), 2)

    def test_benchmark_records_effective_settings_on_resume(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'runs'
            summary = Path(directory) / 'summary.json'
            args = [sys.executable, '-m', 'tools.benchmark', '--out', str(output),
                    '--summary', str(summary), '--shards', '1', '--workers', '1']
            first = subprocess.run(args + ['--cases', 'steane', '--no-proposed-additions'],
                                   cwd=root, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIs(json.loads(summary.read_text())['proposed_additions'], False)
            resumed = subprocess.run(args + ['--cases', 'steane', 'independent_qc', '--resume'],
                                     cwd=root, capture_output=True, text=True)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            report = json.loads(summary.read_text())
            self.assertIsNone(report['proposed_additions'])
            self.assertEqual({case['case']: case['proposed_additions'] for case in report['cases']},
                             {'steane': False, 'independent_qc': True})

    def test_calibration_and_strict_option_validation(self):
        code = cyclic_lp([[1, 1]])
        with tempfile.TemporaryDirectory() as directory:
            for enabled in (False, True):
                run = Path(directory) / f'calibration-{enabled}'
                options = {} if enabled else {'proposed_additions': False}
                result = calibrate(code, run, cutoff=1, samples=3, **options)
                self.assertEqual(audit_calibration(run), result)
                config = json.loads((run / 'calibration.json').read_text())['config']
                self.assertIs(config.get('proposed_additions', False), enabled)
            for value in (1, 'true', None):
                if value is not None:
                    with self.assertRaisesRegex(ValueError, 'boolean'):
                        certify(code, Path(directory) / 'invalid', cutoff=1, proposed_additions=value)
                with self.assertRaisesRegex(ValueError, 'boolean'):
                    calibrate(code, Path(directory) / 'invalid-calibration', cutoff=1,
                              proposed_additions=value)
                with self.assertRaisesRegex(ValueError, 'boolean'):
                    profile_options('css', value)
        terminal = {'fractional_mode': 2, 'repair_depth': 8, 'even_repair_cap': 4,
                    'fractional_placement': 'before_mis', 'proposed_additions': False}
        with self.assertRaisesRegex(ValueError, 'proposed-addition'):
            check_profile_metadata(terminal, {'native_profile': 'css', 'proposed_additions': True})


if __name__ == '__main__':
    unittest.main()
