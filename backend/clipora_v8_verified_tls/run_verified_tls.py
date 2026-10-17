"""Offline-only Docker TLS regression. Does not modify existing containers or trust stores."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

from bounded_worker import collect_worker, workspace_mount
from owned_resources import label_args
from sandbox_bundle import build_bundles

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
FIXTURE = BACKEND / 'clipora_v8_real_guarded_e2e'
STAGE = BACKEND / 'clipora_v8_secure_egress_stage'
IMAGES = ('clipora-worker:v8-dns', 'clipora-gateway:v8-test', 'clipora-dns-wire:v8-test')


def command(args, timeout=30):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'{args[:3]} failed: {p.stderr[-1200:]}')
    return p.stdout.strip()


def docker(*args, timeout=30):
    return command(['docker', *args], timeout)


def certificates(root):
    server, trust = root/'server', root/'trust'
    server.mkdir(); trust.mkdir(); (trust/'empty').mkdir()
    config = root/'openssl.cnf'
    config.write_text('[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=ca\n[dn]\nCN=Clipora ephemeral offline CA\n[ca]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n')
    for name in ('ca', 'other'):
        command(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-sha256','-days','1','-config',str(config),'-keyout',str(root/(name+'.key')),'-out',str(trust/(name+'.pem'))])
    for case, hostname in [('valid','example.com'),('wrong-host','wrong.example.com')]:
        ext=root/(case+'.ext')
        ext.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:'+hostname+'\n')
        command(['openssl','req','-new','-newkey','rsa:2048','-nodes','-sha256','-subj','/CN='+hostname,'-keyout',str(server/(case+'.key')),'-out',str(root/(case+'.csr'))])
        command(['openssl','x509','-req','-sha256','-days','1','-in',str(root/(case+'.csr')),'-CA',str(trust/'ca.pem'),'-CAkey',str(root/'ca.key'),'-CAcreateserial','-extfile',str(ext),'-out',str(server/(case+'.pem'))])
    return server, trust


def ready(name, marker):
    for _ in range(40):
        if marker in docker('logs',name): return
        state=json.loads(docker('inspect',name))[0]['State']
        if not state['Running']: raise RuntimeError('Fixture stopped: '+name)
        time.sleep(.15)
    raise TimeoutError('Fixture readiness timeout: '+name)


def ip(name, network):
    return json.loads(docker('inspect',name))[0]['NetworkSettings']['Networks'][network]['IPAddress']


def size(root):
    total=0
    for p in root.rglob('*'):
        if p.is_symlink(): raise RuntimeError('Unexpected output symlink')
        if p.is_file(): total+=p.stat().st_size
    return total


def run_case(case, server, trust, root, *, artifact_path=None):
    token=uuid.uuid4().hex[:10]
    nw, ne='clipora-vtls-w-'+token,'clipora-vtls-e-'+token
    eg,gw,wr=('clipora-vtls-'+x+'-'+token for x in ('eg','gw','wr'))
    created=[]; cleanup_errors=[]
    output=root/('output-'+case);output.mkdir()
    bundles=build_bundles(BACKEND,HERE,FIXTURE,STAGE,root/('bundles-'+case))
    owner=f'{os.getuid()}:{os.getgid()}'
    base=[*label_args(),'--pull','never','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','256m','--cpus','1','--pids-limit','96','--user',owner]
    try:
        for network in (nw,ne):
            docker('network','create','--internal',*label_args(),network);created.append(('network',network))
            if not json.loads(docker('network','inspect',network))[0]['Internal']: raise RuntimeError('Network must remain internal')
        server_case='wrong-host' if case=='wrong-host' else 'valid'
        docker('run','-d','--name',eg,'--network',ne,*base,
               '-e','CLIPORA_E2E_OFFLINE_ONLY=1','-e','CLIPORA_TLS_CASE='+server_case,
               '-e','CLIPORA_HTTP_CASE='+(case if case.startswith('redirect-') else 'valid'),'-e','PYTHONPATH=/stage:/fixture',
               '-v',f'{bundles["services"]}:/fixture:ro','-v',f'{bundles["policies"]}:/stage:ro','-v',f'{server}:/tls:ro',
               IMAGES[2],'python3','-B','-u','/fixture/egress_fixture.py')
        created.append(('container',eg));ready(eg,'CLIPORA VERIFIED TLS EGRESS READY')
        docker('run','-d','--name',gw,'--network',ne,*base,'-e','EGRESS_IP='+ip(eg,ne),'-v',f'{bundles["services"]}:/fixture:ro',IMAGES[1],'python3','-B','-u','/fixture/gateway.py')
        created.append(('container',gw));ready(gw,'CLIPORA E2E GATEWAY READY')
        docker('network','connect',nw,gw)
        job=uuid.uuid4().hex
        ca='other.pem' if case=='untrusted-ca' else 'ca.pem'
        cmd=['docker','run','-d','--name',wr,'--network',nw,*base,
             '--tmpfs','/tmp:rw,nosuid,nodev,size=32m',
             '-e','PYTHONPATH=/app','-e','CLIPORA_VERIFIED_TLS_OFFLINE_ONLY=1',
             '-e','CLIPORA_HOLD_VERIFIED_OUTPUT=1','--tmpfs',workspace_mount(),
             '-e','CLIPORA_V8_PROXY_URL=http://'+ip(gw,nw)+':8888',
             '-e','CLIPORA_TEST_DOWNLOAD_DIR=/output','-e','CLIPORA_TEST_JOB_ID='+job,
             '-e','SSL_CERT_FILE=/trust/'+ca,'-e','SSL_CERT_DIR=/trust/empty',
             '-v',f'{bundles["worker"]}:/app:ro','-v',f'{trust}:/trust:ro',
             '-w','/app','--entrypoint','python3',IMAGES[0],'-B','/app/worker_verified.py']
        command(cmd)
        code,stdout,stderr=collect_worker(wr,output,job,expected_bundle=bundles["worker"])
        files=list(output.rglob('*.mp4'))
        if case in ('valid', 'redirect-safe'):
            if code or 'PASS: actual v8 worker MP4' not in stdout or len(files)!=1:
                raise RuntimeError('Verified worker failed: '+stderr[-2200:]+' '+stdout[-600:])
            metadata=json.loads(command(['ffprobe','-v','error','-show_entries','stream=codec_name,codec_type,pix_fmt','-of','json',str(files[0])]))
            if not any(s.get('codec_name')=='h264' and s.get('pix_fmt')=='yuv420p' for s in metadata['streams']): raise RuntimeError('Output codec mismatch')
            result={'case':case,'passed':True,'mp4_bytes':files[0].stat().st_size,'verified_h264':True}
            if artifact_path is not None:
                shutil.copyfile(files[0], artifact_path)
        elif case.startswith('redirect-'):
            error=stderr.lower()
            if case=='redirect-loop':
                expected=('redirect loop' in error or 'infinite loop' in error or 'too many redirects' in error)
            else:
                expected='403' in error and 'forbidden' in error
            if code==0 or files or not expected:
                raise RuntimeError('Expected redirect rejection missing: '+stderr[-2200:])
            result={'case':case,'passed':True,'redirect_rejected':True,'mp4_created':False}
        else:
            error=stderr.lower()
            if code==0 or files or not ('certificate_verify_failed' in error or 'certificate verify failed' in error):
                raise RuntimeError('Expected certificate rejection missing: '+stderr[-2200:])
            if case=='wrong-host' and not any(x in error for x in ('hostname mismatch','not valid for','doesn\'t match')):
                raise RuntimeError('Hostname rejection not confirmed: '+stderr[-1800:])
            result={'case':case,'passed':True,'certificate_rejected':True,'mp4_created':False}
        print('PASS: '+case,flush=True)
        return result
    finally:
        # Only this run's random names are ever removed.
        subprocess.run(['docker','rm','-f',wr],capture_output=True,text=True,timeout=15)
        for kind,name in reversed(created):
            args=['docker','rm','-f',name] if kind=='container' else ['docker','network','rm',name]
            p=subprocess.run(args,capture_output=True,text=True,timeout=15)
            if p.returncode: cleanup_errors.append(name)
        if cleanup_errors: raise RuntimeError('Cleanup incomplete: '+', '.join(cleanup_errors))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',type=Path)
    parser.add_argument('--redirects',action='store_true',help='Include synthetic redirect boundary cases')
    args=parser.parse_args()
    for executable in ('docker','openssl','ffprobe'):
        if not shutil.which(executable): raise RuntimeError('Missing executable: '+executable)
    for image in IMAGES: docker('image','inspect',image)
    with tempfile.TemporaryDirectory(prefix='clipora-verified-tls-') as tmp:
        root=Path(tmp);server,trust=certificates(root)
        cases=['valid','wrong-host','untrusted-ca']
        if args.redirects:
            cases.extend(['redirect-safe','redirect-private','redirect-other-host','redirect-http','redirect-loop'])
        results=[run_case(case,server,trust,root) for case in cases]
    report={'offline_only':True,'public_egress_enabled':False,'certificate_verification':True,'cases':results,'temporary_certificates_removed':True}
    if args.report: args.report.write_text(json.dumps(report,indent=2)+'\n')
    print('VERIFIED TLS OFFLINE DOCKER SUITE PASSED',flush=True)

if __name__=='__main__':main()
