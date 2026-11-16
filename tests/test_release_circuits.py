import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cssdist import DetectorModel
from cssdist.circuit_run import audit_circuit, certify_circuit, _conclusion
from cssdist.cli import write_new_pair
from cssdist.code import digest, json_bytes
from cssdist.portable import export_bundle, audit_bundle


def rehash(root, name, value):
    (root / name).write_bytes(json_bytes(value))
    manifest = json.loads((root / 'SHA256SUMS.json').read_text())
    manifest['files'][name] = digest((root / name).read_bytes())
    (root / 'SHA256SUMS.json').write_bytes(json_bytes(manifest))


class CircuitReleaseTests(unittest.TestCase):
    def test_portable_direct_and_window(self):
        model = DetectorModel.from_sparse(3, [[0, 1], [1, 2]], [[0]], witnesses=[[0, 1, 2]])
        with tempfile.TemporaryDirectory() as tmp:
            for mode in ({}, {'detectors_per_layer': 1}):
                root = Path(tmp) / ('window' if mode else 'direct')
                result = certify_circuit(model, root, cutoff=2, **mode)
                self.assertEqual(result['exact_distance'], 3)
                self.assertEqual((root / 'engine/LICENSE.txt').read_bytes(),
                                 (Path(__file__).resolve().parents[1] / 'LICENSE').read_bytes())
                archive = root.with_suffix('.tar.gz')
                with patch('subprocess.Popen', side_effect=AssertionError('audit executed a child')):
                    self.assertEqual(export_bundle(root, archive)['kind'], 'circuit')
                    self.assertEqual(audit_bundle(archive)['result'], result)

    def test_circuit_audit_rejects_inconsistent_records_after_rehash(self):
        model = DetectorModel.from_sparse(2, [[0, 1]], [[0]], witnesses=[[0, 1]])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'run'
            certify_circuit(model, root, cutoff=1)
            receipt = json.loads((root / 'receipt.json').read_text())
            config = json.loads((root / 'config.json').read_text())
            late = dict(receipt, external_timeout=True)
            result = _conclusion(model, config, late)
            self.assertEqual(result['status'], 'INCOMPLETE')
            self.assertIsNone(result['distance_lower_bound'])
            for field, value, message in [('stdout', receipt['stdout'] + '{"event":"invalid"}\n', 'event'),
                                          ('external_timeout', 0, 'status')]:
                rehash(root, 'receipt.json', dict(receipt, **{field: value}))
                with self.assertRaisesRegex(ValueError, message):
                    audit_circuit(root)
            altered = copy.deepcopy(receipt)
            altered['command'][3] = '0'
            rehash(root, 'receipt.json', altered)
            with self.assertRaisesRegex(ValueError, 'budget'):
                audit_circuit(root)
            rehash(root, 'receipt.json', receipt)
            manifest = json.loads((root / 'SHA256SUMS.json').read_text())
            del manifest['files']['engine/exact.cpp']
            (root / 'SHA256SUMS.json').write_bytes(json_bytes(manifest))
            with self.assertRaisesRegex(ValueError, 'required'):
                audit_circuit(root)

    def test_pair_rollback_preserves_other_writer(self):
        import os
        link = os.link
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'model', Path(tmp) / 'certificate'
            def racing_link(src, dst):
                if dst == b:
                    b.write_bytes(b'other writer')
                link(src, dst)
            with patch('cssdist.cli.os.link', side_effect=racing_link), self.assertRaises(FileExistsError):
                write_new_pair((a, b'first'), (b, b'second'))
            self.assertFalse(a.exists())
            self.assertEqual(b.read_bytes(), b'other writer')
