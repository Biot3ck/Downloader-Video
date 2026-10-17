"""API contract regression with isolated durable state; no Docker/network required."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from clipora_v8_browser_real_mp4 import routes
from clipora_v8_browser_real_mp4.job_store import JobStore


class BrowserContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.staging = Path(self.tmp.name) / 'staging'; self.staging.mkdir()
        self.database = JobStore(Path(self.tmp.name) / 'state')
        self.patches = [patch.object(routes,'STAGING',self.staging),patch.object(routes,'STORE',self.database),patch.object(routes,'cleanup_job')]
        for item in self.patches:item.start()
        app=FastAPI();app.include_router(routes.router)
        self.client=TestClient(app)
        self.row=self.database.create();self.job=self.row['job_id'];self.tag=self.row['tag']

    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.tmp.cleanup()

    def artifact(self):
        (self.staging/(self.tag+'.mp4')).write_bytes(b'\x00\x00\x00\x20ftypisom'+b'x'*1024)

    def output(self,verified=True):
        return ('CLIPORA_BROWSER_MP4_READY='+self.tag+'\n'+('CLIPORA_BROWSER_TLS_VERIFIED=1\n' if verified else '')+'V8 SECURE EGRESS REAL WORKER E2E PASSED (OFFLINE ONLY)\n')

    def run_execute(self,verified=True,failure=False):
        row=self.database.claim('test-owner')
        with (self.database.directory/'runner.lock').open('a+') as lease:
            with patch.object(routes.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['runner']) if failure else None,
                              return_value=subprocess.CompletedProcess([],0,self.output(verified),'')) as run:
                routes.execute(row,'test-owner',lease.fileno())
        return run

    def test_verified_completion_delivery_and_range(self):
        self.artifact();run=self.run_execute()
        self.assertEqual(Path(run.call_args.args[0][-1]).name,'run_browser_verified.py')
        state=self.client.get('/api/v8/real-offline/jobs/'+self.job).json()
        self.assertEqual(state['status'],'completed')
        response=self.client.get(state['download_url']);self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['content-type'],'video/mp4')
        partial=self.client.get(state['download_url'],headers={'Range':'bytes=0-15'})
        self.assertEqual(partial.status_code,206);self.assertEqual(len(partial.content),16)

    def test_legacy_marker_fails_closed(self):
        self.artifact();self.run_execute(verified=False)
        self.assertEqual(self.database.get(self.job)['status'],'failed')
        self.assertEqual(self.client.get('/api/v8/real-offline/files/'+self.job).status_code,404)

    def test_runner_failure_has_no_insecure_retry(self):
        run=self.run_execute(failure=True)
        self.assertEqual(run.call_count,1)
        self.assertEqual(self.database.get(self.job)['status'],'failed')

    def complete(self):
        row=self.database.claim('test-owner')
        self.database.finish(row['job_id'],'test-owner',True,'ready')

    def test_expired_and_symlink_outputs_are_not_served(self):
        outside=self.staging/'other.mp4';outside.write_bytes(b'x'*512)
        (self.staging/(self.tag+'.mp4')).symlink_to(outside)
        self.complete()
        self.assertEqual(self.client.get('/api/v8/real-offline/files/'+self.job).status_code,404)
        with self.database.connection() as db:
            db.execute('UPDATE jobs SET updated_at=? WHERE job_id=?',(time.time()-routes.TTL-1,self.job))
        self.assertEqual(self.client.get('/api/v8/real-offline/jobs/'+self.job).status_code,404)
        self.assertTrue(outside.is_file())

    def test_staging_count_limit_returns_507_before_work(self):
        for i in range(routes.MAX_STAGED_FILES):(self.staging/f'{i:010x}.mp4').write_bytes(b'x'*128)
        with patch.dict(os.environ,{'CLIPORA_V8_OFFLINE_BROWSER_TEST':'1'}):
            self.assertEqual(self.client.post('/api/v8/real-offline/jobs').status_code,507)
        self.assertEqual(len(self.database.list()),1)

    def test_full_staging_byte_budget_returns_507(self):
        with (self.staging/'1234567890.mp4').open('wb') as stream:stream.truncate(routes.MAX_SIZE)
        with patch.dict(os.environ,{'CLIPORA_V8_OFFLINE_BROWSER_TEST':'1'}):
            self.assertEqual(self.client.post('/api/v8/real-offline/jobs').status_code,507)

    def test_feature_stays_disabled_without_flag(self):
        with patch.dict(os.environ,{'CLIPORA_V8_OFFLINE_BROWSER_TEST':''}):
            self.assertEqual(self.client.post('/api/v8/real-offline/jobs').status_code,503)

    def test_shared_queue_limit_returns_429(self):
        with patch.dict(os.environ,{'CLIPORA_V8_OFFLINE_BROWSER_TEST':'1'}):
            for _ in range(3):self.assertEqual(self.client.post('/api/v8/real-offline/jobs').status_code,202)
            self.assertEqual(self.client.post('/api/v8/real-offline/jobs').status_code,429)

    def test_completed_status_survives_store_reopen(self):
        self.artifact();self.run_execute()
        reopened=JobStore(self.database.directory)
        with patch.object(routes,'STORE',reopened):
            response=self.client.get('/api/v8/real-offline/jobs/'+self.job)
            self.assertEqual(response.json()['status'],'completed')


if __name__=='__main__':unittest.main()
