"""Export one verified offline MP4. No legacy/insecure runner fallback."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

from bounded_worker import collect_worker, workspace_mount
from staging_store import publish_artifact
from owned_resources import labels
from sandbox_bundle import build_bundles

from run_verified_tls import (
    BACKEND, FIXTURE, HERE, IMAGES, STAGE, certificates, command,
    docker, run_case, size,
)

STAGING = Path(os.environ.get('CLIPORA_OFFLINE_STAGING_DIR', str(BACKEND / 'clipora_v8_browser_real_mp4' / 'staging')))
MAX_BYTES = 64 * 1024 * 1024


def verify_mp4(path):
    if path.is_symlink() or not path.is_file() or not 128 <= path.stat().st_size <= MAX_BYTES:
        raise RuntimeError('Invalid offline MP4 artifact')
    with path.open('rb') as stream:
        if b'ftyp' not in stream.read(16):
            raise RuntimeError('Invalid MP4 signature')
    data = json.loads(command(['ffprobe', '-v', 'error', '-show_entries',
                              'stream=codec_name,codec_type,pix_fmt', '-of', 'json', str(path)]))
    if not any(s.get('codec_type') == 'video' and s.get('codec_name') == 'h264'
               and s.get('pix_fmt') == 'yuv420p' for s in data['streams']):
        raise RuntimeError('Unexpected fixture video codec')


def compose_fixture(server, trust, root, artifact):
    """Use existing internal Compose networks with a temporary TLS-only overlay."""
    output = root / 'compose-output'; output.mkdir()
    bundles = build_bundles(BACKEND,HERE,FIXTURE,STAGE,root/'bundles-compose')
    owner = f'{os.getuid()}:{os.getgid()}'
    job = uuid.uuid4().hex
    worker_name = 'clipora-vtls-b-worker-' + uuid.uuid4().hex[:10]
    overlay = {
        'services': {
            'egress': {
                'pull_policy': 'never', 'user': owner, 'cpus': 1,
                'command': ['python3', '-B', '-u', '/fixture/egress_fixture.py'],
                'environment': {'CLIPORA_TLS_CASE': 'valid'},
                'volumes': [f'{bundles["services"]}:/fixture:ro', f'{bundles["policies"]}:/stage:ro', f'{server}:/tls:ro'],
            },
            'gateway': {'pull_policy': 'never', 'cpus': 1, 'volumes': [f'{bundles["services"]}:/fixture:ro']},
            'worker': {
                'pull_policy': 'never', 'user': owner, 'cpus': 1,
                'environment': {
                    'PYTHONPATH': '/app',
                    'CLIPORA_VERIFIED_TLS_OFFLINE_ONLY': '1',
                    'CLIPORA_V8_PROXY_URL': 'http://gateway:8888',
                    'CLIPORA_TEST_DOWNLOAD_DIR': '/output',
                    'CLIPORA_TEST_JOB_ID': job, 'CLIPORA_HOLD_VERIFIED_OUTPUT': '1',
                    'SSL_CERT_FILE': '/trust/ca.pem', 'SSL_CERT_DIR': '/trust/empty',
                },
                'volumes': [f'{bundles["worker"]}:/app:ro', f'{trust}:/trust:ro'],
                'tmpfs': [workspace_mount()],
            },
        },
    }
    for service in overlay['services'].values():
        service['labels'] = labels()
    overlay['networks'] = {name: {'labels': labels()} for name in ('worker_gateway', 'gateway_egress')}
    overlay_path = root / 'verified-tls.compose.json' 
    overlay_path.write_text(json.dumps(overlay))
    project = 'clipora-vtls-b-' + uuid.uuid4().hex[:10]
    args = ['docker', 'compose', '-p', project,
            '-f', str(BACKEND / 'clipora-compose-v8-offline.yaml'),
            '-f', str(BACKEND / 'clipora-compose-v8-secure-offline.override.yaml'),
            '-f', str(overlay_path)]
    try:
        config = json.loads(command(args + ['config', '--format', 'json']))
        if not all(n.get('internal') is True for n in config['networks'].values()):
            raise RuntimeError('Compose networks must be internal')
        for service in config['services'].values():
            if service.get('ports') or service.get('privileged') or not service.get('read_only'):
                raise RuntimeError('Unexpected unsafe Compose service')
        command(args + ['up', '-d', '--no-build', '--pull', 'never', 'egress', 'gateway'], timeout=50)
        for service, marker in [('egress', 'CLIPORA VERIFIED TLS EGRESS READY'),
                                ('gateway', 'CLIPORA E2E GATEWAY READY')]:
            for _ in range(40):
                if marker in command(args + ['logs', '--no-color', service]):
                    break
                time.sleep(.15)
            else:
                raise TimeoutError('Compose readiness timeout: ' + service)
        command(args + ['run', '-d', '--no-deps', '--pull', 'never', '--name', worker_name,
                        '--entrypoint', 'python3', 'worker', '-B', '/app/worker_verified.py'])
        code, stdout, stderr = collect_worker(worker_name, output, job, expected_bundle=bundles["worker"])
        if code or 'PASS: actual v8 worker MP4 with certificate and hostname verification' not in stdout:
            raise RuntimeError('Verified Compose worker failed: ' + stderr[-1600:])
        if size(output) > MAX_BYTES:
            raise RuntimeError('Offline output budget exceeded')
        files = list(output.rglob('*.mp4'))
        if len(files) != 1:
            raise RuntimeError('Expected one verified MP4')
        verify_mp4(files[0])
        shutil.copyfile(files[0], artifact)
    finally:
        # Project contains only this run's random names. Also removes a worker
        # container if docker-compose CLI is interrupted while it is running.
        subprocess.run(['docker', 'rm', '-f', worker_name], capture_output=True, text=True, timeout=15)
        command(args + ['down', '--remove-orphans', '--timeout', '2'], timeout=30)


def main():
    if os.environ.get('CLIPORA_V8_OFFLINE_BROWSER_TEST') != '1':
        raise SystemExit('Verified offline browser fixture disabled')
    for executable in ('docker', 'openssl', 'ffprobe'):
        if not shutil.which(executable):
            raise RuntimeError('Missing executable: ' + executable)
    for image in IMAGES:
        docker('image', 'inspect', image)
    compose = os.environ.get('CLIPORA_V8_USE_COMPOSE') == '1'
    with tempfile.TemporaryDirectory(prefix='clipora-browser-tls-') as tmp:
        root = Path(tmp)
        server, trust = certificates(root)
        artifact = root / 'browser.mp4'
        if compose:
            compose_fixture(server, trust, root, artifact)
        else:
            run_case('valid', server, trust, root, artifact_path=artifact)
        verify_mp4(artifact)
        # Publish only after worker/services/networks have been cleaned up.
        import re
        tag = os.environ.get('CLIPORA_OFFLINE_ARTIFACT_TAG', uuid.uuid4().hex[:10])
        if not re.fullmatch(r'[0-9a-f]{10}', tag):
            raise ValueError('Invalid reserved artifact tag')
        publish_artifact(artifact, STAGING, tag)
    print('CLIPORA_BROWSER_MP4_READY=' + tag, flush=True)
    print('CLIPORA_BROWSER_TLS_VERIFIED=1', flush=True)
    print('CLIPORA_BROWSER_RUNNER=' + ('compose' if compose else 'docker'), flush=True)
    print('V8 SECURE EGRESS REAL WORKER E2E PASSED (OFFLINE ONLY)', flush=True)


if __name__ == '__main__':
    main()
