from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest

from cssdist.code import digest
from cssdist.engine import build,source_hashes


class BuildCacheTests(unittest.TestCase):
    def test_concurrent_builds_and_corrupt_cache_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cache=root/'cache'
            with ThreadPoolExecutor(max_workers=3) as pool:
                records=list(pool.map(lambda i:build(root/f'out{i}',cache=cache),range(3)))
            self.assertTrue(all(r['identity']==records[0]['identity'] for r in records))
            for i,record in enumerate(records):
                self.assertEqual(source_hashes(root/f'out{i}'),record['identity']['source_sha256'])
                self.assertEqual(digest((root/f'out{i}/exact').read_bytes()),record['executable_sha256'])
            entry=next(p for p in cache.iterdir() if p.is_dir())
            (entry/'build.json').write_text('{interrupted')
            restored=build(root/'restored',cache=cache)
            self.assertEqual(restored['identity'],records[0]['identity'])
            self.assertEqual(json.loads((entry/'build.json').read_text()),restored)


if __name__=='__main__':unittest.main()
