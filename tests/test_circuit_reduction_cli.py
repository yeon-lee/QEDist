"""Exercise reduction commands and their independent audit through the public CLI."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from cssdist.circuit import DetectorModel
from cssdist.cli import main


class CircuitReductionCLITests(unittest.TestCase):
    def invoke(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main(list(map(str, args)))
        return result, stdout.getvalue(), stderr.getvalue()

    def test_public_reduction_audit_and_existing_output_protection(self):
        # Full signatures: D0 L0, D0, D1, D0 D1 L0, D0 D1.
        source = DetectorModel.from_sparse(
            5, [[0, 1, 3, 4], [2, 3, 4]], [[0, 3]],
            neutral_rows=[[0, 2, 3], [1, 2, 4]], witnesses=[[0, 1]])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path, reduced_path = root / 'source.json', root / 'reduced.json'
            certificate_path, indices_path = root / 'certificate.json', root / 'keep.json'
            source.save(source_path)
            indices_path.write_text('[0]')
            command = ('reduce-circuit', source_path, '--keep-detectors', indices_path,
                       '--output', reduced_path, '--certificate', certificate_path)
            code, _, error = self.invoke(*command)
            self.assertEqual(code, 0, error)
            reduced = DetectorModel.load(reduced_path)
            self.assertEqual(reduced.n, 2)
            self.assertEqual(len(reduced.detectors), 1)
            self.assertEqual(reduced.check_witness([0, 1])['weight'], 2)
            code, _, error = self.invoke('audit-circuit-reduction', source_path,
                                         reduced_path, certificate_path)
            self.assertEqual(code, 0, error)
            original_bytes = reduced_path.read_bytes(), certificate_path.read_bytes()
            self.assertEqual(self.invoke(*command)[0], 2)
            self.assertEqual(original_bytes,
                             (reduced_path.read_bytes(), certificate_path.read_bytes()))
            wrong_source = dict(source.document, observable_rows=[[0]])
            wrong_source.pop('neutral_rows')
            wrong_source.pop('witnesses')
            source_path.write_text(json.dumps(wrong_source))
            self.assertEqual(self.invoke('audit-circuit-reduction', source_path,
                                         reduced_path, certificate_path)[0], 2)

    def test_projection_without_column_closure_fails_before_writing(self):
        source = DetectorModel.from_sparse(1, [[0], [0]], [[0]])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source.save(root / 'source.json')
            (root / 'keep.json').write_text('[0]')
            result = self.invoke('reduce-circuit', root / 'source.json',
                                 '--keep-detectors', root / 'keep.json',
                                 '--output', root / 'reduced.json',
                                 '--certificate', root / 'certificate.json')
            self.assertEqual(result[0], 2)
            self.assertFalse((root / 'reduced.json').exists())
            self.assertFalse((root / 'certificate.json').exists())


if __name__ == '__main__':
    unittest.main()
