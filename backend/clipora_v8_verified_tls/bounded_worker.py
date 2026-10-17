"""Collect only a completed fixture from a live, kernel-bounded tmpfs workspace."""
import os
import json
from pathlib import Path
import subprocess
import time
import re

from sandbox_bundle import attest_worker_mounts

READY = 'PASS: actual v8 worker MP4 with certificate and hostname verification'
MAX_WORKSPACE_BYTES = 64 * 1024 * 1024


def workspace_mount():
    return f'/output:rw,nosuid,nodev,noexec,size=64m,uid={os.getuid()},gid={os.getgid()},mode=0700'


def collect_worker(name, output, job, timeout=60, *, expected_bundle):
    if not re.fullmatch(r'[0-9a-f]{32}', job):
        raise ValueError('Invalid export job')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True, timeout=10)
        if state.returncode:
            raise RuntimeError('Cannot inspect fixture worker')
        info = json.loads(state.stdout)[0]
        attest_worker_mounts(info, expected_bundle)
        if not info['HostConfig']['ReadonlyRootfs']:
            raise RuntimeError('Worker root must be read-only')
        mounts = info['HostConfig'].get('Tmpfs', {})
        if mounts.get('/output') != workspace_mount().split(':', 1)[1]:
            raise RuntimeError('Worker tmpfs quota not attested')
        logs = subprocess.run(['docker', 'logs', name], capture_output=True, text=True, timeout=10)
        if logs.returncode:
            raise RuntimeError('Cannot read fixture worker result')
        if READY in logs.stdout:
            # Caller supplied a fresh host temporary directory. Never copy the
            # entire writable workspace, only the single known job output.
            target = Path(output) / 'video.mp4'
            # Docker Desktop's archive API cannot reliably read tmpfs mounts.
            # Execute a fixed bounded reader inside the live mount namespace.
            script = (
                'import os,stat,sys; '
                f'fd=os.open("/output/{job}/video.mp4",os.O_RDONLY|os.O_NOFOLLOW); '
                'info=os.fstat(fd); '
                f'assert stat.S_ISREG(info.st_mode) and 128<=info.st_size<={MAX_WORKSPACE_BYTES}; '
                'stream=os.fdopen(fd,"rb"); data=stream.read(info.st_size+1); '
                'assert len(data)==info.st_size; '
                'sys.stdout.buffer.write(data); stream.close()'
            )
            copied = subprocess.run(['docker', 'exec', name, 'python3', '-B', '-c', script],
                                    capture_output=True, timeout=10)
            if copied.returncode or not 128 <= len(copied.stdout) <= MAX_WORKSPACE_BYTES:
                raise RuntimeError('Invalid bounded worker export: ' + copied.stderr.decode(errors='replace')[-1000:])
            target.write_bytes(copied.stdout)
            return 0, logs.stdout, logs.stderr
        if not info['State']['Running']:
            if info['State']['ExitCode'] == 0:
                raise RuntimeError('Worker exited without verified completion')
            return info['State']['ExitCode'], logs.stdout, logs.stderr
        time.sleep(.15)
    raise TimeoutError('Bounded worker exceeded offline deadline')
