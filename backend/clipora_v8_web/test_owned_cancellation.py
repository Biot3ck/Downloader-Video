import asyncio
from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from clipora_v8_web.owned_jobs import OwnedJobs,QueueFull
from clipora_v8_web.owned_publish import publish,PublicationDenied
from clipora_v8_web.owned_runner import observe


class CancellationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.media=self.root/'media';self.media.mkdir()
        self.store=OwnedJobs(self.root/'state');self.token=self.store.issue_session()
        self.job=self.store.create_owned(self.token,'https://youtu.be/abc','a'*32)
        self.id=self.job['job_id'];self.store.claim('runner')
        self.source=self.root/'source.mp4';self.source.write_bytes(b'\0\0\0\x20ftypisom'+b'x'*4096)
    async def test_cancel_is_durable_and_blocks_all_late_finish(self):
        self.assertTrue(self.store.cancel_owned(self.token,self.id))
        restarted=OwnedJobs(self.root/'state')
        self.assertTrue(restarted.get_owned(self.token,self.id)['cancel_requested'])
        self.assertEqual(restarted.get(self.id)['status'],'processing')
        self.assertFalse(restarted.finish(self.id,'runner',True,'Late success'))
        self.assertFalse(restarted.finish(self.id,'runner',False,'Premature failure'))
        with self.assertRaises(QueueFull):restarted.create_owned(self.token,'https://youtu.be/abc','b'*32)
        self.assertFalse(restarted.confirm_stopped(self.id,'wrong-runner'))
        self.assertTrue(restarted.confirm_stopped(self.id,'runner'))
        self.assertEqual(restarted.get(self.id)['status'],'failed')
    async def test_publish_copies_and_exposes_only_completed_inode(self):
        path=publish(self.store,self.id,'runner',self.source,self.media)
        self.assertEqual(path.read_bytes(),self.source.read_bytes())
        self.assertEqual(self.store.get(self.id)['status'],'completed')
        self.assertEqual(list(self.media.iterdir()),[path])
    async def test_cancellation_between_copy_and_commit_prevents_publication(self):
        original=self.store.transaction
        @contextmanager
        def cancelled_transaction():
            with original() as db:
                db.execute('INSERT INTO job_cancellation VALUES(?,?)',(self.id,self.store.clock()))
            with original() as db:yield db
        with patch.object(self.store,'transaction',cancelled_transaction):
            with self.assertRaises(PublicationDenied):publish(self.store,self.id,'runner',self.source,self.media)
        self.assertEqual(list(self.media.iterdir()),[])
        self.assertEqual(self.store.get(self.id)['status'],'processing')
    async def test_database_commit_failure_removes_only_our_link(self):
        original=self.store.transaction
        @contextmanager
        def fail_commit():
            with original() as db:
                yield db
                raise OSError('Simulated commit failure')
        with patch.object(self.store,'transaction',fail_commit):
            with self.assertRaises(OSError):publish(self.store,self.id,'runner',self.source,self.media)
        self.assertEqual(list(self.media.iterdir()),[])
        self.assertEqual(self.store.get(self.id)['status'],'processing')
    async def test_existing_target_never_overwritten(self):
        target=self.media/(self.id+'.mp4');target.write_bytes(b'original')
        with self.assertRaises(FileExistsError):publish(self.store,self.id,'runner',self.source,self.media)
        self.assertEqual(target.read_bytes(),b'original')
        self.assertEqual(list(self.media.iterdir()),[target])
    async def test_real_process_stopped_before_cancel_acknowledged(self):
        process=await asyncio.create_subprocess_exec(sys.executable,'-B','-c','import time;time.sleep(30)')
        source=self.source
        class Handle:
            async def wait(self):await process.wait();return source
            async def stop(self):
                if process.returncode is None:
                    process.terminate()
                    await asyncio.wait_for(process.wait(),2)
                return True
        task=asyncio.create_task(observe(self.store,self.id,'runner',Handle(),self.media,poll=.01))
        try:
            self.store.cancel_owned(self.token,self.id)
            self.assertFalse(await asyncio.wait_for(task,3))
            self.assertIsNotNone(process.returncode)
            self.assertEqual(self.store.get(self.id)['status'],'failed')
            self.assertEqual(list(self.media.iterdir()),[])
        finally:
            if process.returncode is None:process.kill();await process.wait()
            if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
    async def test_failed_stop_keeps_execution_fence_and_capacity(self):
        class Handle:
            async def wait(self):await asyncio.Event().wait()
            async def stop(self):return False
        self.store.cancel_owned(self.token,self.id)
        with self.assertRaisesRegex(RuntimeError,'cleanup requires recovery'):
            await observe(self.store,self.id,'runner',Handle(),self.media,poll=.01)
        self.assertEqual(self.store.get(self.id)['status'],'processing')
        self.assertEqual(self.store.get(self.id)['owner'],'runner')
    async def test_repeated_cancel_waits_for_stop_confirmation(self):
        entered=asyncio.Event();release=asyncio.Event();confirmed=asyncio.Event()
        class Handle:
            async def wait(self):await asyncio.Event().wait()
            async def stop(self):
                entered.set();await release.wait();confirmed.set();return True
        task=asyncio.create_task(observe(self.store,self.id,'runner',Handle(),self.media,poll=.01))
        try:
            await asyncio.sleep(0);task.cancel();await asyncio.wait_for(entered.wait(),1)
            for _ in range(3):task.cancel();await asyncio.sleep(0)
            self.assertEqual(self.store.get(self.id)['status'],'processing')
            release.set()
            with self.assertRaises(asyncio.CancelledError):await task
            self.assertTrue(confirmed.is_set())
            self.assertEqual(self.store.get(self.id)['status'],'failed')
        finally:
            release.set()
            if not task.done():task.cancel()
            await asyncio.gather(task,return_exceptions=True)

    async def test_successful_real_process_stopped_before_publish(self):
        process=await asyncio.create_subprocess_exec(sys.executable,'-B','-c','pass')
        source=self.source;stopped=asyncio.Event()
        class Handle:
            async def wait(self):
                self_result=await process.wait()
                if self_result:raise RuntimeError('Fixture failed')
                return source
            async def stop(self):
                assert process.returncode is not None
                stopped.set();return True
        self.assertTrue(await observe(self.store,self.id,'runner',Handle(),self.media,poll=.01))
        self.assertTrue(stopped.is_set())
        self.assertEqual(self.store.get(self.id)['status'],'completed')
        self.assertEqual((self.media/(self.id+'.mp4')).read_bytes(),source.read_bytes())

    async def test_stale_execution_owner_cannot_publish(self):
        with self.assertRaises(PublicationDenied):publish(self.store,self.id,'stale',self.source,self.media)
        self.assertEqual(list(self.media.iterdir()),[])

    async def test_disk_full_during_copy_never_exposes_artifact(self):
        import errno
        with patch('clipora_v8_web.owned_publish.os.write',side_effect=OSError(errno.ENOSPC,'Disk full')):
            with self.assertRaises(OSError):publish(self.store,self.id,'runner',self.source,self.media)
        self.assertEqual(list(self.media.iterdir()),[])
        self.assertEqual(self.store.get(self.id)['status'],'processing')

    async def test_job_deadline_stops_handle_and_prevents_publication(self):
        stopped=asyncio.Event()
        class Handle:
            async def wait(self):await asyncio.Event().wait()
            async def stop(self):stopped.set();return True
        self.assertFalse(await observe(self.store,self.id,'runner',Handle(),self.media,poll=.01,timeout=.02))
        self.assertTrue(stopped.is_set())
        self.assertEqual(self.store.get(self.id)['status'],'failed')
        self.assertEqual(list(self.media.iterdir()),[])

    async def test_unfenced_legacy_interruption_cannot_release_running_job(self):
        with self.assertRaisesRegex(RuntimeError,'fenced stop confirmation'):
            self.store.interrupted(self.id)
        self.assertEqual(self.store.get(self.id)['status'],'processing')
        self.assertEqual(self.store.get(self.id)['owner'],'runner')
