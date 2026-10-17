"""Actual offline worker and kernel broker across two internal Docker networks."""
import argparse
import asyncio
import json
import ipaddress
import os
import re
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

HERE=Path(__file__).resolve().parent;BACKEND=HERE.parent
sys.path.insert(0,str(BACKEND))
sys.path.insert(0,str(BACKEND/'clipora_v8_verified_tls'))
from run_verified_tls import certificates
from sandbox_bundle import WORKER_FILES,copy_regular
from bounded_worker import collect_worker,workspace_mount


def docker(*args):
    p=subprocess.run(['docker',*args],capture_output=True,text=True,timeout=30)
    if p.returncode:raise RuntimeError(p.stderr[-2500:])
    return p.stdout.strip()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',type=Path)
    parser.add_argument('--artifact',type=Path,help='Exclusive export path for a verified offline MP4')
    parser.add_argument('--resource-owner',help='Explicit recovery label, 32 lowercase hex characters')
    parser.add_argument('--interactive-hold',action='store_true',help='Keep the fixture held until its runner cancels it')
    parser.add_argument('--mutual',action='store_true',help='Require gateway/egress mutual TLS')
    parser.add_argument('--cancel-running',action='store_true',help='Offline owned-job cancellation while worker is held')
    parser.add_argument('--case',choices=('valid','wrong-host','untrusted-ca'),default='valid')
    args=parser.parse_args()
    if args.cancel_running and args.case!='valid':parser.error('Cancellation fixture requires the valid TLS case')
    if args.resource_owner is not None and re.fullmatch('[0-9a-f]{32}',args.resource_owner) is None:
        parser.error('Invalid resource owner')
    if args.artifact is not None and (args.case!='valid' or args.cancel_running):
        parser.error('Artifact export requires valid non-cancelled fixture')
    def interrupted(signum,frame):raise KeyboardInterrupt('Local runner stopped')
    signal.signal(signal.SIGTERM,interrupted)
    token=args.resource_owner or uuid4().hex;prefix='clipora-three-kernel-'+token[:8]
    eg,gw,worker,attacker=(prefix+'-'+s for s in ('eg','gw','worker','attacker'))
    nw,ne=(prefix+'-'+s for s in ('worker-net','egress-net'))
    containers=[];networks=[];label='clipora.three.kernel='+token
    before=set(docker('ps','-aq','--no-trunc').split())
    def info(name):return json.loads(docker('inspect',name))[0]
    def ip(name,net):return info(name)['NetworkSettings']['Networks'][net]['IPAddress']
    with tempfile.TemporaryDirectory(prefix='clipora-three-kernel-') as tmp:
        root=Path(tmp).resolve();service=root/'service';code=root/'worker';gate=root/'gateway';out=root/'out'
        for d in (service,code,gate,out):d.mkdir()
        server,trust=certificates(service)
        (service/'worker-mode').touch();(service/'tls-case.txt').write_text(args.case)
        names=('kernel_tls_fixture.py','worker_kernel_service.py','integrated_probe.py','numeric_dial.py',
               'binding.py','bootstrap.py','policy.py','dns_snapshot.py','connect_relay.py','three_tier_fixture.py')
        for name in names:copy_regular(HERE,name,service/'clipora_v8_firewall_candidate'/name)
        for name in ('connect_policy.py','ip_policy.py','http_parser.py'):
            copy_regular(BACKEND/'clipora_v8_secure_egress_stage',name,service/'clipora_v8_secure_egress_stage'/name)
        for directory in (service,gate):copy_regular(BACKEND/'clipora_v8_real_guarded_e2e','gateway.py',directory/'gateway.py')
        copy_regular(BACKEND/'clipora_v8_real_guarded_e2e','fixtures/video.mp4',service/'video.mp4')
        if args.mutual:
            from fixture_identity import identities
            identities(service);(service/'mtls-mode').touch()
            for name in ('mutual_gateway.py','connect_relay.py'):
                copy_regular(HERE,name,gate/'clipora_v8_firewall_candidate'/name)
            for name in ('connect_policy.py','http_parser.py'):
                copy_regular(BACKEND/'clipora_v8_secure_egress_stage',name,gate/'clipora_v8_secure_egress_stage'/name)
            for name in ('gateway.pem','gateway.key','other-client.pem','other-client.key'):
                copy_regular(service/'server',name,gate/name)
            copy_regular(trust,'ca.pem',gate/'ca.pem')
            (gate/'mutual_entry.py').write_text('''import asyncio,os,ssl
from clipora_v8_firewall_candidate.mutual_gateway import MutualGateway
async def main():
 ctx=ssl.create_default_context(cafile='/fixture/ca.pem')
 ctx.minimum_version=ssl.TLSVersion.TLSv1_2
 ctx.load_cert_chain('/fixture/gateway.pem','/fixture/gateway.key')
 gateway=MutualGateway(os.environ['EGRESS_IP'],ctx,['example.com'])
 server=await asyncio.start_server(gateway.handle,'0.0.0.0',8888,limit=8192)
 print('CLIPORA E2E GATEWAY READY',flush=True)
 async with server:await server.serve_forever()
asyncio.run(main())
''')
        from fixture_identity import remove_authority_material
        remove_authority_material(service)
        if args.mutual:
            for leaf in ('gateway','other-client'):
                for suffix in ('.key','.pem'):(server/(leaf+suffix)).unlink()
        for name in WORKER_FILES:copy_regular(BACKEND,name,code/name)
        copy_regular(BACKEND/'clipora_v8_verified_tls','worker_verified.py',code/'worker_verified.py')
        base=['--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','192m','--cpus','1','--pids-limit','64']
        try:
            for net in (nw,ne):
                docker('network','create','--internal','--label',label,net);networks.append(net)
                assert json.loads(docker('network','inspect',net))[0]['Internal'] is True
            subnet=json.loads(docker('network','inspect',ne))[0]['IPAM']['Config'][0]['Subnet']
            allocated=ipaddress.IPv4Network(subnet)
            eg_ip=str(allocated.network_address+2);gw_eg_ip=str(allocated.network_address+3)
            docker('create','--pull','never','--name',eg,'--label',label,'--network',ne,'--ip',eg_ip,*base,
                '--cap-add','NET_ADMIN','--cap-add','SETPCAP','--cap-add','SETUID','--cap-add','SETGID','--user','0:0',
                '--tmpfs','/control:rw,noexec,nosuid,nodev,size=1m,uid=65534,gid=65534,mode=0700',
                '-e','CLIPORA_THREE_TIER_OFFLINE_TEST=1','--mount',f'type=bind,source={service},target=/fixture,readonly',
                '--workdir','/fixture','--entrypoint','python3','clipora-dns-wire:v8-test','-B','-u','-m',
                'clipora_v8_firewall_candidate.three_tier_fixture');containers.append(eg)
            docker('create','--pull','never','--name',gw,'--label',label,'--network',ne,'--ip',gw_eg_ip,*base,'--user','65534:65534',
                '-e','EGRESS_IP='+eg_ip,'--mount',f'type=bind,source={gate},target=/fixture,readonly',
                '--workdir','/fixture','--entrypoint','python3','clipora-gateway:v8-test','-B','-u','mutual_entry.py' if args.mutual else 'gateway.py');containers.append(gw)
            docker('network','connect',nw,gw)
            assert set(info(eg)['NetworkSettings']['Networks'])=={ne}
            assert set(info(gw)['NetworkSettings']['Networks'])=={nw,ne}
            subnet=json.loads(docker('network','inspect',ne))[0]['IPAM']['Config'][0]['Subnet']
            (service/'three-tier.json').write_text(json.dumps({'mode':'offline-three-tier','subnet':subnet,
                'gateway_ip':gw_eg_ip,'egress_ip':eg_ip}))
            docker('start',eg)
            for _ in range(50):
                if 'CLIPORA KERNEL WORKER SERVICE READY' in docker('logs',eg):break
                if not info(eg)['State']['Running']:
                    p=subprocess.run(['docker','logs',eg],capture_output=True,text=True)
                    raise RuntimeError('Service startup failed: '+p.stderr[-2500:])
                time.sleep(.1)
            else:raise TimeoutError('Service readiness')
            docker('start',gw)
            for _ in range(30):
                if 'CLIPORA E2E GATEWAY READY' in docker('logs',gw):break
                time.sleep(.1)
            else:raise TimeoutError('Gateway readiness')
            owner_store=None
            if args.cancel_running:
                from clipora_v8_web.owned_jobs import OwnedJobs
                owner_store=OwnedJobs(root/'owner-state')
                browser_token=owner_store.issue_session()
                owner_job=owner_store.create_owned(browser_token,'https://youtu.be/fixture','a'*32)
                execution_owner=uuid4().hex
                assert owner_store.claim(execution_owner)['job_id']==owner_job['job_id']
                job=owner_job['job_id']
            else:job=uuid4().hex
            docker('create','--pull','never','--name',worker,'--label',label,'--label','clipora.owned.job='+job,'--network',nw,*base,
                '--user',str(os.getuid())+':'+str(os.getgid()),'--dns','127.0.0.1',
                '--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=32m','--tmpfs',workspace_mount(),
                '-e','PYTHONPATH=/app','-e','CLIPORA_VERIFIED_TLS_OFFLINE_ONLY=1','-e','CLIPORA_HOLD_VERIFIED_OUTPUT=1',
                '-e','CLIPORA_V8_PROXY_URL=http://'+ip(gw,nw)+':8888','-e','CLIPORA_TEST_DOWNLOAD_DIR=/output',
                '-e','CLIPORA_TEST_JOB_ID='+job,'-e','SSL_CERT_FILE=/trust/'+('other.pem' if args.case=='untrusted-ca' else 'ca.pem'),
                '-e','SSL_CERT_DIR=/trust/empty','--mount',f'type=bind,source={code},target=/app,readonly',
                '--mount',f'type=bind,source={trust},target=/trust,readonly','--workdir','/app','--entrypoint','python3',
                'clipora-worker:v8-dns','-B','/app/worker_verified.py');containers.append(worker)
            assert set(info(worker)['NetworkSettings']['Networks'])=={nw}
            docker('start',worker)
            bypass_tested=False
            if args.case=='valid':
                for _ in range(60):
                    if '--dport 443' in docker('exec',eg,'iptables-save'):break
                    if not info(worker)['State']['Running']:raise RuntimeError('Worker exited before active lease')
                    time.sleep(.1)
                else:raise TimeoutError('Expected active lease')
                def blocked_script(targets):
                    return 'import socket\nfor peer in '+repr(targets)+':\n s=socket.socket();s.settimeout(.3)\n try:s.connect(peer)\n except OSError:pass\n else:raise AssertionError("Network bypass reached "+str(peer))\n finally:s.close()\nprint("BLOCKED")'
                assert docker('exec',worker,'python3','-B','-c',blocked_script(
                    [(ip(eg,ne),8888),('8.8.8.8',443),('169.254.169.254',80)]))=='BLOCKED'
                assert docker('exec',gw,'python3','-B','-c',blocked_script([(ip(eg,ne),443)]))=='BLOCKED'
                docker('create','--pull','never','--name',attacker,'--label',label,'--network',ne,*base,
                    '--user','65534:65534','--entrypoint','python3','clipora-worker:v8-dns','-B','-c',
                    blocked_script([(ip(eg,ne),8888)]));containers.append(attacker)
                docker('start',attacker);assert docker('wait',attacker)=='0';assert docker('logs',attacker)=='BLOCKED'
                assert '--dport 443' in docker('exec',eg,'iptables-save')
                if args.mutual:
                    identity_probe=r'''import os,socket,ssl
for client in (None,'other-client'):
 ctx=ssl.create_default_context(cafile='/fixture/ca.pem')
 if client:ctx.load_cert_chain('/fixture/'+client+'.pem','/fixture/'+client+'.key')
 try:
  with socket.create_connection((os.environ['EGRESS_IP'],8888),timeout=2) as raw:
   with ctx.wrap_socket(raw,server_hostname='egress.clipora.test') as stream:
    stream.sendall(b'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n')
    assert stream.recv(4096)==b''
 except (ssl.SSLError,ConnectionResetError):pass
print('IDENTITIES REJECTED')
'''
                    assert docker('exec',gw,'python3','-B','-c',identity_probe)=='IDENTITIES REJECTED'
                bypass_tested=True
                if not args.cancel_running and not args.interactive_hold:
                    docker('exec','--user','65534:65534',eg,'python3','-B','-c','from pathlib import Path;Path("/control/release").touch()')
            if args.cancel_running:
                from clipora_v8_web.owned_runner import observe
                identity=info(worker)['Id']
                class Handle:
                    def __init__(self):self.removed=False
                    async def wait(self):
                        while True:
                            current=await asyncio.to_thread(info,identity)
                            if not current['State']['Running']:raise RuntimeError('Fixture worker exited before cancellation')
                            await asyncio.sleep(.1)
                    async def stop(self):
                        if self.removed:return True
                        current=await asyncio.to_thread(info,identity)
                        labels=current['Config']['Labels']
                        if labels.get('clipora.three.kernel')!=token or labels.get('clipora.owned.job')!=job:
                            raise RuntimeError('Worker ownership mismatch')
                        assert owner_store.get(job)['status']=='processing'
                        await asyncio.to_thread(docker,'rm','-f',identity)
                        self.removed=True
                        containers.remove(worker)
                        return True
                assert owner_store.cancel_owned(browser_token,job)
                assert not asyncio.run(observe(owner_store,job,execution_owner,Handle(),out,poll=.01))
                assert owner_store.get(job)['status']=='failed'
                assert not owner_store.finish(job,execution_owner,True,'Late success')
                assert not list(out.iterdir())
                result,stdout,stderr=1,'',''
            else:result,stdout,stderr=collect_worker(worker,out,job,timeout=20,expected_bundle=code)
            if args.case=='valid' and not args.cancel_running:
                if result:raise RuntimeError('Actual worker failed: '+stderr[-2200:])
                metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_name,pix_fmt',
                    '-of','json',str(out/'video.mp4')],text=True,timeout=10))
                assert any(s.get('codec_name')=='h264' and s.get('pix_fmt')=='yuv420p' for s in metadata['streams'])
            elif not args.cancel_running:
                assert result!=0 and not list(out.rglob('*.mp4'))
                msg=stderr.lower();assert 'certificate_verify_failed' in msg or 'certificate verify failed' in msg
                if args.case=='wrong-host':assert any(s in msg for s in ('hostname mismatch','not valid for',"doesn't match"))
            for _ in range(80 if args.cancel_running else 30):
                if '--dport 443' not in docker('exec',eg,'iptables-save'):break
                time.sleep(.1)
            else:raise RuntimeError('Destination lease not revoked')
            assert ':OUTPUT DROP' in docker('exec',eg,'ip6tables-save')
            report={'case':args.case,'gateway_egress_mutual_TLS':args.mutual,
                'missing_and_wrong_client_identity_rejected':True if args.mutual and bypass_tested else None,
                'actual_v8_worker':True,'actual_ytdlp':True,
                'mp4_h264_verified':args.case=='valid' and not args.cancel_running,
                'mp4_bytes':(out/'video.mp4').stat().st_size if args.case=='valid' and not args.cancel_running else 0,
                'running_cancel_requested':args.cancel_running,
                'worker_removed_before_cancel_ack':True if args.cancel_running else None,
                'late_job_completion_blocked':True if args.cancel_running else None,
                'certificate_rejected':args.case!='valid','two_internal_networks':True,
                'separate_worker_gateway_egress_namespaces':True,'actual_dns_broker_kernel_tls':True,'issuer_keys_absent_from_runtime':True,
                'bypass_tests_during_active_lease':bypass_tested,'worker_to_egress_direct_blocked':True if bypass_tested else None,
                'worker_to_global_and_metadata_blocked':True if bypass_tested else None,'gateway_to_fixture_tls_direct_blocked':True if bypass_tested else None,
                'unauthorized_egress_network_peer_blocked':True if bypass_tested else None,'lease_removed_after_worker':True,
                'IPv6_default_drop':True,'public_downloads_enabled':False,'offline_fixture_only':True}
        finally:
            errors=[]
            for name in reversed(containers):
                try:
                    assert info(name)['Config']['Labels'].get('clipora.three.kernel')==token
                    docker('rm','-f',name)
                except Exception as exc:errors.append(str(exc))
            for net in reversed(networks):
                try:
                    assert json.loads(docker('network','inspect',net))[0]['Labels'].get('clipora.three.kernel')==token
                    docker('network','rm',net)
                except Exception as exc:errors.append(str(exc))
            if errors:raise RuntimeError('Incomplete cleanup: '+'; '.join(errors))
        preserved=before<=set(docker('ps','-aq','--no-trunc').split())
        if args.resource_owner is None:assert preserved
        if args.artifact is not None:
            destination=args.artifact.absolute()
            if any(p.is_symlink() for p in (destination,*destination.parents)):
                raise RuntimeError('Symlinked artifact export rejected')
            fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:
                with os.fdopen(fd,'wb') as stream, (out/'video.mp4').open('rb') as source:
                    while chunk:=source.read(65536):stream.write(chunk)
                    stream.flush();os.fsync(stream.fileno())
            except BaseException:
                destination.unlink(missing_ok=True);raise
    report.update(owned_resources_removed=True,cleanup_scoped_to_owner_labels=True,
                  preexisting_containers_preserved=preserved if args.resource_owner is None else None)
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
