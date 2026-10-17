"""Explicit runtime-only copies. Never mount the backend tree into a fixture worker."""
from pathlib import Path
import shutil

WORKER_FILES = (
    'real_download_worker_v8.py', 'download_worker.py', 'download_limits.py',
    'video_inspector.py', 'url_security.py', 'config.py',
    'clipora_v8_worker_integration/worker_proxy.py',
)
STAGE_FILES = ('server_stage.py', 'connect_policy.py', 'destination_policy.py',
               'dns_policy_v2.py', 'http_parser.py', 'dns_executor.py', 'ip_policy.py')


def copy_regular(base, relative, target):
    base = Path(base).resolve()
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid bundle source')
    source = base
    for part in relative.parts:
        source = source / part
        if source.is_symlink():
            raise ValueError('Bundle source symlink rejected')
    if not source.is_file():
        raise ValueError('Bundle source missing or not regular')
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o444)


def build_bundles(backend, package, fixture, stage, destination):
    destination = Path(destination)
    destination.mkdir(exist_ok=False)
    worker, services, policies = (destination / name for name in ('worker', 'services', 'policies'))
    for directory in (worker, services, policies):
        directory.mkdir()
    for name in WORKER_FILES:
        copy_regular(backend, name, worker / name)
    copy_regular(package, 'worker_verified.py', worker / 'worker_verified.py')
    copy_regular(fixture, 'gateway.py', services / 'gateway.py')
    copy_regular(fixture, 'fixtures/video.mp4', services / 'fixtures/video.mp4')
    copy_regular(package, 'egress_fixture.py', services / 'egress_fixture.py')
    for name in STAGE_FILES:
        copy_regular(stage, name, policies / name)
    return {'worker': worker, 'services': services, 'policies': policies}


def attest_worker_mounts(info, expected_bundle):
    mounts = info.get('Mounts', [])
    if any(m.get('Type') not in ('bind', 'tmpfs') for m in mounts):
        raise RuntimeError('Unexpected worker mount type')
    if any(m.get('Destination') not in ('/app', '/trust', '/tmp', '/output') for m in mounts):
        raise RuntimeError('Unexpected worker mount destination')
    binds = {m['Destination']:m for m in mounts if m.get('Type') == 'bind'}
    if set(binds) != {'/app', '/trust'} or any(m.get('RW') is not False for m in binds.values()):
        raise RuntimeError('Worker requires only readonly code and CA mounts')
    if Path(binds['/app']['Source']).resolve() != Path(expected_bundle).resolve():
        raise RuntimeError('Worker code mount is not the explicit bundle')
