from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from clipora_v8_web.owned_api import create_owned_app

ORIGIN='http://127.0.0.1:8090'


class OwnedAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.artifacts=self.root/'media'
        self.app=create_owned_app(ORIGIN,self.root/'state',self.artifacts)
        self.a=TestClient(self.app,base_url=ORIGIN);self.b=TestClient(self.app,base_url=ORIGIN)
        for client in (self.a,self.b):
            self.assertEqual(client.post('/api/v8/session',headers={'Origin':ORIGIN}).status_code,204)
        self.store=self.app.state.owned_jobs
        self.job=self.store.create_owned(self.a.cookies['clipora_session'],'https://youtu.be/abc','a'*32)
        self.job_id=self.job['job_id'];self.path='/api/v8/jobs/'+self.job_id
    def test_owner_only_status_and_cancellation(self):
        self.assertEqual(self.a.get(self.path).status_code,200)
        self.assertEqual(self.b.get(self.path).json(),self.b.get('/api/v8/jobs/'+'f'*32).json())
        self.assertEqual(self.b.post(self.path+'/cancel',headers={'Origin':ORIGIN}).status_code,404)
        self.assertEqual(self.a.post(self.path+'/cancel',headers={'Origin':ORIGIN}).status_code,204)
    def test_fresh_state_root_created_private_before_nested_artifacts(self):
        state=self.root/'fresh'
        app=create_owned_app(ORIGIN,state,state/'artifacts')
        for path in (state,state/'owned-public',state/'artifacts'):
            self.assertEqual(path.stat().st_mode & 0o777,0o700)
        client=TestClient(app,base_url=ORIGIN)
        self.assertEqual(client.post('/api/v8/session',headers={'Origin':ORIGIN}).status_code,204)
    def test_file_authorization_precedes_filesystem_access(self):
        with patch('clipora_v8_web.owned_api.PinnedVideoResponse',side_effect=AssertionError('Foreign owner touched filesystem')):
            self.assertEqual(self.b.get(self.path+'/file').status_code,404)
        self.assertEqual(self.a.get(self.path+'/file').status_code,404)
    def test_owned_range_and_head(self):
        self.store.claim('runner');self.store.finish(self.job_id,'runner',True,'private-worker-detail')
        data=b'\0\0\0\x20ftypisom'+b'x'*4096
        (self.artifacts/(self.job_id+'.mp4')).write_bytes(data)
        response=self.a.get(self.path+'/file',headers={'Range':'bytes=0-15'})
        self.assertEqual(response.status_code,206);self.assertEqual(response.content,data[:16])
        self.assertIn('clipora-video.mp4',response.headers['content-disposition'])
        self.assertEqual(self.a.head(self.path+'/file').content,b'')
        self.assertEqual(self.b.get(self.path+'/file').status_code,404)
        self.assertNotIn('private-worker-detail',self.a.get(self.path).text)
    def test_production_cookie_flags_and_default_download_gate(self):
        secure=create_owned_app('https://clipora.example',self.root/'secure-state',self.root/'secure-media')
        client=TestClient(secure,base_url='https://clipora.example')
        response=client.post('/api/v8/session',headers={'Origin':'https://clipora.example'})
        cookie=response.headers['set-cookie']
        for flag in ('__Host-clipora-session=','HttpOnly','Secure','SameSite=strict','Path=/'):self.assertIn(flag,cookie)
        self.assertNotIn('Domain=',cookie)
        self.assertEqual(client.post('/api/v8/download',headers={'Origin':'https://clipora.example'}).status_code,503)
        self.assertEqual(response.content,b'')
    def test_duplicate_and_missing_cookies_rejected(self):
        token=self.a.cookies['clipora_session']
        client=TestClient(self.app,base_url=ORIGIN)
        self.assertEqual(client.get(self.path).status_code,404)
        self.assertEqual(client.get(self.path,headers={'Cookie':'clipora_session='+token+'; clipora_session='+token}).status_code,404)
    def test_foreign_origin_and_expired_session(self):
        self.assertEqual(self.a.post('/api/v8/session',headers={'Origin':'https://evil.example'}).status_code,403)
        with self.store.connection() as db:db.execute('UPDATE browser_sessions SET expires_at=0')
        self.assertEqual(self.a.get(self.path).status_code,404)

    def test_new_session_sweeps_expired_completed_file(self):
        self.store.claim('runner');self.store.finish(self.job_id,'runner',True,'Ready')
        path=self.artifacts/(self.job_id+'.mp4')
        path.write_bytes(b'\0\0\0\x20ftypisom'+b'x'*4096)
        with self.store.connection() as db:db.execute('UPDATE job_ownership SET expires_at=0')
        self.assertEqual(self.a.get(self.path+'/file').status_code,404)
        self.assertEqual(self.b.post('/api/v8/session',headers={'Origin':ORIGIN}).status_code,204)
        self.assertFalse(path.exists())

    def test_running_cancel_requests_stop_without_freeing_slot_or_file(self):
        self.store.claim('runner')
        self.assertEqual(self.b.post(self.path+'/cancel',headers={'Origin':ORIGIN}).status_code,404)
        self.assertFalse(self.store.get_owned(self.a.cookies['clipora_session'],self.job_id)['cancel_requested'])
        self.assertEqual(self.a.post(self.path+'/cancel',headers={'Origin':ORIGIN}).status_code,204)
        status=self.a.get(self.path).json()
        self.assertEqual(status['status'],'processing');self.assertTrue(status['cancel_requested'])
        self.assertFalse(self.store.finish(self.job_id,'runner',True,'Late publish'))
        self.assertEqual(self.a.get(self.path+'/file').status_code,404)
        self.assertTrue(self.store.confirm_stopped(self.job_id,'runner'))
        self.assertEqual(self.a.get(self.path).json()['status'],'failed')
