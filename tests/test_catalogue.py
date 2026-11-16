"""Keep the published catalogue, portable inputs and replay settings aligned."""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import catalogue


class CatalogueTests(unittest.TestCase):
    def test_input_inventory_and_unique_rows(self):
        document = catalogue.catalogue()
        rows = document['rows']
        self.assertEqual(len(rows), document['counts']['table_rows'])
        self.assertEqual(len({row['id'] for row in rows}), len(rows))
        files = {row['input']: row['input_sha256'] for row in rows}
        self.assertEqual(len(files), document['counts']['unique_inputs'])
        for name, expected in files.items():
            self.assertEqual(hashlib.sha256((catalogue.ROOT / name).read_bytes()).hexdigest(), expected)
        for row in rows:
            self.assertEqual(row['recommended_cutoff'], row['result']['lower'] - 1)
            self.assertEqual(row['configuration']['cutoff'], row['recommended_cutoff'])

    def test_document_is_generated_from_manifest(self):
        expected = catalogue.markdown(catalogue.catalogue())
        self.assertEqual((catalogue.ROOT / 'docs/catalogue.md').read_text(), expected)

    def test_small_physical_input(self):
        row = next(r for r in catalogue.catalogue()['rows'] if r['id'] == 'LP04-175')
        code = catalogue.checked_input(row)
        self.assertEqual((code.n, code.k), (175, 19))

    def test_sector_result_and_saved_settings(self):
        row = next(r for r in catalogue.catalogue()['rows'] if r['id'] == 'TT180-k12')
        # The paper row is X-only. A low Z distance must not be reported as
        # failure to reproduce the X-sector exclusion.
        result = {'status': 'CERTIFIED_INTERVAL',
                  'sector_bounds': {'X': {'lower': 20, 'upper': 20},
                                    'Z': {'lower': 4, 'upper': 4}},
                  'last_invocation': {'workers': 1}}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            args = argparse.Namespace(output=output, shards=None, workers=1,
                                      seconds_per_shard=1, resume=False, proposed_additions=None,
                                      large_capacity=None)
            with patch.object(catalogue, 'checked_input', return_value=object()), \
                    patch.object(catalogue, 'certify', return_value=result) as search, \
                    patch.object(catalogue, 'audit_run', return_value=result), \
                    redirect_stdout(io.StringIO()):
                catalogue.run(row, args)
            report = json.loads((output / 'catalogue-replay.json').read_text())
            self.assertEqual(report['fresh_lower'], 20)
            self.assertTrue(report['fresh_exact'])
            self.assertFalse(search.call_args.kwargs['proposed_additions'])
            args.resume = True
            with patch.object(catalogue, 'checked_input', return_value=object()), \
                    patch.object(catalogue, 'certify', return_value=result) as search, \
                    patch.object(catalogue, 'audit_run', return_value=result), \
                    redirect_stdout(io.StringIO()):
                catalogue.run(row, args)
            self.assertIsNone(search.call_args.kwargs['proposed_additions'])


if __name__ == '__main__':
    unittest.main()
