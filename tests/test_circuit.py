"""Direct detector/observable semantics, high-degree backend and evidence audit."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from cssdist.circuit import DetectorModel, from_dem_text
from cssdist.circuit_run import certify_circuit, audit_circuit
from cssdist.code import digest, json_bytes


def hyperedge_model():
    # First two columns share three detectors but differ in logical action.
    # Remaining three form a graphlike logical chain of weight three.
    return DetectorModel.from_sparse(5, [[0, 1, 2, 3], [0, 1, 3, 4], [0, 1]],
                                     [[0, 4]], witnesses=[[0, 1]])


class CircuitModelTests(unittest.TestCase):
    def test_no_css_commutation_assumption_or_second_sector(self):
        model = hyperedge_model()
        self.assertTrue(model.is_logical(3))
        self.assertEqual(model.check_witness([1, 0])['weight'], 2)
        self.assertEqual(model.inspect()['hyperedge_faults'], 2)
        self.assertTrue(model.native_text().startswith('QEDIST_CIRCUIT_V1 5 3 1 0\n'))

    def test_invalid_inputs_and_neutrals(self):
        valid = hyperedge_model().document
        for update in ({'n_faults': True}, {'n_faults': 0}, {'observable_rows': []},
                       {'detector_rows': [[0, 0]]}, {'detector_rows': [[5]]},
                       {'observable_rows': [[False]]}, {'neutral_rows': [[0, 1]]},
                       {'neutral_rows': [[]]}, {'witnesses': [[0]]},
                       {'metric': 'likelihood'}, {'metadata': []}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                DetectorModel(dict(valid, **update))

    def test_sparse_neutral_budget_is_not_a_completeness_claim(self):
        model = DetectorModel.from_sparse(6, [[0, 1, 3, 4], [1, 2, 3, 5]], [[4, 5]])
        found = model.with_sparse_neutrals(pair_budget=10, max_relations=4)
        self.assertLessEqual(len(found.neutrals), 4)
        for row in found.neutrals:
            self.assertFalse(any((row & h).bit_count() & 1
                                 for h in model.detectors + model.observables))
        self.assertFalse(found.document['metadata']['neutral_generation']['complete'])
        self.assertIsNone(found.document['metadata']['neutral_generation']['distance_claim'])
        self.assertEqual(model.with_sparse_neutrals(0, 0).neutrals, [])

    def test_dem_separator_is_one_fault(self):
        try:
            import stim  # noqa: F401
        except ImportError:
            self.skipTest('Optional Stim dependency is not installed')
        model = from_dem_text('error(0.01) D0 D1 ^ D1 D2 L0\nerror(0) D2\n')
        self.assertEqual(model.n, 1)
        self.assertEqual(model.document['detector_rows'], [[0], [], [0]])
        self.assertEqual(model.document['observable_rows'], [[0]])
        self.assertEqual(model.document['metadata']['events'][0]['correlated_component_separators'], 1)


class CircuitNativeTests(unittest.TestCase):
    def test_completed_exclusion_witness_and_audit(self):
        model = hyperedge_model()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for weighted in (False, True):
                out = root / str(weighted)
                result = certify_circuit(model, out, cutoff=1, seconds=5, weighted=weighted)
                self.assertEqual(result['status'], 'EXCLUDED')
                self.assertEqual(result['exact_distance'], 2)
                self.assertEqual(result['terminal']['roots_completed'], model.n)
                self.assertEqual(audit_circuit(out), result)
            result = certify_circuit(model, root / 'witness', cutoff=2, seconds=5)
            self.assertEqual(result['status'], 'WITNESS_FOUND')
            self.assertIsNone(result['distance_lower_bound'])
            self.assertEqual(result['distance_upper_bound'], 2)
            self.assertEqual(audit_circuit(root / 'witness'), result)

    def test_neutral_pruning_preserves_distance(self):
        model = DetectorModel.from_sparse(5, [[0, 1, 3], [1, 2, 3, 4]], [[0, 2]],
                                         neutral_rows=[[0, 1, 2]])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for weighted in (False, True):
                for neutral in (False, True):
                    result = certify_circuit(model, root / f'{weighted}-{neutral}',
                                              cutoff=2, seconds=5, weighted=weighted, neutral=neutral)
                    self.assertEqual(result['status'], 'WITNESS_FOUND')
                    self.assertEqual(result['distance_upper_bound'], 2)

    def test_high_degree_more_than_8192_faults_and_multiple_observables(self):
        model = DetectorModel.from_sparse(9001, [list(range(9001))], [[0], [9000]],
                                         witnesses=[[0, 1]])
        with tempfile.TemporaryDirectory() as tmp:
            result = certify_circuit(model, Path(tmp)/'run', cutoff=1, seconds=5)
            self.assertEqual(result['exact_distance'], 2)
            self.assertEqual(result['terminal']['max_detector_degree'], 9001)
            self.assertEqual(result['terminal']['roots_completed'], 9001)

    def test_detector_free_fault_and_incomplete_never_lower_bound(self):
        model = DetectorModel.from_sparse(2, [[1]], [[0]])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = certify_circuit(model, root/'d1', cutoff=1, seconds=5)
            self.assertEqual(result['distance_upper_bound'], 1)
            result = certify_circuit(model, root/'limited', cutoff=1, seconds=5, node_cap=0)
            self.assertEqual(result['status'], 'INCOMPLETE')
            self.assertIsNone(result['distance_lower_bound'])
            self.assertEqual(audit_circuit(root/'limited'), result)
            result = certify_circuit(model, root/'timeout', cutoff=1, seconds=0.000001)
            self.assertEqual(result['status'], 'INCOMPLETE')
            self.assertIsNone(result['distance_lower_bound'])

    def test_tampered_coverage_rejected_even_after_rehash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'run'
            certify_circuit(hyperedge_model(), root, cutoff=1, seconds=5)
            receipt = json.loads((root/'receipt.json').read_text())
            events = [json.loads(line) for line in receipt['stdout'].splitlines()]
            events[-1]['roots_completed'] = 1
            receipt['stdout'] = '\n'.join(json.dumps(e) for e in events)+'\n'
            (root/'receipt.json').write_bytes(json_bytes(receipt))
            hashes = json.loads((root/'SHA256SUMS.json').read_text())
            hashes['files']['receipt.json'] = digest((root/'receipt.json').read_bytes())
            (root/'SHA256SUMS.json').write_bytes(json_bytes(hashes))
            with self.assertRaisesRegex(ValueError, 'all-root'):
                audit_circuit(root)

    def test_relocated_record_and_malformed_timing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'original'
            result = certify_circuit(hyperedge_model(), root, cutoff=1, seconds=5)
            relocated = Path(tmp)/'relocated'
            shutil.copytree(root, relocated)
            shutil.rmtree(root)
            self.assertEqual(audit_circuit(relocated), result)
            receipt = json.loads((relocated/'receipt.json').read_text())
            receipt['timing']['end_to_end_seconds'] = -1
            (relocated/'receipt.json').write_bytes(json_bytes(receipt))
            hashes = json.loads((relocated/'SHA256SUMS.json').read_text())
            hashes['files']['receipt.json'] = digest((relocated/'receipt.json').read_bytes())
            (relocated/'SHA256SUMS.json').write_bytes(json_bytes(hashes))
            with self.assertRaisesRegex(ValueError, 'timing'):
                audit_circuit(relocated)


if __name__ == '__main__':
    unittest.main()
