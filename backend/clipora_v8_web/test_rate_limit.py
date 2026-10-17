import concurrent.futures
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from fastapi.testclient import TestClient
from clipora_v8_web.main import create_app
from clipora_v8_web.rate_limit import Limiter, LimitReached


class RateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='clipora-rate-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def test_shared_instances_and_window_expiry(self):
        a,b=Limiter(self.root,2,3),Limiter(self.root,2,3)
        a.admit('client',100);b.admit('client',100)
        with self.assertRaises(LimitReached):a.admit('client',100)
        b.admit('other',100)
        with self.assertRaises(LimitReached):a.admit('third',100)
        a.admit('client',121)
        with a.connection() as db:
            self.assertLessEqual(db.execute('SELECT count(*) FROM windows').fetchone()[0],2)
    def test_real_parallel_processes(self):
        Limiter(self.root,3,3).initialize()
        script="""import sys
from clipora_v8_web.rate_limit import Limiter,LimitReached
try:Limiter(sys.argv[1],3,3).admit('shared-client',100);print('accepted')
except LimitReached:print('limited')
"""
        def submit(_):
            r=subprocess.run([sys.executable,'-B','-c',script,str(self.root)],cwd=Path(__file__).resolve().parent.parent,
                             capture_output=True,text=True,timeout=10,check=True)
            return r.stdout.strip()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(submit,range(8)))
        self.assertEqual(results.count('accepted'),3)
        self.assertEqual(results.count('limited'),5)
    def test_stores_no_plaintext_client(self):
        limiter=Limiter(self.root)
        limiter.admit('192.0.2.123',100)
        self.assertNotIn(b'192.0.2.123',limiter.path.read_bytes())
        self.assertEqual(limiter.path.stat().st_mode & 0o777,0o600)
        self.assertLessEqual(limiter.path.stat().st_size,1024*1024)
    def test_symlink_rejected(self):
        target=self.root/'target';target.write_text('keep')
        (self.root/'admission.sqlite3').symlink_to(target)
        with self.assertRaises(OSError):Limiter(self.root).admit('client')
        self.assertEqual(target.read_text(),'keep')
    def test_http_limits_ignore_forged_forwarding_headers(self):
        client=TestClient(create_app('https://testserver',self.root),base_url='https://testserver')
        for n in range(20):
            response=client.post('/api/v8/validate',json={'url':'https://youtu.be/a'},
                                 headers={'Origin':'https://testserver','X-Forwarded-For':f'192.0.2.{n}'})
            self.assertEqual(response.status_code,200)
        response=client.post('/api/v8/validate',json={'url':'https://youtu.be/a'},headers={'Origin':'https://testserver'})
        self.assertEqual(response.status_code,429)
        self.assertGreater(int(response.headers['retry-after']),0)
