"""Global truth tables, boundary regressions and evidence checks for the window option."""
import contextlib
import io
import itertools
import json
from pathlib import Path
import random
import shutil
import tempfile
import unittest

from cssdist.circuit import DetectorModel
from cssdist.circuit_run import audit_circuit, certify_circuit
from cssdist.circuit_window_search import detector_layer_ids, window_model, window_plan
from cssdist.cli import main
from cssdist.code import digest, json_bytes


def model_from_columns(columns, detectors, observables=2, **kwargs):
    rows = [[j for j, value in enumerate(columns) if value & (1 << i)]
            for i in range(detectors + observables)]
    return DetectorModel.from_sparse(len(columns), rows[:detectors], rows[detectors:], **kwargs)


def memory(boundary=False):
    # A data fault has one detector; a bridge has two adjacent detectors and flips L0.
    cols = []
    for i in range(5):
        cols.append(1 << i)
        if i < 4:
            cols.append((3 << i) | (1 << 5))
    if boundary:
        cols.append((1 << 4) | (1 << 6))  # Same D as the last data fault, but flips L1.
    return model_from_columns(cols, 5, witnesses=[[0, 1, 2]])


def brute_distance(model, cutoff, roots):
    for w in range(1, min(cutoff, model.n) + 1):
        for support in itertools.combinations(range(model.n), w):
            if support[0] < roots and model.is_logical(sum(1 << j for j in support)):
                return w
    return None


class WindowSearchTests(unittest.TestCase):
    def test_random_small_covers_against_global_brute_force(self):
        rng = random.Random(13615)
        for _ in range(240):
            m = rng.randint(1, 7)
            n = rng.randint(1, 9)
            columns = [rng.randrange(1 << (m + 2)) for _ in range(n)]
            model = model_from_columns(columns, m)
            layers = detector_layer_ids(model, None, [rng.choice([0, 2, 4, 7]) for _ in range(m)])
            cutoff = rng.randrange(5)
            plan = window_plan(model, cutoff, layers)
            minima = []
            if plan['detector_free_witness'] is not None and cutoff:
                minima.append(1)
            for rep in plan['representatives']:
                local = window_model(model, rep['source_columns'])
                d = brute_distance(local, cutoff, rep['root_end'])
                if d is not None:
                    minima.append(d)
            self.assertEqual(min(minima, default=None), brute_distance(model, cutoff, n))

    def test_native_decisions_match_brute_force_on_shuffled_small_models(self):
        rng = random.Random(13616)
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(30):
                m, n = rng.randint(2, 6), rng.randint(4, 9)
                columns = [rng.randrange(1 << (m + 2)) for _ in range(n)]
                # Install a valid three-column neutral, sometimes across several layers.
                columns[2] = columns[0] ^ columns[1]
                model = model_from_columns(columns, m, neutral_rows=[[0, 1, 2]])
                cutoff = rng.randint(1, 4)
                exact = brute_distance(model, cutoff, n)
                path = Path(tmp) / str(i)
                result = certify_circuit(model, path, cutoff=cutoff,
                                         detector_layers=[rng.randrange(4) for _ in range(m)],
                                         weighted=bool(i % 2), neutral=bool(i % 3))
                with self.subTest(i=i):
                    if exact is None:
                        self.assertEqual(result['status'], 'EXCLUDED')
                        self.assertEqual(result['distance_lower_bound'], cutoff+1)
                    else:
                        self.assertEqual(result['status'], 'WITNESS_FOUND')
                        for w in result['checked_witnesses']:
                            self.assertEqual(model.check_witness(w['support']), w)
                            self.assertLessEqual(exact, w['weight'])
                            self.assertLessEqual(w['weight'], cutoff)
                    self.assertEqual(audit_circuit(path), result)

    def test_no_cut_faults_or_partial_neutrals(self):
        # The bridge touches detectors on both sides of a one-layer boundary.
        # Cutting off that detector would create an artificial logical pair.
        model = model_from_columns([1, 3, 2, 4 | 8], 3, neutral_rows=[[0, 1, 2]])
        plan = window_plan(model, 1, [0, 1, 2])
        final = next(rep for rep in plan['representatives'] if rep['start'] == 2)
        self.assertEqual(final['source_columns'], [3])
        self.assertEqual(window_model(model, final['source_columns']).neutrals, [])
        self.assertEqual(window_model(model, [1, 2]).document['detector_rows'], [[0], [0, 1]])
        self.assertEqual(window_model(model, [1, 2]).neutrals, [])

    def test_stationary_open_boundary_and_observable_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = memory()
            path = Path(tmp) / 'open'
            result = certify_circuit(model, path, cutoff=2, detectors_per_layer=1)
            self.assertEqual(result['exact_distance'], 3)
            self.assertEqual(result['representatives_excluded'], 1)
            self.assertEqual(result['windows_covered_by_plan'], 5)
            self.assertEqual(result['roots_completed'], 2)
            self.assertEqual(audit_circuit(path), result)
            # Shifted containment must retain both observable bits. The last pair
            # is the only two-fault logical, and only its own starting layer can find it.
            model = memory(boundary=True)
            path = Path(tmp) / 'boundary'
            result = certify_circuit(model, path, cutoff=2, detectors_per_layer=1)
            self.assertEqual(result['status'], 'WITNESS_FOUND')
            self.assertGreater(result['representatives_required'], 1)
            self.assertEqual(result['checked_witnesses'], [model.check_witness([8, 9])])
            self.assertEqual(audit_circuit(path), result)
            for file in path.glob('windows/*/receipt.json'):
                terminal = json.loads(json.loads(file.read_text())['stdout'].splitlines()[-1])
                self.assertLessEqual(terminal['roots_completed'], terminal['root_end'])

    def test_long_range_faults_and_arbitrary_input_order(self):
        # Four faults form a path over layers 0, 3 and 6. A fixed five-layer
        # window would miss it. Shuffled fault IDs also exercise witness lifting.
        model = model_from_columns([(1 << 3) | (1 << 6), 1, 1 << 6, 1 | (1 << 3) | (1 << 7)], 7)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'long'
            result = certify_circuit(model, path, cutoff=4, detectors_per_layer=1)
            self.assertEqual(result['max_fault_span'], 3)
            self.assertEqual(result['window_layers'], 7)
            self.assertEqual(result['checked_witnesses'], [model.check_witness(list(range(4)))])
            self.assertEqual(audit_circuit(path), result)

    def test_detector_free_faults_zero_cutoff_and_vacuous_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            for cutoff in (0, 1):
                model = DetectorModel.from_sparse(2, [], [[1]])
                path = Path(tmp) / f'd1-{cutoff}'
                result = certify_circuit(model, path, cutoff=cutoff, node_cap=0, detector_layers=[])
                self.assertEqual(result['exact_distance'], 1)
                self.assertEqual(result['status'], 'EXCLUDED' if cutoff == 0 else 'WITNESS_FOUND')
                self.assertEqual(result['window_runs'], [])
                self.assertEqual(audit_circuit(path), result)
            model = DetectorModel.from_sparse(1, [], [[]])
            path = Path(tmp) / 'silent'
            result = certify_circuit(model, path, cutoff=3, detector_layers=[])
            self.assertEqual(result['distance_lower_bound'], 4)
            self.assertIsNone(result['distance_upper_bound'])
            self.assertEqual(audit_circuit(path), result)

    def test_partial_results_and_cumulative_resource_limits(self):
        # Distinct observable signatures give two different one-root windows.
        model = model_from_columns([1, 2 | (1 << 2)], 2)
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / 'cap'
            result = certify_circuit(model, a, cutoff=1, detectors_per_layer=1, node_cap=1)
            self.assertEqual(result['status'], 'INCOMPLETE')
            self.assertEqual(result['representatives_excluded'], 1)
            self.assertIsNone(result['distance_lower_bound'])
            self.assertEqual(audit_circuit(a), result)
            partial = Path(tmp) / 'mid-window'
            result = certify_circuit(memory(), partial, cutoff=2, detectors_per_layer=1, node_cap=1)
            self.assertEqual(result['window_runs'][0]['status'], 'INCOMPLETE')
            self.assertIsNone(result['distance_lower_bound'])
            self.assertEqual(audit_circuit(partial), result)
            b = Path(tmp) / 'timeout'
            result = certify_circuit(model, b, cutoff=1, detectors_per_layer=1, seconds=1e-9)
            self.assertEqual(result['status'], 'INCOMPLETE')
            self.assertIsNone(result['distance_lower_bound'])
            self.assertEqual(audit_circuit(b), result)

    def test_audit_recomputes_cover_and_rejects_altered_prefix(self):
        def rehash(path, name, value):
            data = json_bytes(value)
            (path / name).write_bytes(data)
            manifest = json.loads((path / 'SHA256SUMS.json').read_text())
            manifest['files'][name] = digest(data)
            (path / 'SHA256SUMS.json').write_bytes(json_bytes(manifest))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit'
            certify_circuit(memory(), path, cutoff=2, detectors_per_layer=1)
            cover = json.loads((path / 'coverage.json').read_text())
            rehash(path, 'coverage.json', dict(cover, windows=cover['windows'][:-1]))
            with self.assertRaisesRegex(ValueError, 'coverage'):
                audit_circuit(path)
            rehash(path, 'coverage.json', cover)
            name = 'windows/0/receipt.json'
            receipt = json.loads((path / name).read_text())
            terminal = json.loads(receipt['stdout'].splitlines()[-1])
            terminal['roots_completed'] -= 1
            receipt['stdout'] = json.dumps(terminal) + '\n'
            rehash(path, name, receipt)
            with self.assertRaisesRegex(ValueError, 'window-root'):
                audit_circuit(path)

    def test_missing_representative_cannot_certify_even_after_rehash(self):
        model = model_from_columns([1, 2 | (1 << 2)], 2)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'initial'
            result = certify_circuit(model, path, cutoff=1, detectors_per_layer=1)
            self.assertEqual(result['representatives_excluded'], 2)
            relocated = Path(tmp) / 'relocated'
            path.rename(relocated)
            self.assertEqual(audit_circuit(relocated), result)
            shutil.rmtree(relocated / 'windows/1')
            manifest = json.loads((relocated/'SHA256SUMS.json').read_text())
            for name in ('windows/1/receipt.json', 'windows/1/model.txt'):
                del manifest['files'][name]
            (relocated/'SHA256SUMS.json').write_bytes(json_bytes(manifest))
            with self.assertRaisesRegex(ValueError, 'Window (timing|conclusion)'):
                audit_circuit(relocated)

    def test_cli_irregular_layout_and_invalid_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = model_from_columns([1, 2, 4, 1 | (1 << 3)], 3)
            model.save(root / 'input.json')
            (root / 'layers.json').write_text('[10, 4, 10]')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                status = main(['certify-circuit', str(root/'input.json'), '--out', str(root/'run'),
                               '--cutoff', '2', '--detector-layers', str(root/'layers.json')])
                self.assertEqual(status, 10)
                self.assertEqual(main(['audit-circuit', str(root/'run')]), 10)
            result = audit_circuit(root/'run')
            self.assertEqual(result['checked_witnesses'], [model.check_witness([0, 3])])
            for bad in ([], [True, 1, 2], [-1, 0, 1], [1.1, 2, 3]):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    certify_circuit(model, root/'bad', cutoff=1, detector_layers=bad)
            with self.assertRaises(ValueError):
                certify_circuit(model, root/'bad', cutoff=1, detectors_per_layer=0)
            with self.assertRaises(ValueError):
                certify_circuit(model, root/'bad', cutoff=1, detectors_per_layer=1, detector_layers=[0, 1, 2])
            self.assertFalse((root/'bad').exists())
