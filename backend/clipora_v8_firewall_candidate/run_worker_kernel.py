"""Actual v8 worker through fixture gateway, DNS, broker, kernel and TLS.

Worker and controller share a network=none namespace. This deliberately does
not claim three-tier Docker network isolation or production acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

HERE=Path(__file__).resolve().parent
BACKEND=HERE.parent
sys.path.insert(0,str(BACKEND/'clipora_v8_verified_tls'))
from run_verified_tls import certificates
from sandbox_bundle import WORKER_FILES,copy_regular
from bounded_worker import collect_worker,workspace_mount


def docker(*args):
    p=subprocess.run(['docker',*args],capture_output=True,text=True,timeout=30)
    if p.returncode:raise RuntimeError(p.stderr[-2000:])
    return p.stdout.strip()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',type=Path)
    parser.add_argument('--case',choices=('valid','wrong-host','untrusted-ca'),default='valid')
    args=parser.parse_args()
    token=uuid4().hex;eg='clipora-worker-kernel-'+token[:10];worker=eg+'-worker'
    owned=[]
    before=set(docker('ps','-aq','--no-trunc').split())
    def info(name):return json.loads(docker('inspect',name))[0]
    with tempfile.TemporaryDirectory(prefix='clipora-worker-kernel-') as tmp:
        root=Path(tmp);service=root/'service';service.mkdir();code=root/'worker';code.mkdir();out=root/'output';out.mkdir()
        server,trust=certificates(service)
        (service/'worker-mode').touch();(service/'tls-case.txt').write_text(args.case)
        files=('kernel_tls_fixture.py','worker_kernel_service.py','integrated_probe.py',
               'numeric_dial.py','binding.py','bootstrap.py','policy.py','dns_snapshot.py','connect_relay.py')
        for name in files:copy_regular(HERE,name,service/'clipora_v8_firewall_candidate'/name)
        for name in ('connect_policy.py','ip_policy.py','http_parser.py'):
            copy_regular(BACKEND/'clipora_v8_secure_egress_stage',name,service/'clipora_v8_secure_egress_stage'/name)
        copy_regular(BACKEND/'clipora_v8_real_guarded_e2e','gateway.py',service/'gateway.py')
        copy_regular(BACKEND/'clipora_v8_real_guarded_e2e','fixtures/video.mp4',service/'video.mp4')
        for name in WORKER_FILES:copy_regular(BACKEND,name,code/name)
        copy_regular(BACKEND/'clipora_v8_verified_tls','worker_verified.py',code/'worker_verified.py')
        try:
            docker('create','--pull','never','--name',eg,'--label','clipora.worker.kernel='+token,
                   '--network','none','--read-only','--cap-drop','ALL',
                   '--cap-add','NET_ADMIN','--cap-add','SETPCAP','--cap-add','SETUID','--cap-add','SETGID',
                   '--security-opt','no-new-privileges','--user','0:0','--memory','192m','--cpus','1','--pids-limit','64',
                   '-e','CLIPORA_NUMERIC_OFFLINE_TEST=1','--mount',f'type=bind,source={service},target=/fixture,readonly',
                   '--workdir','/fixture','--entrypoint','python3','clipora-dns-wire:v8-test','-B','-u','-c',
                   'from clipora_v8_firewall_candidate.kernel_tls_fixture import parent;parent()')
            owned.append(eg)
            assert info(eg)['HostConfig']['NetworkMode']=='none'
            docker('start',eg)
            for _ in range(40):
                if 'CLIPORA KERNEL WORKER SERVICE READY' in docker('logs',eg):break
                if not info(eg)['State']['Running']:raise RuntimeError('Service exited before readiness')
                time.sleep(.1)
            else:raise TimeoutError('Service readiness deadline')
            job=uuid4().hex
            docker('create','--pull','never','--name',worker,'--label','clipora.worker.kernel='+token,
                   '--network','container:'+eg,'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                   '--user',str(os.getuid())+':'+str(os.getgid()),
                   '--memory','384m','--cpus','1','--pids-limit','64','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=32m',
                   '--tmpfs',workspace_mount(),'-e','PYTHONPATH=/app','-e','CLIPORA_VERIFIED_TLS_OFFLINE_ONLY=1',
                   '-e','CLIPORA_HOLD_VERIFIED_OUTPUT=1','-e','CLIPORA_V8_PROXY_URL=http://127.0.0.2:8888',
                   '-e','CLIPORA_TEST_DOWNLOAD_DIR=/output','-e','CLIPORA_TEST_JOB_ID='+job,
                   '-e','SSL_CERT_FILE=/trust/'+('other.pem' if args.case=='untrusted-ca' else 'ca.pem'),'-e','SSL_CERT_DIR=/trust/empty',
                   '--mount',f'type=bind,source={code},target=/app,readonly',
                   '--mount',f'type=bind,source={trust},target=/trust,readonly','--workdir','/app',
                   '--entrypoint','python3','clipora-worker:v8-dns','-B','/app/worker_verified.py')
            owned.append(worker)
            assert info(worker)['HostConfig']['NetworkMode']=='container:'+info(eg)['Id']
            docker('start',worker)
            result,stdout,stderr=collect_worker(worker,out,job,timeout=20,expected_bundle=code)
            if args.case=='valid':
                if result:raise RuntimeError('Actual worker failed: '+stderr[-2000:])
                metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
                    'stream=codec_name,pix_fmt','-of','json',str(out/'video.mp4')],text=True,timeout=10))
                assert any(s.get('codec_name')=='h264' and s.get('pix_fmt')=='yuv420p' for s in metadata['streams'])
            else:
                assert result!=0 and not list(out.rglob('*.mp4'))
                message=stderr.lower()
                assert 'certificate_verify_failed' in message or 'certificate verify failed' in message
                if args.case=='wrong-host':
                    assert any(part in message for part in ('hostname mismatch','not valid for',"doesn't match"))
            for _ in range(30):
                rules=docker('exec',eg,'iptables-save')
                if '--dport 443' not in rules:break
                time.sleep(.1)
            else:raise RuntimeError('Lease rules remained after worker completion')
            probe='import socket;s=socket.socket();s.settimeout(.2)\ntry:s.connect(("8.8.8.8",443))\nexcept TimeoutError:print("BLOCKED")\nelse:raise AssertionError("Unexpected direct socket")'
            probe_name=worker+'-probe'
            docker('create','--pull','never','--name',probe_name,'--label','clipora.worker.kernel='+token,
                   '--network','container:'+eg,'--read-only','--cap-drop','ALL',
                   '--security-opt','no-new-privileges','--user','65534:65534',
                   '--memory','64m','--cpus','1','--pids-limit','16','--entrypoint','python3',
                   'clipora-worker:v8-dns','-B','-c',probe)
            owned.append(probe_name)
            docker('start',probe_name)
            assert docker('wait',probe_name)=='0'
            assert docker('logs',probe_name)=='BLOCKED'
            report={'case':args.case,'actual_v8_worker':True,'actual_ytdlp':True,'ffmpeg_output_verified':args.case=='valid','fixture_gateway':True,
                    'real_dns_broker_kernel_CONNECT_TLS':True,'certificate_verification':True,
                    'mp4_h264_yuv420p_verified':args.case=='valid',
                    'certificate_rejected':args.case!='valid',
                    'mp4_bytes':(out/'video.mp4').stat().st_size if args.case=='valid' else 0,
                    'lease_rules_removed_after_completion':True,'direct_socket_blocked_after_completion':True,
                    'network_none_namespace_shared':True,'three_tier_network_isolation_tested':False,
                    'worker_tmpfs_bytes':64*1024*1024,'public_downloads_enabled':False,'offline_fixture_only':True}
        finally:
            for name in reversed(owned):
                assert info(name)['Config']['Labels'].get('clipora.worker.kernel')==token
                docker('rm','-f',name)
        assert before<=set(docker('ps','-aq','--no-trunc').split())
    report['owned_containers_removed']=True
    report['preexisting_containers_preserved']=True
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
