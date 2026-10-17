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
FILES=('main.py','platforms.py','rate_limit.py','owned_jobs.py','owned_runner.py','owned_publish.py','owned_artifacts.py','owned_api.py','owned_entry.py','index.html','assets/app.js','assets/style.css')


def base_image():
    """Read the single source of truth for the pinned base image."""
    values={}
    for line in (HERE/'base_image.lock').read_text().splitlines():
        line=line.split('#',1)[0].strip()
        if not line:continue
        key,_,value=line.partition('=')
        values[key.strip()]=value.strip()
    if set(values)!={'image','id'}:raise ValueError('Unexpected base_image.lock keys')
    if not re.fullmatch(r'[a-z0-9][a-z0-9._/-]*(:[A-Za-z0-9._-]+)?',values['image']):
        raise ValueError('Invalid pinned base image reference')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}',values['id']):
        raise ValueError('Invalid pinned base image id')
    return values['image'],values['id']


def main():
    if len(sys.argv)!=2:raise SystemExit('Usage: build_image.py /absolute/wheelhouse')
    wheelhouse=Path(sys.argv[1])
    image,expected=base_image()
    result=subprocess.run(['docker','image','inspect',image,'--format','{{.Id}}'],
                          capture_output=True,text=True,check=True,timeout=15)
    if result.stdout.strip()!=expected:raise RuntimeError('Local base image changed; review it before building')
    from_lines=[line.split(None,1)[1].strip() for line in (HERE/'Dockerfile').read_text().splitlines()
                if line.upper().startswith('FROM ')]
    if from_lines!=[image]:raise RuntimeError('Dockerfile FROM does not match base_image.lock')
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
