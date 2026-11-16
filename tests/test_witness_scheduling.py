from pathlib import Path
import tempfile
import unittest

from cssdist import CSSCode
from cssdist.audit import audit_run
from cssdist.campaign import certify


class WitnessSchedulingTests(unittest.TestCase):
    def test_checked_witness_stops_unstarted_shards_and_can_resume(self):
        code = CSSCode.from_sparse(8, [], [], cyclic_period=8,
                                   sector_exchange=list(range(8)))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'run'
            result = certify(code, out, cutoff=1, shards=64, workers=1,
                             stop_on_witness=True)
            invocation = result['last_invocation']
            self.assertTrue(invocation['stopped_for_witness'])
            self.assertGreater(invocation['jobs_not_started'], 0)
            self.assertLess(invocation['jobs_run'], 64)
            self.assertEqual(result['distance_lower_bound'], 1)
            self.assertFalse(result['all_required_shards_excluded'])
            self.assertTrue(any(j['status'] == 'pending' for j in result['jobs']))
            self.assertEqual(audit_run(out)['exact_distance'], 1)
            again = certify(code, out, cutoff=1, shards=64, workers=1,
                            stop_on_witness=True, resume=True)
            self.assertEqual(again['last_invocation']['jobs_run'], 0)
            finished = certify(code, out, cutoff=1, shards=64, workers=2,
                               stop_on_witness=False, resume=True)
            self.assertFalse(any(j['status'] == 'pending' for j in finished['jobs']))
            self.assertEqual(finished['exact_distance'], 1)

    def test_completion_without_witness_keeps_every_shard(self):
        rows = [[0,2,4,6], [1,2,5,6], [3,4,5,6]]
        code = CSSCode.from_sparse(7, rows, rows, sector_exchange=list(range(7)))
        with tempfile.TemporaryDirectory() as tmp:
            result = certify(code, Path(tmp)/'run', cutoff=2, shards=4, workers=2,
                             stop_on_witness=True)
            self.assertEqual(result['last_invocation']['jobs_run'], 4)
            self.assertFalse(result['last_invocation']['stopped_for_witness'])
            self.assertTrue(result['all_required_shards_excluded'])
            self.assertEqual(result['exact_distance'], 3)

    def test_option_type_is_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'boolean'):
                certify(CSSCode.from_sparse(1, [], []), Path(tmp)/'run', cutoff=1,
                        stop_on_witness=1)


if __name__ == '__main__':
    unittest.main()
