"""Build local staging from a verified local base and predownloaded wheel files.

No downloads are performed. The temporary context contains only explicit web
sources and wheels whose SHA-256 matches requirements-web.lock.
"""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
EXPECTED_BASE='sha256:c0e3e82ca62c54eadf25137f4bc520bce1e42a73760a6655aa67c168b7f18432'
FILES=('main.py','platforms.py','rate_limit.py','owned_jobs.py','owned_runner.py','owned_publish.py','owned_artifacts.py','owned_api.py','owned_entry.py','index.html','assets/app.js','assets/style.css')


def main():
    if len(sys.argv)!=2:raise SystemExit('Usage: build_image.py /absolute/wheelhouse')
    wheelhouse=Path(sys.argv[1])
    result=subprocess.run(['docker','image','inspect','clipora-worker:v8-dns','--format','{{.Id}}'],
                          capture_output=True,text=True,check=True,timeout=15)
    if result.stdout.strip()!=EXPECTED_BASE:raise RuntimeError('Local base image changed; review it before building')
    with tempfile.TemporaryDirectory(prefix='clipora-web-build-') as tmp:
        root=Path(tmp);(root/'wheels').mkdir()
        for line in (HERE/'requirements-web.lock').read_text().splitlines():
            match=re.fullmatch(r'([a-z0-9_]+)==([0-9.]+) --hash=sha256:([a-f0-9]{64})',line)
            if not match:raise ValueError('Unexpected lock format')
            name,version,digest=match.groups()
            wheel=wheelhouse/f'{name}-{version}-py3-none-any.whl'
            if wheel.is_symlink() or hashlib.sha256(wheel.read_bytes()).hexdigest()!=digest:
                raise ValueError('Wheel hash mismatch')
            shutil.copyfile(wheel,root/'wheels'/wheel.name)
        for name in FILES:
            source=HERE/name
            if source.is_symlink():raise ValueError('Source symlink rejected')
            target=root/'clipora_v8_web'/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
        for name in ('job_store.py','artifact_delivery.py'):
            source=HERE.parent/'clipora_v8_browser_real_mp4'/name
            if source.is_symlink():raise ValueError('Shared source symlink rejected')
            target=root/'clipora_v8_browser_real_mp4'/name
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        for name in ('Dockerfile','requirements-web.lock'):shutil.copyfile(HERE/name,root/name)
        subprocess.run(['docker','build','--pull=false','--network=none','-t','clipora-web:v8-staging',str(root)],check=True,timeout=120)


if __name__=='__main__':main()
