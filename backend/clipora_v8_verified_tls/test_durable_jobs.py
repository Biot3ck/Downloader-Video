import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BACKEND=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(BACKEND))
from clipora_v8_browser_real_mp4.job_store import JobStore,QueueFull
from clipora_v8_browser_real_mp4 import routes


class DurableQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name)/'state'
        self.db=JobStore(self.directory)
    def tearDown(self):self.temp.cleanup()

    def test_restart_retains_queue_and_completed_result(self):
        first=self.db.create();second=self.db.create()
        claimed=self.db.claim('owner');self.assertEqual(claimed['job_id'],first['job_id'])
        self.assertTrue(self.db.finish(first['job_id'],'owner',True,'ready'))
        reopened=JobStore(self.directory)
        self.assertEqual(reopened.get(first['job_id'])['status'],'completed')
        self.assertEqual(reopened.claim('new-owner')['job_id'],second['job_id'])

    def test_stale_owner_cannot_finish_and_only_one_claim(self):
        first=self.db.create();self.db.create()
        self.db.claim('owner')
        self.assertIsNone(self.db.claim('second-owner'))
        self.assertFalse(self.db.finish(first['job_id'],'stale',True,'wrong'))
        self.assertEqual(self.db.get(first['job_id'])['status'],'processing')

    def test_retained_record_limit(self):
        db=JobStore(self.directory,max_records=1)
        row=db.create();db.claim('owner');db.finish(row['job_id'],'owner',False,'failed')
        with self.assertRaises(QueueFull):db.create()

    def test_two_processes_admission_is_atomic(self):
        script='''import sys
sys.path.insert(0,sys.argv[1])
from clipora_v8_browser_real_mp4.job_store import JobStore,QueueFull
try: JobStore(sys.argv[2],max_pending=1).create()
except QueueFull: raise SystemExit(2)
'''
        processes=[subprocess.Popen([sys.executable,'-B','-c',script,str(BACKEND),str(self.directory)],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        results=[p.communicate(timeout=10) for p in processes]
        self.assertEqual(sorted(p.returncode for p in processes),[0,2],results)
        self.assertEqual(len(self.db.list()),1)

    def test_child_inherits_global_lock_after_parent_descriptor_closes(self):
        path=self.directory/'runner.lock'
        fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        child=subprocess.Popen([sys.executable,'-B','-c','import sys;print("ready",flush=True);sys.stdin.read()'],pass_fds=(fd,),stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        contender=None
        try:
            self.assertEqual(child.stdout.readline().strip(),'ready')
            os.close(fd);fd=None
            contender=os.open(path,os.O_RDWR)
            with self.assertRaises(BlockingIOError):fcntl.flock(contender,fcntl.LOCK_EX|fcntl.LOCK_NB)
            child.stdin.close();child.wait(timeout=5)
            fcntl.flock(contender,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:
            if fd is not None:os.close(fd)
            if contender is not None:os.close(contender)
            if child.poll() is None:child.kill();child.wait()
            if child.stdout:child.stdout.close()

    def test_dispatch_recovery_before_next_claim(self):
        first=self.db.create();second=self.db.create();self.db.claim('dead-owner')
        calls=[]
        def execute(job,owner,fd):
            calls.append(('execute',job['job_id']))
            self.db.finish(job['job_id'],owner,True,'ready')
        with patch.object(routes,'STORE',self.db),patch.object(routes,'STAGING',Path(self.temp.name)/'staging'),patch.object(routes,'cleanup_job',side_effect=lambda key:calls.append(('cleanup',key))),patch.object(routes,'execute',side_effect=execute):
            self.assertTrue(routes.dispatch_once())
        self.assertEqual(calls,[('cleanup',first['job_id']),('execute',second['job_id'])])
        self.assertEqual(self.db.get(first['job_id'])['status'],'failed')

    def test_failed_recovery_prevents_replacement_worker(self):
        first=self.db.create();self.db.create();self.db.claim('dead-owner')
        with patch.object(routes,'STORE',self.db),patch.object(routes,'cleanup_job',side_effect=RuntimeError('daemon unavailable')),patch.object(routes,'execute') as execute:
            with self.assertRaises(RuntimeError):routes.dispatch_once()
            execute.assert_not_called()
        self.assertEqual(self.db.get(first['job_id'])['status'],'processing')

    def test_busy_global_lock_prevents_recovery_or_claim(self):
        self.db.create()
        with (self.directory/'runner.lock').open('a+') as lease:
            fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with patch.object(routes,'STORE',self.db),patch.object(routes,'execute') as execute:
                self.assertFalse(routes.dispatch_once());execute.assert_not_called()
        self.assertEqual(self.db.list()[0]['status'],'queued')


if __name__=='__main__':unittest.main()
