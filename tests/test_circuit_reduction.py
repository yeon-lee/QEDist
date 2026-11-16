"""Exhaustive small-model and tamper controls for exact sector projection."""
import copy
import itertools
import random
import tempfile
import unittest
from pathlib import Path

from cssdist.circuit import DetectorModel
from cssdist.circuit_reduction import (reduce_detector_sector, verify_sector_reduction,
    project_fault_support, lift_reduced_witness, reduce_stim_sector)


def from_columns(columns, detectors=2, observables=1, **kwargs):
    rows = [[j for j, col in enumerate(columns) if col >> i & 1]
            for i in range(detectors + observables)]
    return DetectorModel.from_sparse(len(columns), rows[:detectors], rows[detectors:], **kwargs)


def brute_distance(model):
    return min((word.bit_count() for word in range(1, 1 << model.n) if model.is_logical(word)), default=None)


class CircuitReductionTests(unittest.TestCase):
    def model(self):
        return from_columns([5, 1, 2, 7, 3, 5, 4],
                    neutral_rows=[[0, 2, 3], [1, 2, 4], [0, 5], [0, 1, 6]],
                    witnesses=[[0, 4, 2]])

    def test_dedup_zero_cancellation_witness_and_neutrals(self):
        original = self.model()
        snapshot = copy.deepcopy(original.document)
        reduced, certificate = reduce_detector_sector(original, [0])
        self.assertEqual(original.document, snapshot)
        self.assertEqual(certificate['source_to_reduced'], [0, 1, None, 0, 1, 0, 2])
        self.assertEqual(certificate['reduced_to_source'], [0, 1, 6])
        self.assertEqual(reduced.document['neutral_rows'], [[0, 1, 2]])
        self.assertEqual(certificate['source_neutral_to_reduced'], [None, None, None, 0])
        self.assertEqual(reduced.document['witnesses'], [[0, 1]])
        self.assertEqual(lift_reduced_witness([0, 1], certificate, original, reduced), [0, 1])
        self.assertEqual(project_fault_support([0, 3, 2], certificate['source_to_reduced']), [])
        self.assertEqual(brute_distance(original), brute_distance(reduced))
        self.assertTrue(verify_sector_reduction(original, reduced, certificate)['distance_preserved'])

    def test_projection_without_closure_is_rejected(self):
        # Removing detector 1 would create an unavailable undetected logical.
        with self.assertRaisesRegex(ValueError, 'not closed'):
            reduce_detector_sector(from_columns([6]), [0])
        with self.assertRaisesRegex(ValueError, 'no nonzero'):
            reduce_detector_sector(from_columns([2]), [0])

    def test_every_original_witness_projects_and_every_reduced_witness_lifts(self):
        original = self.model()
        reduced, certificate = reduce_detector_sector(original, [0])
        for word in range(1 << original.n):
            if original.is_logical(word):
                indices = [j for j in range(original.n) if word >> j & 1]
                mapped = project_fault_support(indices, certificate['source_to_reduced'])
                self.assertLessEqual(reduced.check_witness(mapped)['weight'], len(indices))
        for word in range(1 << reduced.n):
            if reduced.is_logical(word):
                indices = [j for j in range(reduced.n) if word >> j & 1]
                lifted = lift_reduced_witness(indices, certificate, original, reduced)
                self.assertEqual(len(lifted), len(indices))

    def test_random_projection_closed_models_multiple_observables(self):
        rng = random.Random(1945)
        for _ in range(60):
            columns = {1, *rng.sample(range(1, 32), rng.randint(1, 5))}
            # Three detector rows, two observables; keep detectors 0 and 2.
            columns.update(col & ~2 for col in list(columns) if col & ~2)
            original = from_columns(sorted(columns), detectors=3, observables=2)
            reduced, certificate = reduce_detector_sector(original, [2, 0])
            self.assertEqual(brute_distance(original), brute_distance(reduced))
            self.assertEqual(certificate['kept_detectors'], [0, 2])
            self.assertEqual(verify_sector_reduction(original, reduced, certificate)['observables_preserved'], 2)

    def test_tampered_maps_rejected(self):
        original = self.model()
        reduced, certificate = reduce_detector_sector(original, [0])
        mutations = [lambda c: c['source_to_reduced'].__setitem__(3, 1),
                     lambda c: c['reduced_to_source'].__setitem__(0, 3),
                     lambda c: c['source_to_reduced'].__setitem__(2, False),
                     lambda c: c['kept_detectors'].__setitem__(0, 1),
                     lambda c: c['source_neutral_to_reduced'].__setitem__(0, 0),
                     lambda c: c['projected_witnesses'].__setitem__(0, [2]),
                     lambda c: c.__setitem__('metric', 'probability')]
        for mutate in mutations:
            c = copy.deepcopy(certificate)
            mutate(c)
            with self.assertRaises(ValueError):
                verify_sector_reduction(original, reduced, c)

    def test_rehashed_wrong_observable_bits_rejected(self):
        original = self.model()
        reduced, certificate = reduce_detector_sector(original, [0])
        bad_data = copy.deepcopy(reduced.document)
        bad_data['observable_rows'] = [[1, 2]]
        bad = DetectorModel(bad_data)
        certificate['reduced_fingerprint'] = bad.fingerprint
        with self.assertRaisesRegex(ValueError, 'lift'):
            verify_sector_reduction(original, bad, certificate)

    def test_bad_explicit_indices_rejected(self):
        for kept in ([0, 0], [True], [-1], [2], None, 2):
            with self.assertRaises(ValueError):
                reduce_detector_sector(self.model(), kept)

    def test_detector_coordinates_propose_but_do_not_prove(self):
        try:
            import stim
        except ImportError:
            self.skipTest('Optional Stim not installed')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'example.stim'
            path.write_text('R 0\nM 0\nDETECTOR(0,0,0,0) rec[-1]\nDETECTOR(0,0,0,3) rec[-1]\n')
            reduced, certificate = reduce_stim_sector(self.model(), path, basis='X')
            self.assertEqual(certificate['kept_detectors'], [0])
            self.assertEqual(reduced.n, 3)
            with self.assertRaisesRegex(ValueError, 'No certified'):
                reduce_stim_sector(from_columns([6]), path, basis='X')


if __name__ == '__main__':
    unittest.main()
