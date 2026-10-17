"""SIGKILL only disposable queue actors/runners; never the Docker daemon.

A test-only wrapper pauses collection after the actual Docker worker starts.
This gives a deterministic crash boundary without adding production hooks.
"""
import fcntl
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))
from clipora_v8_browser_real_mp4 import routes
from clipora_v8_browser_real_mp4.job_store import JobStore
from clipora_v8_verified_tls.owned_resources import cleanup_job


def wait_for(predicate, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.15)
    raise TimeoutError('Fault-test checkpoint timeout')


def resources(job):
    filters = ['--filter', 'label=clipora.offline.owner=clipora-v8-verified-offline',
               '--filter', 'label=clipora.offline.job=' + job]
    found = []
    for args in (['ps', '-aq'], ['network', 'ls', '-q']):
        result = subprocess.run(['docker', *args, *filters], capture_output=True, text=True, check=True, timeout=15)
        found.extend(result.stdout.split())
    return found


def lock_free(directory):
    fd = os.open(directory / 'runner.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False
    finally:
        os.close(fd)


def run_case(mode):
    with tempfile.TemporaryDirectory(prefix='clipora-process-fault-') as tmp:
        root = Path(tmp); staging = root / 'staging'; staging.mkdir()
        database = JobStore(root / 'state')
        first, second = database.create(), database.create()
        checkpoint, release = root / 'checkpoint.json', root / 'release'
        wrapper = root / 'runner.py'
        wrapper.write_text(f'''
import json, os, runpy, sys, time
from pathlib import Path
sys.path.insert(0, {str(HERE)!r})
import bounded_worker
original = bounded_worker.collect_worker
def paused(*args, **kwargs):
    Path({str(checkpoint)!r}).write_text(json.dumps({{"pid": os.getpid(), "worker": args[0], "scratch": str(Path(kwargs["expected_bundle"]).resolve().parents[1])}}))
    deadline = time.monotonic() + 40
    while not Path({str(release)!r}).exists():
        if time.monotonic() > deadline: raise TimeoutError("Test release missing")
        time.sleep(.1)
    return original(*args, **kwargs)
bounded_worker.collect_worker = paused
runpy.run_path({str(HERE / 'run_browser_verified.py')!r}, run_name="__main__")
''')
        actor_code = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from clipora_v8_browser_real_mp4 import routes
from clipora_v8_browser_real_mp4.job_store import JobStore
routes.STORE = JobStore(sys.argv[2])
routes.STAGING = Path(sys.argv[3])
routes.RUNNER = Path(sys.argv[4])
assert routes.dispatch_once()
'''
        child_pid = None
        scratch = None
        with (root / 'actor.log').open('w') as log:
            actor = subprocess.Popen([sys.executable, '-B', '-c', actor_code, str(BACKEND),
                                      str(database.directory), str(staging), str(wrapper)],
                                     stdout=log, stderr=log,
                                     env={**os.environ, 'CLIPORA_V8_USE_COMPOSE': '1'})
            try:
                wait_for(checkpoint.exists)
                state = json.loads(checkpoint.read_text()); child_pid = state['pid']; scratch = Path(state['scratch'])
                assert resources(first['job_id']), 'Actual Docker resources missing'
                assert database.get(first['job_id'])['status'] == 'processing'
                with patch.object(routes, 'STORE', database), patch.object(routes, 'STAGING', staging):
                    if mode == 'parent-killed':
                        actor.kill(); actor.wait(timeout=10)
                        assert actor.returncode == -signal.SIGKILL
                        assert not routes.dispatch_once(), 'Surviving child lost global lock'
                        assert database.get(second['job_id'])['status'] == 'queued'
                        release.touch()
                        wait_for(lambda: lock_free(database.directory), 65)
                    else:
                        os.kill(child_pid, signal.SIGKILL)
                        actor.wait(timeout=35)
                        assert actor.returncode == 0, (root / 'actor.log').read_text()
                        assert database.get(first['job_id'])['status'] == 'failed'
                        assert not resources(first['job_id']), 'Killed runner resources remain'
                        assert database.get(second['job_id'])['status'] == 'queued'
                    # Recovery and then a real successor job, using the normal runner.
                    with patch.dict(os.environ, {'CLIPORA_V8_USE_COMPOSE': '1'}):
                        assert routes.dispatch_once()
                assert database.get(first['job_id'])['status'] == 'failed'
                assert database.get(second['job_id'])['status'] == 'completed'
                assert not (staging / (first['tag'] + '.mp4')).exists()
                assert (staging / (second['tag'] + '.mp4')).read_bytes() == (BACKEND / 'clipora_v8_real_guarded_e2e/fixtures/video.mp4').read_bytes()
                assert not resources(first['job_id']) and not resources(second['job_id'])
                print('PASS: ' + mode, flush=True)
                return {'case': mode, 'actual_docker_worker_at_crash': True,
                        'interrupted_job_failed': True, 'successor_completed': True,
                        'owned_resources_removed': True,
                        'inherited_lock_verified': mode == 'parent-killed'}
            finally:
                if actor.poll() is None:
                    actor.kill(); actor.wait(timeout=10)
                release.touch()
                if child_pid is not None:
                    # Kill only this test's checkpointed child if it still holds our lock.
                    if not lock_free(database.directory):
                        try: os.kill(child_pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                        wait_for(lambda: lock_free(database.directory), 10)
                cleanup_job(first['job_id']); cleanup_job(second['job_id'])
                if scratch is not None:
                    assert scratch.parent == Path(tempfile.gettempdir()).resolve()
                    assert scratch.name.startswith('clipora-browser-tls-')
                    shutil.rmtree(scratch, ignore_errors=False) if scratch.exists() else None


def main():
    report = {'offline_only': True, 'docker_daemon_stopped': False,
              'cases': [run_case(mode) for mode in ('parent-killed', 'runner-killed')]}
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
