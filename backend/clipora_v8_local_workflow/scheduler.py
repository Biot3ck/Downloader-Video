"""Single leader for local sample jobs; never dispatches public video URLs."""
import asyncio
import fcntl
import os
from pathlib import Path
import shutil
from uuid import uuid4
from clipora_v8_web.owned_runner import observe
from clipora_v8_web.owned_artifacts import sweep
from .resources import SampleResource,ImageSampleResource,cleanup
from clipora_v8_image_backend.jobs import FIXTURE
from clipora_v8_image_backend.publish import publish_album


class Scheduler:
    def __init__(self,store,artifacts,*,factory=SampleResource,image_factory=ImageSampleResource):
        self.store,self.artifacts,self.factory=store,Path(artifacts),factory
        self.image_factory=image_factory
        self.work=store.directory/'work';self.work.mkdir(mode=0o700,exist_ok=True)
        if self.work.is_symlink():raise ValueError('Symlinked work directory rejected')
        self.fd=None;self.task=None;self.available=False

    async def start(self):
        self.fd=os.open(self.store.directory/'scheduler.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            # A still-running helper inherits the lock, so recovery cannot race
            # its resource creation or artifact export after web-process death.
            for job in self.store.list('processing'):
                await cleanup(job['owner'])
                self.store.confirm_stopped(job['job_id'],job['owner'])
            for path in self.work.iterdir():
                if path.is_symlink() or not path.is_dir():raise RuntimeError('Unexpected sample work entry')
                if len(path.name)!=32 or any(c not in '0123456789abcdef' for c in path.name):
                    raise RuntimeError('Unexpected sample work identity')
                shutil.rmtree(path)
            sweep(self.store,self.artifacts)
            self.available=True;self.task=asyncio.create_task(self.run())
        except BaseException:
            os.close(self.fd);self.fd=None;raise

    async def run(self):
        try:
            while True:
                owner=uuid4().hex;job=self.store.claim(owner)
                if job is None:
                    sweep(self.store,self.artifacts)
                    await asyncio.sleep(.3);continue
                payload=self.store.payload_for_runner(job['job_id'],owner)
                if payload not in ('clipora:offline-sample',FIXTURE):
                    self.store.confirm_stopped(job['job_id'],owner)
                    continue
                factory=self.image_factory if payload==FIXTURE else self.factory
                resource=factory(owner,self.work/owner,self.fd)
                try:await observe(self.store,job['job_id'],owner,resource,self.artifacts,stop_timeout=10,
                                  publisher=publish_album if payload==FIXTURE else None)
                except asyncio.CancelledError:raise
                except Exception:
                    # Stop failure deliberately preserves processing. Stop
                    # admission rather than launching another resource owner.
                    if self.store.get(job['job_id'])['status']=='processing':raise
                finally:
                    if self.store.get(job['job_id'])['status']!='processing':
                        path=self.work/owner
                        if path.exists():shutil.rmtree(path)
        except asyncio.CancelledError:raise
        except Exception:self.available=False
        finally:self.available=False

    async def close(self):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)
        self.available=False
        if self.fd is not None:os.close(self.fd);self.fd=None
