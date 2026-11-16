"""Check the two physical sectors, their quotient spaces, and campaign coverage."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import random
import shutil
import tempfile
import unittest

from cssdist import CSSCode, cyclic_lp
from cssdist.algebra import basis, remainder, support, vector
from cssdist.audit import audit_run
from cssdist.campaign import certify
from cssdist.calibration import calibrate
from cssdist.cli import main
from cssdist.code import digest, json_bytes
from cssdist.lp_blocks import layout, search_problems
from cssdist.portable import audit_bundle, export_bundle


PROFILE = 'lp'


class LPBlockTests(unittest.TestCase):
    def test_cli_lists_both_tensor_parts_in_each_required_sector(self):
        source = Path(__file__).resolve().parents[1] / 'examples/independent_qc.json'
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(['inspect', str(source), '--profile', PROFILE]), 0)
        parts = json.loads(output.getvalue())['lp_search_tasks']
        self.assertEqual(set(parts), {'X-anchor', 'X-stripe', 'Z-anchor', 'Z-stripe'})
        self.assertTrue(all(part['roots'] > 0 for part in parts.values()))

    def test_split_cannot_inherit_a_whole_code_root_estimate(self):
        code = cyclic_lp([[1, 1]], [[1, 0]])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'calibration'
            with self.assertRaisesRegex(ValueError, 'two different root sets'):
                calibrate(code, out, cutoff=1, profile=PROFILE)
            self.assertFalse(out.exists())

    def test_source_inventory_and_links_are_rejected(self):
        code = cyclic_lp([[1, 1]], [[1, 0]])
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / 'run'
            certify(code, run, cutoff=1, profile=PROFILE)
            extra = run / 'engine/untracked.cpp'
            extra.write_text('// untracked')
            with self.assertRaisesRegex(ValueError, 'inventory'):
                audit_run(run)
            extra.unlink()
            source = run / 'engine/even_methods.inc'
            moved = Path(tmp) / 'outside.inc'
            source.rename(moved)
            source.symlink_to(moved)
            with self.assertRaisesRegex(ValueError, 'regular file'):
                audit_run(run)

    def test_physical_quotients_and_distances_in_both_sectors(self):
        rng = random.Random(401)
        cases = [cyclic_lp([[1, 1]], [[1, 0]]), cyclic_lp([[1, 1], [1, 1]], [[1], [1]]),
                 cyclic_lp([[0, 0]], [[0, 0]]),
                 cyclic_lp([[1, [[1, 1]]]], [[[[1, 1]], 1]], period=2)]
        cases += [cyclic_lp([[1, 2]], [[1, 3]], field=4, check_basis=basis_name)
                  for basis_name in ('raw', 'balanced', 'redundant')]
        for i in range(10):
            a = [[rng.randrange(2) for _ in range(1 + i % 2)]]
            c = [[rng.randrange(2) for _ in range(2)] for _ in range(1 + i % 2)]
            cases.append(cyclic_lp(a, c, period=1 + (i % 3 == 0)))
        placement_dependent = common_nonzero = False
        with tempfile.TemporaryDirectory() as directory:
            for i, code in enumerate(cases):
                if code.k == 0:
                    continue
                sa, sc, fiber = layout(code)
                parts = search_problems(code, {'sectors': ['X', 'Z'], 'lp_anchor_site': sa * sc * fiber})
                distances = {}
                for sector in ('X', 'Z'):
                    local = parts[sector + '-stripe']
                    local_stabilizers = basis(local.stabilizers)
                    common_nonzero |= bool(local_stabilizers)
                    for word in range(1 << local.n):
                        if any((h & word).bit_count() % 2 for h in local.checks):
                            continue
                        placements = []
                        for blocks in local.stripes:
                            full = sum(1 << (blocks[j // local.fiber] * local.fiber + j % local.fiber)
                                       for j in support(word))
                            placements.append(code.is_logical(full, sector))
                        placement_dependent |= any(placements) and not all(placements)
                        self.assertEqual(bool(remainder(word, local_stabilizers)), any(placements))
                    distances[sector] = min(w.bit_count() for w in range(1, 1 << code.n)
                                            if code.is_logical(w, sector))
                for cutoff in (1, 2, 3):
                    path = Path(directory) / f'{i}-{cutoff}'
                    result = certify(code, path, cutoff=cutoff, profile=PROFILE,
                                     use_symmetry=i % 2 == 0, coset_pruning=i % 3 != 0,
                                     shards=2, workers=2)
                    for sector in ('X', 'Z'):
                        bounds = result['sector_bounds'][sector]
                        self.assertEqual(bounds['lower'] > cutoff, distances[sector] > cutoff)
                        self.assertLessEqual(distances[sector], bounds['upper'])
                        self.assertTrue(code.is_logical(vector(bounds['witness'], code.n), sector))
        self.assertTrue(placement_dependent)
        self.assertTrue(common_nonzero)

    def test_row_equivalent_layout_and_rejection_of_false_layout(self):
        code = cyclic_lp([[1, 1]], [[1, 0]])
        doc = copy.deepcopy(code.document)
        doc['hx'][0] = support(code.hx[0] ^ code.hx[1])
        rows = search_problems(CSSCode(doc), {'sectors': ['Z'], 'lp_anchor_site': 4})['Z-stripe'].checks
        self.assertEqual(len(basis(rows)), 1)
        doc.update(hx=[[0, 1]], hz=[], witnesses={})
        with self.assertRaisesRegex(ValueError, 'couple'):
            search_problems(CSSCode(doc), {'sectors': ['Z'], 'lp_anchor_site': 4})
        doc['construction']['period'] = 2
        with self.assertRaisesRegex(ValueError, 'period'):
            search_problems(CSSCode(doc), {'sectors': ['Z'], 'lp_anchor_site': 4})

    def test_missing_stripe_resume_portable_and_root_tampering(self):
        code = cyclic_lp([[1, 1]], [[1, 1, 0], [0, 1, 1]])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            options = dict(cutoff=1, profile=PROFILE, shards=2, workers=2)
            result = certify(code, root, **options)
            self.assertEqual(result['exact_distance'], 2)
            shutil.rmtree(root / 'jobs/Z-stripe/000001')
            self.assertEqual(audit_run(root)['sector_bounds']['Z']['lower'], 1)
            result = certify(code, root, resume=True, **options)
            self.assertEqual(result['last_invocation']['jobs_run'], 1)
            bundle = Path(directory) / 'resumed.tar.gz'
            export_bundle(root, bundle)
            self.assertEqual(audit_bundle(bundle)['result']['exact_distance'], 2)
            with self.assertRaisesRegex(ValueError, 'same code'):
                certify(code, root, cutoff=1, resume=True)
            receipt_path = next((root / 'jobs/Z-anchor').glob('*/attempt-*/receipt.json'))
            receipt = json.loads(receipt_path.read_text())
            result = receipt['terminal']
            result['anchor_site'] = 0
            stdout = json_bytes(result).replace(b'\n', b'') + b'\n'
            (receipt_path.parent / 'stdout.jsonl').write_bytes(stdout)
            receipt['stdout_sha256'] = digest(stdout)
            receipt_path.write_bytes(json_bytes(receipt))
            with self.assertRaisesRegex(ValueError, 'partition'):
                audit_run(root)
