import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
BACKEND=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(BACKEND))
from clipora_v8_browser_real_mp4.artifact_delivery import PinnedVideoResponse,unlink_idle


class PinnedDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'video.mp4'
        self.data=b'\x00\x00\x00\x20ftypisom'+b'x'*(180*1024)
        self.path.write_bytes(self.data)
    def tearDown(self):self.temp.cleanup()

    async def serve(self,response,headers=(),send_hook=None,method='GET'):
        messages=[]
        async def send(message):
            messages.append(message)
            if send_hook:await send_hook(message)
        async def receive():return {'type':'http.disconnect'}
        scope={'type':'http','method':method,'headers':list(headers),'extensions':{'http.response.pathsend':{}}}
        await response(scope,receive,send)
        return messages

    async def test_cleanup_skips_active_stream_until_response_finishes(self):
        response=PinnedVideoResponse(self.path,1024*1024)
        async def inspect(message):
            if message['type']=='http.response.body':
                self.assertFalse(unlink_idle(self.path));self.assertTrue(self.path.is_file())
        messages=await self.serve(response,send_hook=inspect)
        self.assertEqual(b''.join(x.get('body',b'') for x in messages),self.data)
        self.assertIsNone(response.fd);self.assertTrue(unlink_idle(self.path))

    async def test_pinned_inode_survives_name_replacement(self):
        response=PinnedVideoResponse(self.path,1024*1024)
        self.path.unlink();self.path.write_bytes(b'changed')
        messages=await self.serve(response)
        self.assertEqual(b''.join(x.get('body',b'') for x in messages),self.data)

    async def test_ranges_and_head_release_lock(self):
        for headers,method in [([(b'range',b'bytes=0-15')],'GET'), ([(b'range',b'bytes=-16')],'GET'),([], 'HEAD')]:
            with self.subTest(headers=headers,method=method):
                response=PinnedVideoResponse(self.path,1024*1024)
                messages=await self.serve(response,headers,method=method)
                self.assertEqual(messages[0]['status'],206 if headers else 200)
                body=b''.join(x.get('body',b'') for x in messages)
                self.assertEqual(body,self.data[:16] if headers and b'-16' not in headers[0][1] else self.data[-16:] if headers else b'')
                self.assertIsNone(response.fd)

    async def test_cancellation_releases_descriptor_and_lock(self):
        response=PinnedVideoResponse(self.path,1024*1024);started=asyncio.Event()
        async def block(message):
            if message['type']=='http.response.body':
                started.set();await asyncio.Event().wait()
        task=asyncio.create_task(self.serve(response,send_hook=block))
        await asyncio.wait_for(started.wait(),2);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertIsNone(response.fd);self.assertTrue(unlink_idle(self.path))

    async def test_expiry_cleanup_waits_for_pinned_response(self):
        import time
        from unittest.mock import patch
        from clipora_v8_browser_real_mp4 import routes
        from clipora_v8_browser_real_mp4.job_store import JobStore
        db=JobStore(Path(self.temp.name)/'state')
        row=db.create();db.claim('owner');db.finish(row['job_id'],'owner',True,'ready')
        path=Path(self.temp.name)/(row['tag']+'.mp4');path.write_bytes(self.data)
        with patch.object(routes,'STORE',db),patch.object(routes,'STAGING',Path(self.temp.name)):
            response=routes.file_download(row['job_id'])
            with db.connection() as connection:
                connection.execute('UPDATE jobs SET updated_at=? WHERE job_id=?',(time.time()-routes.TTL-1,row['job_id']))
            routes.cleanup()
            self.assertTrue(path.is_file());self.assertIsNotNone(db.get(row['job_id']))
            messages=await self.serve(response)
            self.assertEqual(b''.join(x.get('body',b'') for x in messages),self.data)
            routes.cleanup()
            self.assertFalse(path.exists());self.assertIsNone(db.get(row['job_id']))

    async def test_bad_range_releases_descriptor(self):
        response=PinnedVideoResponse(self.path,1024*1024)
        messages=await self.serve(response,[(b'range',b'bytes=99999999-')])
        self.assertEqual(messages[0]['status'],416);self.assertIsNone(response.fd)

    def test_symlink_and_non_mp4_rejected(self):
        link=Path(self.temp.name)/'link';link.symlink_to(self.path)
        with self.assertRaises(OSError):PinnedVideoResponse(link,1024*1024)
        self.path.write_bytes(b'z'*200)
        with self.assertRaises(ValueError):PinnedVideoResponse(self.path,1024*1024)


if __name__=='__main__':unittest.main()
