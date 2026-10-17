import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock,patch
from fastapi.testclient import TestClient
from clipora_v8_local_workflow.app import create_local_app
from clipora_v8_local_workflow.scheduler import Scheduler
from clipora_v8_web.owned_jobs import OwnedJobs

ORIGIN='http://127.0.0.1:8090'


class FakeScheduler:
    def __init__(self,store,artifacts):self.available=False
    async def start(self):self.available=True
    async def close(self):self.available=False


class LocalAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
    def test_only_sample_can_be_submitted_and_session_survives_refresh(self):
        app=create_local_app(ORIGIN,self.root,scheduler_factory=FakeScheduler)
        with TestClient(app,base_url=ORIGIN) as client:
            headers={'Origin':ORIGIN}
            self.assertTrue(client.get('/api/v8/ui/config').json()['offline_sample_enabled'])
            client.post('/api/v8/session',headers=headers);token=client.cookies['clipora_session']
            client.post('/api/v8/session',headers=headers)
            self.assertEqual(client.cookies['clipora_session'],token)
            sample_headers={**headers,'Idempotency-Key':'a'*32}
            response=client.post('/api/v8/samples',headers=sample_headers,json={})
            self.assertEqual(response.status_code,202,response.text)
            first=response.json()
            self.assertEqual(client.post('/api/v8/samples',headers=sample_headers,json={}).json(),first)
            self.assertEqual(client.post('/api/v8/samples',headers=sample_headers,json={'url':'https://youtu.be/abc'}).status_code,422)
            self.assertEqual(client.post('/api/v8/download',headers=headers,json={'url':'https://youtu.be/abc'}).status_code,503)
            self.assertEqual(app.state.owned_jobs.claim('runner')['job_id'],first['job_id'])
            self.assertEqual(app.state.owned_jobs.payload_for_runner(first['job_id'],'runner'),'clipora:offline-sample')
    def test_missing_owner_origin_and_nonlocal_configuration_denied(self):
        app=create_local_app(ORIGIN,self.root,scheduler_factory=FakeScheduler)
        with TestClient(app,base_url=ORIGIN) as client:
            self.assertEqual(client.post('/api/v8/samples',json={}).status_code,403)
            self.assertEqual(client.post('/api/v8/samples',headers={'Origin':ORIGIN,'Idempotency-Key':'a'*32},json={}).status_code,403)
        for origin in ('https://clipora.example','http://localhost:8090'):
            with self.assertRaises(ValueError):create_local_app(origin,self.root,scheduler_factory=FakeScheduler)


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.media=self.root/'media';self.media.mkdir()
        self.store=OwnedJobs(self.root/'state');self.token=self.store.issue_session()
        self.source=self.root/'sample.mp4';self.source.write_bytes(b'\0\0\0\x20ftypisom'+b'x'*4096)
    async def test_sample_publication_and_global_leader_lock(self):
        source=self.source
        class Resource:
            def __init__(self,*args):pass
            async def wait(self):return source
            async def stop(self):return True
        job=self.store.create_sample(self.token,'a'*32)
        scheduler=Scheduler(self.store,self.media,factory=Resource)
        second=Scheduler(self.store,self.media,factory=Resource)
        await scheduler.start()
        try:
            with self.assertRaises(BlockingIOError):await second.start()
            async with asyncio.timeout(3):
                while self.store.get(job['job_id'])['status'] not in ('completed','failed'):await asyncio.sleep(.02)
            self.assertEqual(self.store.get(job['job_id'])['status'],'completed')
            self.assertEqual((self.media/(job['job_id']+'.mp4')).read_bytes(),source.read_bytes())
        finally:await scheduler.close()
    async def test_public_url_never_dispatched(self):
        job=self.store.create_owned(self.token,'https://youtu.be/abc','a'*32)
        calls=[]
        def factory(*args):calls.append(args);raise AssertionError('Public URL dispatched')
        scheduler=Scheduler(self.store,self.media,factory=factory)
        await scheduler.start()
        try:
            async with asyncio.timeout(2):
                while self.store.get(job['job_id'])['status']!='failed':await asyncio.sleep(.02)
            self.assertEqual(calls,[])
        finally:await scheduler.close()
    async def test_restart_recovery_cleans_before_releasing_fence(self):
        job=self.store.create_sample(self.token,'a'*32);owner='f'*32;self.store.claim(owner)
        cleaned=[]
        async def cleanup(value):
            self.assertEqual(self.store.get(job['job_id'])['status'],'processing');cleaned.append(value)
        scheduler=Scheduler(self.store,self.media)
        with patch('clipora_v8_local_workflow.scheduler.cleanup',cleanup):await scheduler.start()
        try:
            self.assertEqual(cleaned,[owner]);self.assertEqual(self.store.get(job['job_id'])['status'],'failed')
        finally:await scheduler.close()
    async def test_failed_recovery_does_not_release_processing_record(self):
        job=self.store.create_sample(self.token,'a'*32);self.store.claim('f'*32)
        scheduler=Scheduler(self.store,self.media)
        with patch('clipora_v8_local_workflow.scheduler.cleanup',AsyncMock(side_effect=RuntimeError('Unavailable'))):
            with self.assertRaises(RuntimeError):await scheduler.start()
        self.assertEqual(self.store.get(job['job_id'])['status'],'processing')
        self.assertIsNone(scheduler.fd)
