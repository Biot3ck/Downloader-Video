from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import multiprocessing
import unittest
from clipora_v8_web.owned_jobs import OwnedJobs,OwnerRequired,IdempotencyConflict,QueueFull


def submit_process(directory,token,barrier,results):
    try:
        store=OwnedJobs(directory,clock=lambda:100)
        barrier.wait(timeout=10)
        store.create_owned(token,'https://youtu.be/abc','d'*32)
        results.put('accepted')
    except QueueFull:results.put('limited')
    except BaseException as exc:results.put(type(exc).__name__)


class OwnedJobTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='clipora-owned-jobs-');self.addCleanup(self.temp.cleanup)
        self.state=Path(self.temp.name).resolve()
        self.now=100.0
        self.store=OwnedJobs(self.state,clock=lambda:self.now)
        self.a=self.store.issue_session();self.b=self.store.issue_session()
    def create(self,owner=None,key='a'*32,url='https://youtu.be/abc'):
        return self.store.create_owned(owner or self.a,url,key)
    def test_foreign_and_missing_job_are_indistinguishable(self):
        job=self.create()
        for token in (self.b,'f'*64,'invalid'):
            self.assertIsNone(self.store.get_owned(token,job['job_id']))
            self.assertFalse(self.store.cancel_owned(token,job['job_id']))
        self.assertEqual(set(job),{'job_id','status','created_at','updated_at','cancel_requested'})
        self.assertTrue(self.store.get_owned(self.a,job['job_id']))
    def test_restart_keeps_session_and_queue_without_raw_token(self):
        job=self.create()
        restarted=OwnedJobs(self.state,clock=lambda:self.now)
        self.assertEqual(restarted.get_owned(self.a,job['job_id']),job)
        with restarted.connection() as db:
            dump='\n'.join(db.iterdump())
            self.assertNotIn(self.a,dump);self.assertNotIn(self.b,dump)
    def test_idempotency_and_conflicting_body(self):
        first=self.create()
        self.assertEqual(self.create(),first)
        with self.assertRaises(IdempotencyConflict):self.create(url='https://youtu.be/different')
        self.assertNotEqual(self.create(owner=self.b)['job_id'],first['job_id'])
    def test_one_active_job_per_owner(self):
        self.create()
        with self.assertRaises(QueueFull):self.create(key='b'*32)
    def test_atomic_global_capacity_across_store_instances(self):
        owners=[self.store.issue_session() for _ in range(8)]
        def submit(token):
            try:OwnedJobs(self.state,clock=lambda:100).create_owned(token,'https://youtu.be/abc','b'*32);return True
            except QueueFull:return False
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(submit,owners))
        self.assertEqual(sum(results),4)
    def test_execution_fence_is_distinct_from_browser_ownership(self):
        job=self.create();claimed=self.store.claim('runner-a')
        self.assertEqual(job['job_id'],claimed['job_id'])
        self.assertIsNone(self.store.payload_for_runner(job['job_id'],self.a))
        self.assertIsNone(self.store.payload_for_runner(job['job_id'],'runner-b'))
        self.assertEqual(self.store.payload_for_runner(job['job_id'],'runner-a'),'https://youtu.be/abc')
        self.assertFalse(self.store.finish(job['job_id'],'runner-b',True,'Unsafe message'))
        self.assertTrue(self.store.finish(job['job_id'],'runner-a',True,'/private/path?secret=abc'))
        self.assertNotIn('secret',str(self.store.get_owned(self.a,job['job_id'])))
    def test_expiry_denies_owner_and_runner_payload(self):
        job=self.create();self.store.claim('runner')
        self.now+=3601
        self.assertIsNone(self.store.get_owned(self.a,job['job_id']))
        self.assertIsNone(self.store.payload_for_runner(job['job_id'],'runner'))
        self.store.issue_session()
        self.assertEqual(self.store.get(job['job_id'])['status'],'processing')
    def test_expired_queued_jobs_pruned_and_capacity_reclaimed(self):
        old=self.create();self.now+=3601;self.store.issue_session()
        self.assertIsNone(self.store.get(old['job_id']))
        self.assertTrue(self.create(key='b'*32))
    def test_session_limit_and_expiry(self):
        other=OwnedJobs(self.state/'bounded',clock=lambda:self.now,max_sessions=1)
        token=other.issue_session()
        with self.assertRaises(QueueFull):other.issue_session()
        self.now+=86401
        with self.assertRaises(OwnerRequired):other.create_owned(token,'https://youtu.be/abc','c'*32)
        self.assertTrue(other.issue_session())
    def test_symlink_and_ownerless_creation_rejected(self):
        link=self.state/'link';link.symlink_to(self.state,target_is_directory=True)
        with self.assertRaises(ValueError):OwnedJobs(link/'child')
        with self.assertRaises(OwnerRequired):self.store.create()
    def test_queued_cancellation_and_retention_delete(self):
        job=self.create()
        self.assertTrue(self.store.cancel_owned(self.a,job['job_id']))
        self.assertEqual(self.store.get_owned(self.a,job['job_id'])['status'],'failed')
        self.store.delete_expired(job['job_id'],self.now+1)
        self.assertIsNone(self.store.get_owned(self.a,job['job_id']))

    def test_global_admission_across_processes(self):
        owners=[self.store.issue_session() for _ in range(6)]
        context=multiprocessing.get_context('spawn')
        barrier=context.Barrier(6);results=context.Queue()
        children=[context.Process(target=submit_process,args=(str(self.state),token,barrier,results)) for token in owners]
        try:
            for child in children:child.start()
            outcome=[results.get(timeout=15) for _ in children]
            for child in children:child.join(timeout=5)
            self.assertEqual(outcome.count('accepted'),4,outcome)
            self.assertEqual(outcome.count('limited'),2,outcome)
            self.assertTrue(all(child.exitcode==0 for child in children))
        finally:
            for child in children:
                if child.is_alive():child.terminate();child.join()
            results.close();results.join_thread()
