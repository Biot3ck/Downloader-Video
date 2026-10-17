"""Offline E2E of the real v8 worker with a storage monitor; NOT production security."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parent
IMAGE_SERVER = 'clipora-gateway:v8-test'
IMAGE_WORKER = 'clipora-worker:v8-dns'


def docker(*args, timeout=30):
    res = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=timeout)
    if res.returncode:
        raise RuntimeError(f'Docker {args[:3]} failed: {res.stderr[-700:]}')
    return res.stdout.strip()


def ip(container, net):
    return json.loads(docker('inspect', container))[0]['NetworkSettings']['Networks'][net]['IPAddress']


def await_ready(container, marker):
    for _ in range(60):
        logs = docker('logs', container)
        if marker in logs: return
        state = json.loads(docker('inspect', container))[0]['State']
        if not state['Running']: raise RuntimeError(f'{container} exited: {logs}')
        time.sleep(0.2)
    raise RuntimeError(f'{container} not ready: {docker("logs", container)}')


def folder_size(root):
    size = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            target = Path(directory) / name
            if target.is_symlink(): raise RuntimeError('Symlink in workspace')
            if target.is_file(): size += target.stat().st_size
    return size


def main():
    for needed in ('real_download_worker_v8.py', 'download_worker.py',
                   'worker_entry_v8.py', 'config.py', 'url_security.py',
                   'download_limits.py', 'video_inspector.py'):
        if not (BACKEND / needed).is_file():
            raise RuntimeError('Missing backend file: ' + needed)
    tag = uuid.uuid4().hex[:10]
    nw, ne = f'clipora-grw-{tag}', f'clipora-gre-{tag}'
    eg, gw, wr = (f'clipora-gre-{tag}', f'clipora-grg-{tag}', f'clipora-grd-{tag}')
    output = BACKEND / 'v8-guarded-e2e-test-output' / tag
    output.mkdir(parents=True, exist_ok=False)
    created=[]
    proc=None
    try:
        for image in (IMAGE_SERVER, IMAGE_WORKER): docker('image','inspect',image)
        for net in (nw, ne):
            docker('network','create','--internal',net)
            created.append(('network',net))
            if not json.loads(docker('network','inspect',net))[0]['Internal']:
                raise RuntimeError('Network unexpectedly public')
        base=['--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
              '--memory','256m','--pids-limit','96','--user','65534:65534']
        mount=['-v',f'{ROOT}:/fixture:ro']
        docker('run','-d','--name',eg,'--network',ne,*base,*mount,
               IMAGE_SERVER,'python3','-B','-u','/fixture/egress.py')
        created.append(('container',eg));await_ready(eg,'CLIPORA E2E EGRESS READY')
        docker('run','-d','--name',gw,'--network',ne,'-e',f'EGRESS_IP={ip(eg,ne)}',
               *base,*mount,IMAGE_SERVER,'python3','-B','-u','/fixture/gateway.py')
        created.append(('container',gw));await_ready(gw,'CLIPORA E2E GATEWAY READY')
        docker('network','connect',nw,gw)
        job = uuid.uuid4().hex
        # Test-only: fixture uses a self-signed certificate, so TLS trust is bypassed
        # only in worker_actual_test.py, NOT in the original v8 worker source.
        cmd=['docker','run','--rm','--name',wr,'--network',nw,
             '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
             '--memory','384m','--pids-limit','96',
             '--user',f'{os.getuid()}:{os.getgid()}',
             '--tmpfs','/tmp:rw,nosuid,nodev,size=32m',
             '-e','PYTHONPATH=/app:/fixture',
             '-e',f'CLIPORA_V8_PROXY_URL=http://{ip(gw,nw)}:8888',
             '-e',f'CLIPORA_TEST_DOWNLOAD_DIR=/output',
             '-e',f'CLIPORA_TEST_JOB_ID={job}',
             '-v',f'{BACKEND}:/app:ro','-v',f'{ROOT}:/fixture:ro',
             '-v',f'{output}:/output:rw',
             '-w','/app','--entrypoint','python3',IMAGE_WORKER,
             '-B','/fixture/worker_actual_test.py']
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        deadline=time.monotonic()+90
        while proc.poll() is None:
            if folder_size(output)>64*1024*1024:
                raise RuntimeError('Fixture exceeded 64 MiB workspace budget')
            if time.monotonic()>deadline:
                raise TimeoutError('Actual v8 Worker exceeded 90s fixture limit')
            time.sleep(0.1)
        stdout,stderr=proc.communicate(timeout=5)
        if proc.returncode:
            raise RuntimeError('Worker failed:\n'+stderr[-2500:]+'\n'+stdout[-1000:])
        if 'PASS: actual v8 process_video' not in stdout:
            raise RuntimeError('Missing verified completion marker:\n'+stdout)
        if folder_size(output)>64*1024*1024:
            raise RuntimeError('Fixture workspace budget exceeded')
        print(stdout.strip())
        print('PASS: workspace size checked; worker exited; isolated internal networks')
        print('V8 REAL WORKER GUARDED E2E PASSED (OFFLINE ONLY)')
    finally:
        # Stop worker first, then all servers and networks.
        subprocess.run(['docker','rm','-f',wr],capture_output=True,timeout=15)
        if proc and proc.poll() is None:
            proc.kill()
            proc.communicate()
        for kind, name in reversed(created):
            args=['docker','rm','-f',name] if kind=='container' else ['docker','network','rm',name]
            subprocess.run(args,capture_output=True,timeout=15)
        shutil.rmtree(output,ignore_errors=True)

if __name__=='__main__': main()
