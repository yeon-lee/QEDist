"""Malformed proof JSON must fail closed with the documented CLI error contract."""
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

from cssdist import CSSCode
from cssdist.calibration import calibrate
from cssdist.campaign import certify
from cssdist.code import digest, json_bytes


class MalformedContainerTests(unittest.TestCase):
    def assert_cli_error(self, action, path, message=None):
        result = subprocess.run([sys.executable, '-m', 'cssdist', action, str(path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, '')
        error = json.loads(result.stderr)
        self.assertEqual(error['status'], 'ERROR_NO_NEW_LOWER_BOUND')
        if message:
            self.assertIn(message, error['error'])

    def test_top_level_nonobjects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for action, filename in [('audit', 'campaign.json'),
                                     ('audit-calibration', 'calibration.json')]:
                folder = root/action
                folder.mkdir()
                for value in ([], None, False, 7, 'invalid'):
                    with self.subTest(action=action, value=value):
                        (folder/filename).write_text(json.dumps(value))
                        self.assert_cli_error(action, folder, 'must be a JSON object')
            for value in ([], None, False, 7, 'invalid'):
                with self.subTest(action='audit-bundle', value=value):
                    archive = root/'bad.tar.gz'
                    with tarfile.open(archive, 'w:gz') as handle:
                        data = json_bytes(value)
                        item = tarfile.TarInfo('MANIFEST.json')
                        item.size = len(data)
                        handle.addfile(item, io.BytesIO(data))
                    self.assert_cli_error('audit-bundle', archive, 'must be a JSON object')

    def test_campaign_nested_containers(self):
        code = CSSCode.from_sparse(4, [[0, 1, 2, 3]], [[0, 1, 2, 3]],
                                   sector_exchange=list(range(4)))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'campaign'
            certify(code, root, cutoff=1)
            campaign_path = root/'campaign.json'
            campaign = json.loads(campaign_path.read_text())
            for field in ('config', 'engine', 'input_sha256'):
                for invalid in ([], None):
                    changed = copy.deepcopy(campaign)
                    changed[field] = invalid
                    campaign_path.write_bytes(json_bytes(changed))
                    with self.subTest(field=field, invalid=invalid):
                        self.assert_cli_error('audit', root, 'must be a JSON object')
            campaign_path.write_bytes(json_bytes(campaign))
            receipt_path = next(root.glob('jobs/*/*/attempt-*/receipt.json'))
            receipt = json.loads(receipt_path.read_text())
            for invalid in ([], None, dict(receipt, limits=[]), dict(receipt, limits=None)):
                receipt_path.write_bytes(json_bytes(invalid))
                with self.subTest(receipt=invalid):
                    self.assert_cli_error('audit', root, 'must be a JSON object')
            receipt_path.write_bytes(json_bytes(receipt))
            build_path = root/'engine/build.json'
            build = json.loads(build_path.read_text())
            for invalid in ([], None, dict(build, identity=[]), dict(build, identity=None)):
                build_path.write_bytes(json_bytes(invalid))
                changed = copy.deepcopy(campaign)
                changed['engine']['build_sha256'] = digest(build_path.read_bytes())
                campaign_path.write_bytes(json_bytes(changed))
                with self.subTest(build=invalid):
                    self.assert_cli_error('audit', root, 'must be a JSON object')

    def test_calibration_nested_containers(self):
        code = CSSCode.from_sparse(4, [[0, 1, 2, 3]], [[0, 1, 2, 3]],
                                   sector_exchange=list(range(4)))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'calibration'
            calibrate(code, root, cutoff=1, samples=1)
            path = root/'calibration.json'
            calibration = json.loads(path.read_text())
            for field in ('config', 'engine', 'input_sha256'):
                for invalid in ([], None):
                    changed = copy.deepcopy(calibration)
                    changed[field] = invalid
                    path.write_bytes(json_bytes(changed))
                    with self.subTest(field=field, invalid=invalid):
                        self.assert_cli_error('audit-calibration', root, 'must be a JSON object')
            for invalid in ([], None):
                changed = copy.deepcopy(calibration)
                changed['engine']['identity'] = invalid
                path.write_bytes(json_bytes(changed))
                self.assert_cli_error('audit-calibration', root, 'must be a JSON object')
            path.write_bytes(json_bytes(calibration))
            receipt = next(root.glob('roots/*/*/receipt.json'))
            for invalid in ([], None):
                receipt.write_bytes(json_bytes(invalid))
                self.assert_cli_error('audit-calibration', root, 'must be a JSON object')


if __name__ == '__main__':
    unittest.main()
