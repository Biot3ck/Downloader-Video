"""Exercise real kernel rule replacement and live-flow revocation offline."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
from run_offline import docker

HERE=Path(__file__).resolve().parent
BACKEND=HERE.parent
SINK='''
import socket,threading,time
for port in (8443,8444):
 s=socket.socket();s.bind(('0.0.0.0',port));s.listen()
 def serve(s):
  def connection(c):
   try:
    while True:
     data=c.recv(128)
     if not data:break
     c.sendall(data)
   finally:c.close()
  while True:
   c,_=s.accept();threading.Thread(target=connection,args=(c,),daemon=True).start()
 threading.Thread(target=serve,args=(s,),daemon=True).start()
print('ECHO READY',flush=True)
time.sleep(150)
'''
PROBE='''
import json,os,socket,sys
from pathlib import Path
sys.path.insert(0,'/fixture/clipora_v8_firewall_candidate')
from bootstrap import drop_privileges
drop_privileges(65534,65534)
status=dict(l.split(':',1) for l in Path('/proc/self/status').read_text().splitlines() if ':' in l)
assert all(int(status[n],16)==0 for n in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
s=socket.socket();s.settimeout(.5)
try:s.connect((sys.argv[1],int(sys.argv[2])))
except OSError:print('BLOCKED',flush=True);sys.exit(0)
print('CONNECTED-NONROOT-NOCAPS',flush=True)
for line in sys.stdin:
 if line.strip()=='stop':break
 try:
  s.sendall(b'clipora-probe');data=s.recv(128)
  print('ECHO' if data==b'clipora-probe' else 'BLOCKED',flush=True)
 except OSError:print('BLOCKED',flush=True)
s.close()
'''
CONTROLLER='''
import asyncio,json,sys,time,subprocess
from pathlib import Path
from dataclasses import replace
from clipora_v8_firewall_candidate.binding import Destination
from clipora_v8_firewall_candidate.kernel_leases import KernelLeases
async def main():
 config=json.loads(Path('/fixture/config.json').read_text())
 fw=KernelLeases(config);await fw.initialize()
 probes=[]
 async def probe(port):
  p=await asyncio.create_subprocess_exec(sys.executable,'-B','-u','/fixture/probe.py',config['destination_ip'],str(port),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
  probes.append(p)
  return p,(await asyncio.wait_for(p.stdout.readline(),3)).decode().strip()
 async def ping(p):
  p.stdin.write(b'ping\\n');await p.stdin.drain()
  return (await asyncio.wait_for(p.stdout.readline(),3)).decode().strip()
 try:
  _,state=await probe(8443);assert state=='BLOCKED',state
  a=Destination('a'*32,'example.com',8443,config['destination_ip'],(config['destination_ip'],),time.monotonic()+25)
  b=replace(a,lease_id='b'*32)
  await fw.grant(a)
  held,state=await probe(8443);assert state=='CONNECTED-NONROOT-NOCAPS',state
  assert await ping(held)=='ECHO'
  _,state=await probe(8444);assert state=='BLOCKED',state
  await fw.grant(b);await fw.revoke(a)
  assert await ping(held)=='ECHO'
  await fw.revoke(b);await fw.revoke(b)
  assert await ping(held)=='BLOCKED'
  _,state=await probe(8443);assert state=='BLOCKED',state
  assert not fw.leases
  # Cause an actual iptables-restore rejection while a live flow is permitted.
  a=replace(a,expires_at=time.monotonic()+25);b=replace(a,lease_id='b'*32)
  await fw.grant(a)
  held_failure,state=await probe(8443);assert state=='CONNECTED-NONROOT-NOCAPS'
  assert await ping(held_failure)=='ECHO'
  original=fw.command;failed=False
  def reject_once(args,data=None):
   nonlocal failed
   if not failed:
    failed=True
    data=data.replace('COMMIT','-A OUTPUT -j CLIPORA_MISSING_CHAIN\\nCOMMIT')
   return original(args,data)
  fw.command=reject_once
  try:await fw.grant(b)
  except subprocess.CalledProcessError:pass
  else:raise AssertionError('Expected actual restore rejection')
  assert fw.poisoned and not fw.leases
  assert await ping(held_failure)=='BLOCKED'
  _,state=await probe(8443);assert state=='BLOCKED'
  try:await fw.grant(b)
  except PermissionError:pass
  else:raise AssertionError('Unhealthy controller accepted a lease')
  print(json.dumps({'default_deny':True,'granted_destination_reachable':True,'wrong_port_denied':True,
    'shared_destination_survives_first_revoke':True,'last_revoke_blocks_existing_flow':True,
    'last_revoke_blocks_new_connection':True,'revoke_idempotent':True,'probe_nonroot_no_capabilities':True,
    'actual_restore_failure_falls_back_to_deny_all':True,'unhealthy_controller_rejects_grants':True,
    'private_fixture_addresses_only':True,'live_dns_used':False,'public_broker_integrated':False}),flush=True)
 finally:
  for p in probes:
   if p.returncode is None:
    p.stdin.close()
    await asyncio.wait_for(p.wait(),3)
asyncio.run(main())
'''


def main():
    run_id=uuid4().hex;prefix='clipora-leases-'+run_id[:10];label='clipora.leases.test='+run_id
    names=[];network=None;before=set(docker(['ps','-aq','--no-trunc']).split())
    with tempfile.TemporaryDirectory(prefix='clipora-kernel-leases-') as tmp:
        root=Path(tmp)
        files=['clipora_v8_firewall_candidate/'+n for n in ('binding.py','kernel_leases.py','policy.py','bootstrap.py')]
        files+=['clipora_v8_secure_egress_stage/'+n for n in ('connect_policy.py','ip_policy.py')]
        for filename in files:
            target=root/filename;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BACKEND/filename,target)
        (root/'probe.py').write_text(PROBE);(root/'controller.py').write_text(CONTROLLER)
        def info(name):return json.loads(docker(['inspect',name]))[0]
        def ip(name):return info(name)['NetworkSettings']['Networks'][network]['IPAddress']
        try:
            network=prefix+'-internal';docker(['network','create','--internal','--label',label,network])
            topology=json.loads(docker(['network','inspect',network]))[0];assert topology['Internal'] is True
            for suffix in ('target','peer'):
                name=prefix+'-'+suffix
                docker(['create','--pull','never','--name',name,'--label',label,'--network',network,'--read-only',
                        '--cap-drop','ALL','--security-opt','no-new-privileges','--user','65534:65534',
                        '--memory','128m','--cpus','1','--pids-limit','32','--entrypoint','python3',
                        'clipora-gateway:v8-test','-B','-u','-c',SINK]);names.append(name);docker(['start',name])
                for _ in range(40):
                    if 'ECHO READY' in docker(['logs',name]):break
                    time.sleep(.1)
                else:raise TimeoutError('Fixture readiness failed')
            target,peer=names
            for port in (8443,8444):
                script=f"import socket;s=socket.create_connection(({ip(target)!r},{port}),2);s.sendall(b'x');assert s.recv(1)==b'x';s.close()"
                docker(['exec',peer,'python3','-B','-c',script])
            config={'mode':'offline-fixture','network':topology['IPAM']['Config'][0]['Subnet'],
                    'gateway_ip':ip(peer),'destination_ip':ip(target),'destination_port':8443,'uid':65534,'gid':65534}
            (root/'config.json').write_text(json.dumps(config))
            controller=prefix+'-controller'
            docker(['create','--pull','never','--name',controller,'--label',label,'--network',network,'--read-only',
                    '--cap-drop','ALL','--cap-add','NET_ADMIN','--cap-add','SETPCAP','--cap-add','SETUID','--cap-add','SETGID',
                    '--security-opt','no-new-privileges','--user','0:0','--memory','128m','--cpus','1','--pids-limit','32',
                    '-e','CLIPORA_DISPOSABLE_FIREWALL_TEST=1','--mount',f'type=bind,source={root},target=/fixture,readonly',
                    '--workdir','/fixture','--entrypoint','python3','clipora-gateway:v8-test','-B','-u','/fixture/controller.py'])
            names.append(controller);docker(['start',controller])
            code=docker(['wait',controller],timeout=50)
            logs=docker(['logs',controller],check=False)
            if code!='0':raise RuntimeError('Kernel lease probe failed: '+logs.stderr[-2000:])
            report=json.loads(logs.stdout)
            report.update({'environment':docker(['info','--format','{{.OSType}} / {{.OperatingSystem}}']),
                           'offline_only':True,'host_firewall_modified':False,'production_gate_closed':False})
        finally:
            errors=[]
            for name in reversed(names):
                try:
                    assert info(name)['Config']['Labels'].get('clipora.leases.test')==run_id
                    docker(['rm','-f',name])
                except Exception as exc:errors.append(str(exc))
            if network:
                try:
                    assert json.loads(docker(['network','inspect',network]))[0]['Labels'].get('clipora.leases.test')==run_id
                    docker(['network','rm',network])
                except Exception as exc:errors.append(str(exc))
            if errors:raise RuntimeError('Cleanup incomplete: '+'; '.join(errors))
            assert before<=set(docker(['ps','-aq','--no-trunc']).split())
    report['owned_resources_removed']=True;report['preexisting_containers_preserved']=True
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
