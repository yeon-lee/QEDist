import copy
import json
from pathlib import Path
import random
import tempfile
import unittest

from cssdist import CSSCode
from cssdist.audit import audit_run, check_parity_metadata
from cssdist.calibration import calibrate, audit_calibration
from cssdist.campaign import certify
from cssdist.portable import export_bundle, audit_bundle


def even_code():
    return CSSCode.from_sparse(4, [[0,1,2,3]], [[0,1,2,3]],
                               cyclic_period=4, sector_exchange=list(range(4)))


class KernelParityTests(unittest.TestCase):
    def test_rowspace_test_matches_direct_kernel_enumeration(self):
        rng = random.Random(793)
        for n in range(1,9):
            for _ in range(20):
                rows = [rng.randrange(1<<n) for _ in range(rng.randrange(n+2))]
                supports = [[j for j in range(n) if (v>>j)&1] for v in rows]
                code = CSSCode.from_sparse(n, supports, [])
                expected = all(v.bit_count()%2 == 0 for v in range(1<<n)
                               if all((v&r).bit_count()%2 == 0 for r in rows))
                self.assertIs(code.kernel_even_weight('Z'), expected)
                self.assertFalse(code.kernel_even_weight('X'))
        with self.assertRaisesRegex(ValueError, 'Sector must'):
            even_code().kernel_even_weight('Y')

    def test_even_representatives_are_not_an_even_kernel(self):
        # Each quotient class has an even representative after adding e0,
        # but the kernel still contains weight-one logicals e1 and e2.
        code = CSSCode.from_sparse(3, [], [[0]])
        self.assertFalse(code.kernel_even_weight('Z'))
        self.assertTrue(code.is_logical(2, 'Z'))

    def test_native_certificate_is_checked_independently(self):
        code = even_code()
        cfg = {'native_profile':'css', 'cutoff':1}
        good = {'kernel_even':True, 'parity_cutoff_enabled':True, 'effective_W':0,
                'parity_trivial_exclusion':True, 'parity_certificate_rows':[0],
                'nodes':0, 'status':'excluded', 'frontier_seen':0,
                'frontier_owned':0, 'common_nodes':0}
        self.assertTrue(check_parity_metadata(good, code, cfg, 'Z'))
        mutations = {'kernel_even':False, 'parity_cutoff_enabled':False,
                     'effective_W':1, 'parity_trivial_exclusion':False,
                     'parity_certificate_rows':[], 'nodes':1, 'status':'incomplete',
                     'frontier_seen':1}
        for key, value in mutations.items():
            bad = copy.deepcopy(good); bad[key] = value
            with self.assertRaises(ValueError, msg=key):
                check_parity_metadata(bad, code, cfg, 'Z')
        for rows in ([True], [0,0], [-1], [1], '0'):
            bad = dict(good, parity_certificate_rows=rows)
            with self.assertRaises(ValueError):
                check_parity_metadata(bad, code, cfg, 'Z')


class ParitySearchTests(unittest.TestCase):
    def test_zero_node_algebraic_exclusion_shards_and_portable_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'run'
            result = certify(even_code(), out, cutoff=1, shards=3, workers=2,
                             profile='css')
            self.assertEqual(result['exact_distance'], 2)
            self.assertEqual(result['nodes_in_recorded_attempts'], 0)
            self.assertEqual(audit_run(out)['exact_distance'], 2)
            archive = Path(tmp)/'bundle.tar.gz'
            export_bundle(out, archive)
            self.assertEqual(audit_bundle(archive)['result']['exact_distance'], 2)

    def test_zero_node_calibration_remains_noncertifying(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'pilot'
            result = calibrate(even_code(), out, cutoff=1, samples=1,
                               profile='css')
            self.assertEqual(result['sectors']['Z']['status'], 'ALL_ROOTS_MEASURED')
            self.assertIsNone(result['distance_claim'])
            self.assertEqual(result, audit_calibration(out))
            self.assertEqual(result['records'][0]['nodes'], 0)

    def test_even_cutoff_and_odd_kernel_match_known_distances(self):
        odd = CSSCode.from_sparse(3, [], [[0]])
        rows = [[0,2,4,6], [1,2,5,6], [3,4,5,6]]
        steane = CSSCode.from_sparse(7, rows, rows, sector_exchange=list(range(7)))
        cases = [(even_code(), 2, 2), (odd, 1, 1), (steane, 2, 3), (steane, 3, 3)]
        with tempfile.TemporaryDirectory() as tmp:
            for index, (code, cutoff, distance) in enumerate(cases):
                result = certify(code, Path(tmp)/str(index), cutoff=cutoff,
                                 profile='css', shards=3, seconds_per_shard=1)
                self.assertLessEqual(result['distance_lower_bound'], distance)
                self.assertEqual(result['distance_upper_bound'], distance)
                if cutoff < distance:
                    self.assertEqual(result['exact_distance'], distance)


if __name__ == '__main__':
    unittest.main()
