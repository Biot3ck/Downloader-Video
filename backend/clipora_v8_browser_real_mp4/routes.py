"""Durable, globally bounded offline browser jobs. Keep bound to localhost."""
from contextlib import asynccontextmanager
import fcntl
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from clipora_v8_verified_tls.staging_store import MAX_STAGED_FILES
from clipora_v8_verified_tls.owned_resources import cleanup_job
from .artifact_delivery import PinnedVideoResponse, unlink_idle
from .job_store import JobStore, QueueFull

BASE = Path(__file__).resolve().parent
BACKEND = BASE.parent
STAGING = BASE / 'staging'
STATE = BACKEND / 'clipora_v8_runtime'
RUNNER = BACKEND / 'clipora_v8_verified_tls' / 'run_browser_verified.py'
TTL = 15 * 60
MAX_SIZE = 64 * 1024 * 1024
STORE = None
STORE_LOCK = threading.Lock()
WAKE = threading.Event()
UUID_PATTERN = re.compile(r'^[0-9a-f]{32}$')
TAG_PATTERN = re.compile(r'^CLIPORA_BROWSER_MP4_READY=([0-9a-f]{10})$', re.M)
TLS_PATTERN = re.compile(r'^CLIPORA_BROWSER_TLS_VERIFIED=1$', re.M)


def store():
    global STORE
    with STORE_LOCK:
        if STORE is None:
            STORE = JobStore(STATE)
        return STORE


def cleanup():
    now = time.time()
    database = store()
    rows = database.list()
    known = {row['tag'] for row in rows}
    for row in rows:
        if row['status'] in ('completed', 'failed') and now-row['updated_at'] > TTL:
            if unlink_idle(STAGING / (row['tag']+'.mp4')):
                database.delete_expired(row['job_id'], now-TTL)
    if STAGING.exists():
        for path in STAGING.glob('*.mp4'):
            if re.fullmatch(r'[0-9a-f]{10}\.mp4', path.name) and path.stem not in known:
                try:
                    if not path.is_symlink() and now-path.stat().st_mtime > TTL:
                        unlink_idle(path)
                except FileNotFoundError:
                    pass


def execute(job, owner, lock_fd):
    tag = job['tag']
    try:
        result = subprocess.run(
            [sys.executable, '-B', str(RUNNER)], cwd=str(BACKEND),
            capture_output=True, text=True, timeout=150, check=True,
            # The child retains the global lock if the web process dies.
            pass_fds=(lock_fd,),
            env={**os.environ, 'CLIPORA_V8_OFFLINE_BROWSER_TEST':'1',
                 'CLIPORA_OFFLINE_JOB_ID':job['job_id'], 'CLIPORA_OFFLINE_ARTIFACT_TAG':tag,
                 'CLIPORA_OFFLINE_STAGING_DIR':str(STAGING)},
        )
        marker = TAG_PATTERN.search(result.stdout)
        if (not marker or marker.group(1) != tag or not TLS_PATTERN.search(result.stdout)
                or 'V8 SECURE EGRESS REAL WORKER E2E PASSED (OFFLINE ONLY)' not in result.stdout):
            raise ValueError('Verified completion missing')
        # Pin and validate the inode, then release the validation-only response.
        checked = PinnedVideoResponse(STAGING / (tag+'.mp4'), MAX_SIZE)
        checked.close()
        if not store().finish(job['job_id'], owner, True, 'Offline MP4 ready; expires in 15 minutes'):
            raise ValueError('Stale job owner')
    except (subprocess.SubprocessError, OSError, ValueError):
        # Also handles a killed runner that could not execute its finally block.
        cleanup_job(job['job_id'])
        unlink_idle(STAGING / (tag+'.mp4'))
        store().finish(job['job_id'], owner, False, 'Secure offline job failed. Try a new sample.')


def dispatch_once():
    database = store()
    fd = os.open(database.directory / 'runner.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        # No inherited lock holder exists, so these jobs lost their runner.
        # Recovery must finish before another worker may be admitted.
        for row in database.list('processing'):
            cleanup_job(row['job_id'])
            if not unlink_idle(STAGING / (row['tag']+'.mp4')):
                raise RuntimeError('Interrupted artifact still in use')
            database.interrupted(row['job_id'])
        cleanup()
        owner = uuid4().hex
        job = database.claim(owner)
        if job is None:
            return False
        execute(job, owner, fd)
        return True
    finally:
        # Do not LOCK_UN here: a surviving child may share this open-file
        # description after web-process death. Closing releases only our copy.
        os.close(fd)


def scheduler(stop):
    while not stop.is_set():
        try:
            if dispatch_once():
                continue
        except Exception:
            logging.getLogger(__name__).exception('Offline scheduler/recovery failed; no replacement worker started')
        WAKE.wait(.5)
        WAKE.clear()


@asynccontextmanager
async def lifespan(app):
    stop = threading.Event()
    thread = None
    if os.environ.get('CLIPORA_V8_OFFLINE_BROWSER_TEST') == '1':
        thread = threading.Thread(target=scheduler, args=(stop,), daemon=True, name='clipora-offline-dispatcher')
        thread.start()
    try:
        yield
    finally:
        stop.set(); WAKE.set()
        if thread:
            import asyncio
            await asyncio.to_thread(thread.join, 2)


router = APIRouter(lifespan=lifespan)


@router.post('/api/v8/real-offline/jobs', status_code=202)
def start():
    if os.environ.get('CLIPORA_V8_OFFLINE_BROWSER_TEST') != '1':
        raise HTTPException(503, 'Offline Docker feature not enabled')
    cleanup()
    files = list(STAGING.glob('*.mp4'))
    if len(files) >= MAX_STAGED_FILES:
        raise HTTPException(507, 'Offline fixture file limit reached')
    try:
        used = sum(path.stat().st_size for path in files if path.is_file() and not path.is_symlink())
    except FileNotFoundError:
        raise HTTPException(503, 'Storage changed; try again')
    if used >= MAX_SIZE:
        raise HTTPException(507, 'Offline fixture storage full')
    try:
        job = store().create()
    except QueueFull:
        raise HTTPException(429, 'Offline queue is full')
    WAKE.set()
    return {'job_id':job['job_id'], 'status':'queued', 'status_url':f"/api/v8/real-offline/jobs/{job['job_id']}"}


@router.get('/api/v8/real-offline/jobs/{job_id}')
def status(job_id: str):
    if not UUID_PATTERN.fullmatch(job_id):
        raise HTTPException(400, 'Invalid job ID')
    cleanup()
    job = store().get(job_id)
    if not job or (job['status'] in ('completed','failed') and time.time()-job['updated_at'] > TTL):
        raise HTTPException(404, 'Job expired or not found')
    result = {key:job[key] for key in ('job_id','status','updated_at','message')}
    if job['status'] == 'completed':
        result['download_url'] = f'/api/v8/real-offline/files/{job_id}'
    return result


@router.get('/api/v8/real-offline/files/{job_id}')
def file_download(job_id: str):
    if not UUID_PATTERN.fullmatch(job_id):
        raise HTTPException(400, 'Invalid job ID')
    cleanup()
    job = store().get(job_id)
    if not job or job['status'] != 'completed' or time.time()-job['updated_at'] > TTL:
        raise HTTPException(404, 'File expired or not found')
    try:
        return PinnedVideoResponse(STAGING / (job['tag']+'.mp4'), MAX_SIZE)
    except (OSError, ValueError):
        raise HTTPException(404, 'File unavailable')
