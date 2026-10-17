import asyncio
import fcntl
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib
from fastapi.testclient import TestClient
from clipora_v8_image_backend.archive import pack,verify
from clipora_v8_image_backend.formats import image_info
from clipora_v8_image_backend.jobs import create_fixture_job,create_image_job,image_payload
from clipora_v8_image_backend.publish import publish_album
from clipora_v8_image_backend.delivery import Album,attach_album_routes
from clipora_v8_web.owned_api import create_owned_app
from clipora_v8_web.owned_jobs import OwnedJobs,IdempotencyConflict
from clipora_v8_web.owned_publish import PublicationDenied
from clipora_v8_web.owned_artifacts import sweep
from clipora_v8_web.owned_runner import observe

ORIGIN='http://127.0.0.1:8090'


def png(width=2,height=2):
    def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x62\x55\xea'*width)*height))+chunk(b'IEND',b'')


class ArchiveTests(unittest.TestCase):
    def test_manifest_order_and_original_bytes(self):
        images=[png(),png(1,1)];data,manifest=pack(images)
        self.assertEqual(verify(io.BytesIO(data)),manifest)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.read('image-01.png'),images[0])
            self.assertEqual(archive.read('image-02.png'),images[1])
        self.assertEqual(manifest['image_count'],2)
        self.assertNotIn('url',json.dumps(manifest))

    def test_bounds_corruption_and_active_formats_rejected(self):
        for images in ([],[png()]*21,[b'<svg/>'],[png()[:-1]], [b'<html/>']):
            with self.subTest(images=len(images)),self.assertRaises(ValueError):pack(images)
        data=bytearray(png());data[-1]^=1
        with self.assertRaises(ValueError):image_info(bytes(data))
        with self.assertRaises(ValueError):image_info(png(5000,1).replace(b'IHDR',b'IDAT',1))

    def test_compressed_and_path_manifests_rejected(self):
        original,manifest=pack([png()])
        for bad_name,compression in (('../escape.png',zipfile.ZIP_STORED),('image-01.png',zipfile.ZIP_DEFLATED)):
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w',compression=compression) as archive:
                archive.writestr('manifest.json',json.dumps(manifest))
                archive.writestr(bad_name,png())
            with self.assertRaises(ValueError):verify(io.BytesIO(output.getvalue()))

    def test_directory_limits_checked_before_allocating_zip_entries(self):
        data,_=pack([png()]);data=bytearray(data)
        struct.pack_into('<H',data,len(data)-12,65535)
        with patch('clipora_v8_image_backend.archive.zipfile.ZipFile',side_effect=AssertionError('Directory parsed too early')):
            with self.assertRaises(ValueError):verify(io.BytesIO(data))

    def test_hash_mismatch_and_extra_manifest_fields_rejected(self):
        for change in ('hash','url'):
            _,manifest=pack([png()]);output=io.BytesIO()
            if change=='hash':manifest['items'][0]['sha256']='0'*64
            else:manifest['items'][0]['url']='https://private.example/a'
            with zipfile.ZipFile(output,'w') as archive:
                archive.writestr('manifest.json',json.dumps(manifest));archive.writestr('image-01.png',png())
            with self.assertRaises(ValueError):verify(io.BytesIO(output.getvalue()))


class OwnedAlbumTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.media=self.root/'media';self.media.mkdir()
        self.now=[1000.];self.store=OwnedJobs(self.root/'state',clock=lambda:self.now[0])
        self.token=self.store.issue_session();self.job=create_fixture_job(self.store,self.token,'a'*32)
        self.store.claim('runner');self.path=self.root/'album.zip';self.path.write_bytes(pack([png(),png(1,1)])[0])

    def test_atomic_publication_and_expiry_sweep_respects_active_reader(self):
        path=publish_album(self.store,self.job['job_id'],'runner',self.path,self.media)
        self.assertEqual(self.store.get(self.job['job_id'])['status'],'completed')
        self.assertEqual(path.read_bytes(),self.path.read_bytes())
        album=Album(path)
        try:
            self.now[0]+=3601
            self.assertEqual(sweep(self.store,self.media),0);self.assertTrue(path.exists())
        finally:album.close()
        self.assertEqual(sweep(self.store,self.media),1)

    def test_cancel_stale_owner_and_expiry_deny_publication(self):
        with self.assertRaises(PublicationDenied):publish_album(self.store,self.job['job_id'],'stale',self.path,self.media)
        self.store.cancel_owned(self.token,self.job['job_id'])
        with self.assertRaises(PublicationDenied):publish_album(self.store,self.job['job_id'],'runner',self.path,self.media)
        self.assertEqual(list(self.media.iterdir()),[])
        self.assertEqual(self.store.get(self.job['job_id'])['status'],'processing')

    def test_cancellation_between_validation_and_commit_is_fenced(self):
        from clipora_v8_image_backend.archive import verify as original
        def cancel(stream):
            result=original(stream);self.store.cancel_owned(self.token,self.job['job_id']);return result
        with patch('clipora_v8_image_backend.publish.verify',cancel):
            with self.assertRaises(PublicationDenied):publish_album(self.store,self.job['job_id'],'runner',self.path,self.media)
        self.assertEqual(list(self.media.iterdir()),[])

    def test_corruption_symlink_and_existing_file_fail_without_overwrite(self):
        link=self.root/'link';link.symlink_to(self.path)
        with self.assertRaises(PublicationDenied):publish_album(self.store,self.job['job_id'],'runner',link,self.media)
        destination=self.media/(self.job['job_id']+'.zip');destination.write_bytes(b'preserve')
        with self.assertRaises(FileExistsError):publish_album(self.store,self.job['job_id'],'runner',self.path,self.media)
        self.assertEqual(destination.read_bytes(),b'preserve')
        self.assertEqual(len(list(self.media.iterdir())),1)
        self.path.write_bytes(b'corrupt'*20)
        with self.assertRaises(PublicationDenied):publish_album(self.store,self.job['job_id'],'runner',self.path,self.media)

    def test_video_job_cannot_publish_image_album(self):
        self.store.confirm_stopped(self.job['job_id'],'runner')
        job=self.store.create_owned(self.token,'https://youtu.be/a','b'*32);self.store.claim('video')
        with self.assertRaises(PublicationDenied):publish_album(self.store,job['job_id'],'video',self.path,self.media)

    def test_typed_requests_idempotency_and_no_network(self):
        self.store.confirm_stopped(self.job['job_id'],'runner')
        with patch('socket.getaddrinfo',side_effect=AssertionError('No DNS')):
            job=create_image_job(self.store,self.token,'https://www.instagram.com/p/abc/','b'*32)
            self.assertEqual(create_image_job(self.store,self.token,'https://www.instagram.com/p/abc/','b'*32),job)
            with self.assertRaises(IdempotencyConflict):create_image_job(self.store,self.token,'https://pin.it/abc','b'*32)
        self.store.claim('image')
        self.assertTrue(image_payload(self.store.payload_for_runner(job['job_id'],'image')))
        with self.assertRaises(ValueError):create_image_job(self.store,self.token,'https://youtu.be/a','c'*32)


class AlbumAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.app=create_owned_app(ORIGIN,self.root/'state',self.root/'video');self.media=self.root/'albums'
        attach_album_routes(self.app,self.media)
        self.client=TestClient(self.app,base_url=ORIGIN);self.client.post('/api/v8/session',headers={'Origin':ORIGIN})
        store=self.app.state.owned_jobs;token=self.client.cookies['clipora_session'];self.token=token
        self.job=create_fixture_job(store,token,'a'*32);self.id=self.job['job_id'];store.claim('runner')
        self.path=self.root/'archive.zip';self.path.write_bytes(pack([png(),png(1,1)])[0])
        publish_album(store,self.id,'runner',self.path,self.media);self.base='/api/v8/jobs/'+self.id

    def test_owned_manifest_individual_images_zip_head_and_range(self):
        response=self.client.get(self.base+'/images');self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['image_count'],2)
        self.assertEqual(self.client.get(self.base+'/images/1').content,png())
        self.assertEqual(self.client.get(self.base+'/images/2').content,png(1,1))
        self.assertEqual(self.client.get(self.base+'/album.zip').content,self.path.read_bytes())
        response=self.client.head(self.base+'/images/1');self.assertEqual(response.content,b'');self.assertEqual(int(response.headers['content-length']),len(png()))
        response=self.client.get(self.base+'/images/1',headers={'Range':'bytes=0-7'})
        self.assertEqual(response.status_code,206);self.assertEqual(response.content,png()[:8])
        response=self.client.get(self.base+'/images/1',headers={'Range':'bytes=-4'})
        self.assertEqual(response.content,png()[-4:])
        response=self.client.get(self.base+'/album.zip',headers={'Range':'bytes=0-3'})
        self.assertEqual(response.status_code,206);self.assertEqual(response.content,b'PK\x03\x04')

    def test_foreign_missing_expired_jobs_never_expose_manifest_or_files(self):
        stranger=TestClient(self.app,base_url=ORIGIN);stranger.post('/api/v8/session',headers={'Origin':ORIGIN})
        for suffix in ('/images','/images/1','/album.zip'):
            self.assertEqual(stranger.get(self.base+suffix).status_code,404)
            self.assertEqual(stranger.get('/api/v8/jobs/'+'f'*32+suffix).status_code,404)
        store=self.app.state.owned_jobs
        with store.transaction() as db:db.execute('UPDATE job_ownership SET expires_at=0 WHERE job_id=?',(self.id,))
        self.assertEqual(self.client.get(self.base+'/images').status_code,404)

    def test_ranges_invalid_indices_duplicate_cookie_and_public_submission_blocked(self):
        for position in ('0','-1','01','3','999'):
            self.assertEqual(self.client.get(self.base+'/images/'+position).status_code,404)
        for value in ('bytes=999999-','bytes=7-0','bytes=-0','bytes=0-1,3-4','bad'):
            response=self.client.get(self.base+'/images/1',headers={'Range':value})
            self.assertEqual(response.status_code,416);self.assertEqual(response.headers['content-range'],'bytes */'+str(len(png())))
        self.assertEqual(self.client.get(self.base+'/images',headers={'Cookie':f'clipora_session={self.token}; clipora_session={self.token}'}).status_code,404)
        self.assertEqual(self.client.post('/api/v8/download',headers={'Origin':ORIGIN},json={'url':'https://pin.it/a','media_kind':'images'}).status_code,503)


class ObserverTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_observer_uses_album_publisher_only_after_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();store=OwnedJobs(root/'state');token=store.issue_session()
            job=create_fixture_job(store,token,'a'*32);store.claim('runner');media=root/'media';media.mkdir()
            source=root/'album.zip';source.write_bytes(pack([png()])[0]);stopped=[]
            class Handle:
                async def wait(self):return source
                async def stop(self):stopped.append(True);return True
            def publish(*args):
                self.assertTrue(stopped);return publish_album(*args)
            self.assertTrue(await observe(store,job['job_id'],'runner',Handle(),media,publisher=publish))
            self.assertTrue((media/(job['job_id']+'.zip')).exists())




class LocalImageAdmissionTests(unittest.TestCase):
    def test_only_fixed_image_fixture_can_enter_HTTP_queue(self):
        from clipora_v8_local_workflow.app import create_local_app
        class FakeScheduler:
            def __init__(self,*args):self.available=False
            async def start(self):self.available=True
            async def close(self):self.available=False
        with tempfile.TemporaryDirectory() as temp:
            app=create_local_app(ORIGIN,Path(temp).resolve(),scheduler_factory=FakeScheduler)
            with TestClient(app,base_url=ORIGIN) as client:
                headers={'Origin':ORIGIN,'Idempotency-Key':'a'*32}
                self.assertEqual(client.post('/api/v8/samples/images',headers=headers,json={}).status_code,403)
                client.post('/api/v8/session',headers={'Origin':ORIGIN})
                self.assertEqual(client.post('/api/v8/samples/images',headers=headers,json={'url':'https://pin.it/a'}).status_code,422)
                first=client.post('/api/v8/samples/images',headers=headers,json={});self.assertEqual(first.status_code,202)
                self.assertEqual(client.post('/api/v8/samples/images',headers=headers,json={}).json(),first.json())
                self.assertEqual(client.post('/api/v8/samples',headers=headers,json={}).status_code,409)
                self.assertEqual(client.post('/api/v8/jobs/'+first.json()['job_id']+'/cancel',headers={'Origin':ORIGIN}).status_code,204)


class PublicImageDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_image_payload_is_never_dispatched_by_local_scheduler(self):
        from clipora_v8_local_workflow.scheduler import Scheduler
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();store=OwnedJobs(root/'state');token=store.issue_session();media=root/'media';media.mkdir()
            job=create_image_job(store,token,'https://pin.it/a','a'*32);calls=[]
            def forbidden(*args):calls.append(args);raise AssertionError('Public job dispatched')
            scheduler=Scheduler(store,media,factory=forbidden,image_factory=forbidden)
            await scheduler.start()
            try:
                async with asyncio.timeout(2):
                    while store.get(job['job_id'])['status']!='failed':await asyncio.sleep(.01)
                self.assertEqual(calls,[])
            finally:await scheduler.close()


if __name__=='__main__':unittest.main()
