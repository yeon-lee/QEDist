from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest

from cssdist import CSSCode, cyclic_lp
from cssdist.algebra import same_span
from cssdist.cli import main
from cssdist.formats import import_css_matrices, matrix_market_text, read_matrix_market


class MatrixMarketTests(unittest.TestCase):
    def test_roundtrip_independent_binary_and_quaternary_checks(self):
        codes = [cyclic_lp([[1,1]], [[1,1,0],[0,1,1]], period=3),
                 cyclic_lp([[1,2,3]], period=4, field=4, check_basis='balanced')]
        with tempfile.TemporaryDirectory() as tmp:
            for code in codes:
                hx, hz = Path(tmp)/'x.mtx', Path(tmp)/'z.mtx'
                hx.write_text(matrix_market_text(code.hx,code.n))
                hz.write_text(matrix_market_text(code.hz,code.n))
                restored = import_css_matrices(hx,hz,period=code.period)
                self.assertEqual((restored.n,restored.k),(code.n,code.k))
                self.assertEqual(restored.hx,code.hx)
                self.assertEqual(restored.hz,code.hz)
                self.assertTrue(same_span(restored.hx,code.hx))
                self.assertIsNone(restored.exchange)  # Never inferred from a filename.

    def test_pattern_comments_duplicates_zero_entries_and_empty_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'m.mtx'
            p.write_text('%%MatrixMarket matrix coordinate pattern general\n% test\n3 4 4\n1 2\n1 2\n\n2 4\n3 1\n')
            self.assertEqual(read_matrix_market(p),(4,[[],[3],[0]]))
            p.write_text('%%MatrixMarket matrix coordinate integer general\n2 3 3\n1 1 0\n2 2 1\n2 3 1\n')
            self.assertEqual(read_matrix_market(p),(3,[[],[1,2]]))
            p.write_text(matrix_market_text([],5))
            self.assertEqual(read_matrix_market(p),(5,[]))

    def test_malformed_and_unsupported_formats_are_rejected(self):
        header='%%MatrixMarket matrix coordinate integer general\n'
        bad=['', '%%MatrixMarket matrix array integer general\n1 1\n1\n',
             '%%MatrixMarket matrix coordinate real general\n1 1 1\n1 1 1.0\n',
             '%%MatrixMarket matrix coordinate integer symmetric\n1 1 1\n1 1 1\n',
             header+'2 2 2\n1 1 1\n', header+'2 2 0\n1 1 1\n',
             header+'2 2 1\n0 1 1\n', header+'2 2 1\n1 3 1\n',
             header+'2 2 1\n1 1 2\n', header+'2 2 1\n1 1 -1\n',
             header+'2 2 1\n1 1 1.0\n', header+'-1 2 0\n', header+'1 0 0\n']
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.mtx'
            for content in bad:
                p.write_text(content)
                with self.assertRaises(ValueError,msg=content):
                    read_matrix_market(p)

    def test_commutation_dimensions_and_symmetry_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            x,z=Path(tmp)/'x.mtx',Path(tmp)/'z.mtx'
            x.write_text(matrix_market_text([1],4));z.write_text(matrix_market_text([1],4))
            with self.assertRaisesRegex(ValueError,'commutation'):
                import_css_matrices(x,z)
            z.write_text(matrix_market_text([],3))
            with self.assertRaisesRegex(ValueError,'column counts'):
                import_css_matrices(x,z)
            z.write_text(matrix_market_text([],4))
            with self.assertRaisesRegex(ValueError,'cyclic action'):
                import_css_matrices(x,z,period=4)

    def test_cli_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.json';x=root/'x.mtx';z=root/'z.mtx';target=root/'target.json'
            CSSCode.from_sparse(4,[[0,1,2,3]],[[0,1,2,3]],cyclic_period=4).save(source)
            def call(args):
                with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                    return main(args)
            self.assertEqual(call(['export-matrices',str(source),'--hx',str(x),'--hz',str(z)]),0)
            original=x.read_bytes()
            self.assertEqual(call(['export-matrices',str(source),'--hx',str(x),'--hz',str(z)]),2)
            self.assertEqual(x.read_bytes(),original)
            self.assertEqual(call(['import-matrices',str(x),str(z),'--period','4','--output',str(target)]),0)
            self.assertEqual(CSSCode.load(target).k,2)
            self.assertEqual(call(['import-matrices',str(x),str(z),'--output',str(target)]),2)


if __name__=='__main__':
    unittest.main()
