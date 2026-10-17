from pathlib import Path
import tempfile
import unittest
from clipora_v8_browser_real_mp4.artifact_delivery import PinnedVideoResponse
from clipora_v8_web.owned_jobs import OwnedJobs
from clipora_v8_web.owned_artifacts import sweep


class OwnedArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.media=self.root/'media';self.media.mkdir()
        self.now=100
        self.store=OwnedJobs(self.root/'state',clock=lambda:self.now)
        self.owner=self.store.issue_session()
        self.job=self.store.create_owned(self.owner,'https://youtu.be/abc','a'*32)
        self.path=self.media/(self.job['job_id']+'.mp4')
        self.path.write_bytes(b'\0\0\0\x20ftypisom'+b'x'*1024)
    def test_processing_artifact_retained_until_runner_finishes(self):
        self.store.claim('runner');self.now+=3601
        self.assertEqual(sweep(self.store,self.media),0)
        self.store.finish(self.job['job_id'],'runner',False,'Stopped')
        self.assertEqual(sweep(self.store,self.media),1)
    def test_expired_download_retained_while_stream_is_pinned(self):
        self.store.claim('runner');self.store.finish(self.job['job_id'],'runner',True,'Ready')
        self.assertEqual(sweep(self.store,self.media),0)
        response=PinnedVideoResponse(self.path,1024*1024)
        try:
            self.now+=3601
            self.assertEqual(sweep(self.store,self.media),0)
        finally:response.close()
        self.assertEqual(sweep(self.store,self.media),1)
    def test_orphan_and_unknown_names(self):
        orphan=self.media/('f'*32+'.mp4');orphan.write_bytes(b'x')
        other=self.media/'keep.txt';other.write_bytes(b'x')
        self.path.unlink()
        self.assertEqual(sweep(self.store,self.media),1)
        self.assertTrue(other.exists())
    def test_symlink_file_and_directory_rejected(self):
        outside=self.root/'outside.mp4';outside.write_bytes(b'x')
        self.path.unlink();self.path.symlink_to(outside)
        self.assertEqual(sweep(self.store,self.media),0)
        self.assertTrue(outside.exists())
        link=self.root/'link';link.symlink_to(self.media,target_is_directory=True)
        with self.assertRaises(ValueError):sweep(self.store,link)

    def test_private_publication_temp_is_removed_only_when_unlocked(self):
        import fcntl,os
        path=self.media/('.'+self.job['job_id']+'.'+'a'*32+'.tmp')
        path.write_bytes(b'partial')
        fd=os.open(path,os.O_RDONLY)
        try:
            fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
            self.path.unlink()
            self.assertEqual(sweep(self.store,self.media),0)
        finally:os.close(fd)
        self.assertEqual(sweep(self.store,self.media),1)
