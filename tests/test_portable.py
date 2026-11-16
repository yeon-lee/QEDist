import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from cssdist import CSSCode
from cssdist.calibration import calibrate
from cssdist.campaign import certify
from cssdist.code import digest,json_bytes
from cssdist.portable import export_bundle,audit_bundle


def code():
    rows=[[0,2,4,6],[1,2,5,6],[3,4,5,6]]
    return CSSCode.from_sparse(7,rows,rows,sector_exchange=list(range(7)))


def rewrite_archive(source,target,change):
    with tarfile.open(source,'r:gz') as archive:
        contents={p.name:archive.extractfile(p).read() for p in archive}
    change(contents)
    with tarfile.open(target,'w:gz') as archive:
        for name,data in contents.items():
            entry=tarfile.TarInfo(name);entry.size=len(data);archive.addfile(entry,io.BytesIO(data))


class PortableTests(unittest.TestCase):
    def test_deterministic_export_and_audit_do_not_execute_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'run'
            expected=certify(code(),out,cutoff=2,seconds_per_shard=1)
            # Arbitrary stored summaries are not trusted as distance claims.
            (out/'result.json').write_text('{"exact_distance":99}')
            with patch('subprocess.run',side_effect=AssertionError('No execution permitted')):
                a=export_bundle(out,root/'a.tar.gz');b=export_bundle(out,root/'b.tar.gz')
                self.assertEqual(a['sha256'],b['sha256'])
                result=audit_bundle(root/'a.tar.gz')
                self.assertEqual(result['result']['exact_distance'],expected['exact_distance'])
                self.assertFalse(result['executed_archived_code'])
            with tarfile.open(root/'a.tar.gz','r:gz') as archive:
                self.assertIn('checker/cssdist/audit.py',archive.getnames())
                self.assertIn('evidence/engine/exact.cpp',archive.getnames())
                project_license = (Path(__file__).resolve().parents[1] / 'LICENSE').read_bytes()
                for path in ('checker/cssdist/LICENSE.txt', 'evidence/engine/LICENSE.txt'):
                    self.assertEqual(archive.extractfile(path).read(), project_license)

    def test_incomplete_and_calibration_evidence_remain_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            certify(code(),root/'incomplete',cutoff=2,node_cap=1)
            export_bundle(root/'incomplete',root/'incomplete.tar.gz')
            r=audit_bundle(root/'incomplete.tar.gz')['result']
            self.assertEqual(r['status'],'INCOMPLETE');self.assertEqual(r['distance_lower_bound'],1)
            calibrate(code(),root/'calibration',cutoff=2,samples=4)
            export_bundle(root/'calibration',root/'calibration.tar.gz')
            r=audit_bundle(root/'calibration.tar.gz')['result']
            self.assertIsNone(r['distance_claim'])

    def test_locked_linked_and_nested_export_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'run';certify(code(),run,cutoff=2)
            (run/'.running.lock').write_text('123')
            with self.assertRaisesRegex(ValueError,'locked'):
                export_bundle(run,root/'a.tar.gz')
            (run/'.running.lock').unlink()
            with self.assertRaisesRegex(ValueError,'outside'):
                export_bundle(run,run/'a.tar.gz')
            (run/'linked').symlink_to(run/'code.json')
            with self.assertRaisesRegex(ValueError,'symbolic link'):
                export_bundle(run,root/'a.tar.gz')

    def test_corruption_and_forged_summary_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);certify(code(),root/'run',cutoff=2)
            export_bundle(root/'run',root/'original.tar.gz')
            def corrupt(contents):contents['evidence/code.json']+=b'\n'
            rewrite_archive(root/'original.tar.gz',root/'corrupt.tar.gz',corrupt)
            with self.assertRaisesRegex(ValueError,'checksum'):
                audit_bundle(root/'corrupt.tar.gz')
            def false_result(contents):
                m=json.loads(contents['MANIFEST.json']);m['audited_result']['exact_distance']=99
                contents['MANIFEST.json']=json_bytes(m)
            rewrite_archive(root/'original.tar.gz',root/'false.tar.gz',false_result)
            with self.assertRaisesRegex(ValueError,'fresh audit'):
                audit_bundle(root/'false.tar.gz')

    def test_traversal_and_duplicate_members_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for names in (['../escape'],['evidence/x','evidence/x'],['/absolute'],['evidence/./x']):
                path=Path(tmp)/'bad.tar.gz'
                with tarfile.open(path,'w:gz') as archive:
                    for name in names:
                        info=tarfile.TarInfo(name);info.size=1;archive.addfile(info,io.BytesIO(b'x'))
                with self.assertRaisesRegex(ValueError,'Unsafe'):
                    audit_bundle(path)
            self.assertFalse((Path(tmp).parent/'escape').exists())


if __name__=='__main__':unittest.main()
