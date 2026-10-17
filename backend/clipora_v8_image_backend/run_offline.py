"""Real PNG/JPEG/WebP decoding in a disposable networkless Docker worker."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import re
import signal
import struct
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
import zlib

BACKEND=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(BACKEND))
EXPECTED='sha256:c0e3e82ca62c54eadf25137f4bc520bce1e42a73760a6655aa67c168b7f18432'


def command(args,timeout=15,*,input=None):
    result=subprocess.run(args,capture_output=True,timeout=timeout,input=input)
    if result.returncode:raise RuntimeError('Offline image fixture command failed')
    return result.stdout


def png(*,invalid=False):
    def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',16,16,8,2,0,0,0))+chunk(b'IDAT',b'invalid-zlib-payload' if invalid else zlib.compress((b'\0'+b'\x62\x55\xea'*16)*16))+chunk(b'IEND',b'')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path);parser.add_argument('--artifact',type=Path);parser.add_argument('--resource-owner');parser.add_argument('--interactive-hold',action='store_true');args=parser.parse_args()
    if args.resource_owner is not None and not re.fullmatch('[0-9a-f]{32}',args.resource_owner):parser.error('Invalid execution owner')
    def terminate(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,terminate)
    name='clipora-image-'+uuid4().hex[:10];owner=args.resource_owner or uuid4().hex;identity=None
    label='clipora.three.kernel' if args.resource_owner else 'clipora.image.fixture'
    before=set(command(['docker','ps','-aq','--no-trunc']).decode().split())
    if command(['docker','image','inspect','clipora-worker:v8-dns','--format','{{.Id}}']).decode().strip()!=EXPECTED:
        raise RuntimeError('Worker base changed; review required')
    try:
        with tempfile.TemporaryDirectory(prefix='clipora-image-fixture-') as temporary:
            root=Path(temporary).resolve();root.chmod(0o755)
            code=root/'code';package=code/'clipora_v8_image_backend';package.mkdir(parents=True)
            source=root/'images';source.mkdir();(source/'image-01.png').write_bytes(png())
            for extension in ('jpg','webp'):
                converted=command(['docker','run','-i','--rm','--pull','never','--label',label+'='+owner,
                    '--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                    '--user','10001:10001','--memory','128m','--cpus','1','--pids-limit','32','--entrypoint','ffmpeg',
                    'clipora-worker:v8-dns','-nostdin','-hide_banner','-loglevel','error','-threads','1','-filter_threads','1',
                    '-protocol_whitelist','file,pipe','-i','pipe:0','-frames:v','1','-threads','1',
                    '-c:v','mjpeg' if extension=='jpg' else 'libwebp','-f','image2pipe','pipe:1'],input=png())
                (source/('image-'+('02' if extension=='jpg' else '03')+'.'+extension)).write_bytes(converted)
            for filename in ('formats.py','archive.py','worker.py'):
                shutil.copyfile(BACKEND/'clipora_v8_image_backend'/filename,package/filename);(package/filename).chmod(0o444)
            rejected=code/'rejected';rejected.mkdir();(rejected/'image-01.png').write_bytes(png(invalid=True));(rejected/'image-01.png').chmod(0o444);rejected.chmod(0o555)
            package.chmod(0o555);code.chmod(0o555)
            for path in source.iterdir():path.chmod(0o444)
            source.chmod(0o555)
            script="""import json,os,threading
from pathlib import Path
from clipora_v8_image_backend.worker import prepare
s=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
assert os.getuid()!=0 and s['NoNewPrivs'].strip()=='1'
assert all(int(s[key],16)==0 for key in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
try:prepare('/app/rejected','/output/rejected.zip')
except ValueError:pass
else:raise AssertionError('Corrupt image was accepted')
assert not Path('/output/rejected.zip').exists()
print(json.dumps(prepare('/input','/output/album.zip')),flush=True)
threading.Event().wait(120)
"""
            identity=command(['docker','create','--pull','never','--name',name,'--label',label+'='+owner,
                '--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                '--user',f'{os.getuid()}:{os.getgid()}','--memory','384m','--cpus','1','--pids-limit','64',
                '--tmpfs',f'/output:rw,nosuid,nodev,noexec,size=64m,uid={os.getuid()},gid={os.getgid()},mode=0700',
                '--mount',f'type=bind,source={code},target=/app,readonly','--mount',f'type=bind,source={source},target=/input,readonly',
                '--workdir','/app','--entrypoint','python3','clipora-worker:v8-dns','-B','-c',script]).decode().strip()
            info=json.loads(command(['docker','inspect',identity]))[0];host=info['HostConfig']
            assert host['NetworkMode']=='none' and host['ReadonlyRootfs'] and host['CapDrop']==['ALL'] and not host.get('CapAdd')
            assert not host['Privileged'] and not host.get('PortBindings')
            binds=[mount for mount in info['Mounts'] if mount['Type']=='bind']
            assert {mount['Destination'] for mount in binds}=={'/app','/input'} and all(mount['RW'] is False for mount in binds)
            assert 'size=64m' in host['Tmpfs']['/output']
            command(['docker','start',identity]);result=None
            for _ in range(100):
                logs=command(['docker','logs',identity]).decode()
                if logs.strip():result=json.loads(logs);break
                if not json.loads(command(['docker','inspect',identity]))[0]['State']['Running']:raise RuntimeError('Image worker failed')
                time.sleep(.1)
            if result is None:raise TimeoutError('Image worker timeout')
            assert result['all_images_decoded'] and result['image_count']==3
            if args.interactive_hold:time.sleep(120)
            reader="import os,stat,sys;fd=os.open('/output/album.zip',os.O_RDONLY|os.O_NOFOLLOW);s=os.fstat(fd);assert stat.S_ISREG(s.st_mode) and 64<=s.st_size<=50*1024*1024+32768;data=os.read(fd,s.st_size+1);assert len(data)==s.st_size;sys.stdout.buffer.write(data);os.close(fd)"
            data=command(['docker','exec',identity,'python3','-B','-c',reader])
            assert hashlib.sha256(data).hexdigest()==result['archive_sha256']
            output=root/'album.zip';output.write_bytes(data)
            from fastapi.testclient import TestClient
            from clipora_v8_web.owned_api import create_owned_app
            from clipora_v8_image_backend.delivery import attach_album_routes
            from clipora_v8_image_backend.jobs import create_fixture_job
            from clipora_v8_image_backend.publish import publish_album
            origin='http://127.0.0.1:8090';app=create_owned_app(origin,root/'state',root/'videos');attach_album_routes(app,root/'albums')
            with TestClient(app,base_url=origin) as client:
                client.post('/api/v8/session',headers={'Origin':origin});token=client.cookies['clipora_session'];store=app.state.owned_jobs
                job=create_fixture_job(store,token,'a'*32);store.claim('fixture-runner')
                publish_album(store,job['job_id'],'fixture-runner',output,root/'albums');base='/api/v8/jobs/'+job['job_id']
                manifest=client.get(base+'/images');assert manifest.status_code==200
                for index,path in enumerate(sorted(source.iterdir()),1):
                    response=client.get(base+'/images/'+str(index));assert response.status_code==200 and response.content==path.read_bytes()
                    assert client.head(base+'/images/'+str(index)).content==b''
                assert client.get(base+'/album.zip').content==data
                response=client.get(base+'/images/1',headers={'Range':'bytes=0-7'});assert response.status_code==206 and response.content==png()[:8]
                stranger=TestClient(app,base_url=origin)
                for suffix in ('/images','/images/1','/album.zip'):assert stranger.get(base+suffix).status_code==404
            report={'actual_FFmpeg_decoded':['PNG','JPEG','WebP'],'worker_network':'none','readonly_nonroot_cap_drop_all':True,
                    'worker_workspace_limit_bytes':64*1024*1024,'original_image_bytes_preserved':True,'corrupt_image_payload_rejected':True,'ordered_manifest_and_hashes_verified':True,
                    'owned_manifest_image_ZIP_HTTP_verified':True,'HEAD_and_Range_verified':True,'foreign_owner_rejected':True,
                    'public_extractor_implemented':False,'public_downloads_enabled':False}
    finally:
        for container in command(['docker','ps','-aq','--no-trunc','--filter','label=clipora.image.fixture='+owner]).decode().split():
            info=json.loads(command(['docker','inspect',container]))[0]
            if info['Config']['Labels'].get(label)!=owner:raise RuntimeError('Fixture cleanup identity mismatch')
            command(['docker','rm','-f',container])
    assert not command(['docker','ps','-aq','--filter','label=clipora.image.fixture='+owner]).strip()
    if args.resource_owner is None:assert before<=set(command(['docker','ps','-aq','--no-trunc']).decode().split())
    report['owned_container_removed']=True;report['preexisting_containers_preserved']=True if args.resource_owner is None else None
    if args.artifact:
        target=args.artifact.absolute()
        if any(path.is_symlink() for path in (target.parent,*target.parent.parents)):raise ValueError('Symlinked export directory')
        fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        except BaseException:target.unlink(missing_ok=True);raise
    if args.report:
        with args.report.open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
