import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from staging_store import publish_artifact


class StagingBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.mp4'; self.source.write_bytes(b'x' * 200)
        self.staging = self.root / 'staging'

    def tearDown(self): self.temp.cleanup()

    def test_publish_complete_file(self):
        publish_artifact(self.source, self.staging, 'a'*10, limit=200)
        self.assertEqual((self.staging / ('a'*10+'.mp4')).read_bytes(), b'x'*200)
        self.assertFalse(list(self.staging.glob('*.part')))

    def test_budget_counts_existing_files(self):
        publish_artifact(self.source, self.staging, 'a'*10, limit=300)
        with self.assertRaises(ValueError):
            publish_artifact(self.source, self.staging, 'b'*10, limit=300)
        self.assertEqual(len(list(self.staging.glob('*.mp4'))), 1)

    def test_file_count_limit(self):
        publish_artifact(self.source, self.staging, 'a'*10, max_files=1)
        with self.assertRaises(ValueError):
            publish_artifact(self.source, self.staging, 'b'*10, max_files=1)

    def test_existing_target_never_overwritten(self):
        publish_artifact(self.source, self.staging, 'a'*10)
        self.source.write_bytes(b'y'*200)
        with self.assertRaises(FileExistsError):
            publish_artifact(self.source, self.staging, 'a'*10)
        self.assertEqual((self.staging/('a'*10+'.mp4')).read_bytes(), b'x'*200)
        self.assertFalse(list(self.staging.glob('*.part')))

    def test_source_symlink_rejected(self):
        link=self.root/'link.mp4';link.symlink_to(self.source)
        with self.assertRaises(OSError):publish_artifact(link,self.staging,'a'*10)

    def test_staging_symlink_rejected(self):
        self.staging.mkdir();link=self.root/'link';link.symlink_to(self.staging)
        with self.assertRaises(ValueError):publish_artifact(self.source,link,'a'*10)

    def test_existing_non_regular_entry_rejected(self):
        self.staging.mkdir();(self.staging/'link').symlink_to(self.source)
        with self.assertRaises(ValueError):publish_artifact(self.source,self.staging,'a'*10)
        self.assertEqual(self.source.stat().st_size,200)

    def test_concurrent_processes_cannot_exceed_budget(self):
        script = ('import sys;sys.path.insert(0,sys.argv[1]);'
                  'from staging_store import publish_artifact;'
                  'publish_artifact(sys.argv[2],sys.argv[3],sys.argv[4],limit=300)')
        jobs=[subprocess.Popen([sys.executable,'-B','-c',script,str(Path(__file__).parent),str(self.source),str(self.staging),c*10],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for c in ('a','b')]
        outcomes=[p.communicate(timeout=10) for p in jobs]
        self.assertEqual(sorted(p.returncode for p in jobs),[0,1])
        self.assertEqual(sum(p.stat().st_size for p in self.staging.glob('*.mp4')),200)
        self.assertFalse(list(self.staging.glob('*.part')))


if __name__=='__main__':unittest.main()
