"""Broker + real numeric TCP socket, using a local alias in network=none."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

PROBE=r'''
import asyncio,json,os,socket,subprocess,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,'/fixture/clipora_v8_firewall_candidate')
from bootstrap import drop_privileges
from clipora_v8_firewall_candidate.binding import Broker
from clipora_v8_firewall_candidate.numeric_dial import NumericDial
assert os.environ.get('CLIPORA_NUMERIC_OFFLINE_TEST')=='1'
# This IP is an alias inside a disposable network=none namespace, never a
# route to its real Internet owner. There is no non-loopback interface.
interfaces=[name for _,name in socket.if_nameindex()]
assert [name for name in interfaces if int(Path('/sys/class/net',name,'flags').read_text(),16)&1]==['lo']
for name in interfaces:
 if name!='lo':
  lines=subprocess.check_output(['ip','addr','show','dev',name],text=True).splitlines()
  assert not any(line.strip().startswith(('inet ','inet6 ')) for line in lines)
assert not subprocess.check_output(['ip','route','show','default']).strip()
subprocess.run(['ip','addr','add','8.8.8.8/32','dev','lo'],check=True,timeout=3)
listen=socket.socket();listen.bind(('8.8.8.8',443));listen.listen();listen.setblocking(False)
drop_privileges(65534,65534)
status=dict(l.split(':',1) for l in Path('/proc/self/status').read_text().splitlines() if ':' in l)
assert all(int(status[n],16)==0 for n in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
grants=[];revoked=[];queries=[];active=set();empty=asyncio.Event()
class Firewall:
 async def grant(self,d):grants.append(d)
 async def revoke(self,d):revoked.append(d)
async def resolver(host):
 queries.append(host);return {'host':host,'A':['8.8.8.8'],'AAAA':[],'ttl':30}
async def echo(reader,writer):
 active.add(writer);empty.clear()
 try:
  while data:=await reader.read(1024):writer.write(data);await writer.drain()
 finally:
  writer.close();await writer.wait_closed();active.remove(writer)
  if not active:empty.set()
async def main():
 server=await asyncio.start_server(echo,sock=listen)
 broker=Broker(['example.com'],resolver,Firewall(),NumericDial())
 try:
  loop=asyncio.get_running_loop()
  # Fail the test if either socket layer tries an additional DNS lookup.
  with patch.object(loop,'getaddrinfo',side_effect=AssertionError('Unexpected DNS lookup')):
   async with broker.connection('example.com:443') as (reader,writer,dest):
    assert writer.get_extra_info('peername')==('8.8.8.8',443)
    writer.write(b'clipora-numeric-probe');await writer.drain()
    assert await asyncio.wait_for(reader.readexactly(21),2)==b'clipora-numeric-probe'
   await asyncio.wait_for(empty.wait(),2)
   assert len(grants)==1 and grants==revoked
   entered=asyncio.Event()
   async def work():
    async with broker.connection('example.com:443') as (reader,writer,dest):
     writer.write(b'x');await writer.drain();assert await reader.readexactly(1)==b'x'
     entered.set();await asyncio.Event().wait()
   task=asyncio.create_task(work());await asyncio.wait_for(entered.wait(),2);task.cancel()
   try:await task
   except asyncio.CancelledError:pass
   else:raise AssertionError('Expected cancellation')
   await asyncio.wait_for(empty.wait(),2)
   assert len(grants)==2 and grants==revoked and broker.active==0 and not active
  print(json.dumps({'numeric_tcp_bytes_roundtrip':True,'actual_socket_peer_verified':True,
   'no_getaddrinfo_during_connect':True,'normal_exit_closes_socket':True,
   'cancelled_session_closes_socket_and_revokes':True,'broker_active_returns_zero':True,
   'nonroot_zero_capabilities_after_bootstrap':True,'global_ip_is_local_loopback_alias':True,
   'only_loopback_active_and_addressed':True,'no_default_route':True,'dns_and_firewall_simulated':True,
   'tls_tested':False,'public_network_used':False}))
 finally:server.close();await server.wait_closed()
asyncio.run(main())
'''


def main(*, probe=PROBE, extra_files=(), report_path=None, prepare=None):
    backend=Path(__file__).resolve().parent.parent
    name='clipora-numeric-'+uuid4().hex[:10]
    def docker(*args):
        p=subprocess.run(['docker',*args],capture_output=True,text=True,timeout=25)
        if p.returncode:raise RuntimeError(p.stderr[-2500:])
        return (p.stdout+p.stderr).strip() if args[0]=='logs' else p.stdout.strip()
    with tempfile.TemporaryDirectory(prefix='clipora-numeric-') as tmp:
        root=Path(tmp)
        files=['clipora_v8_firewall_candidate/'+n for n in ('numeric_dial.py','binding.py','bootstrap.py','policy.py')]
        files+=list(extra_files)
        files+=['clipora_v8_secure_egress_stage/'+n for n in ('connect_policy.py','ip_policy.py')]
        for relative in files:
            target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(backend/relative,target)
        (root/'probe.py').write_text(probe)
        if prepare is not None:prepare(root)
        created=False
        try:
            docker('create','--pull','never','--name',name,'--label','clipora.numeric.test='+name,
                   '--network','none','--read-only','--cap-drop','ALL',
                   '--cap-add','NET_ADMIN','--cap-add','SETPCAP','--cap-add','SETUID','--cap-add','SETGID',
                   '--user','0:0','--security-opt','no-new-privileges',
                   '--memory','128m','--cpus','1','--pids-limit','32','-e','CLIPORA_NUMERIC_OFFLINE_TEST=1',
                   '--mount',f'type=bind,source={root},target=/fixture,readonly','--workdir','/fixture',
                   '--entrypoint','python3','clipora-dns-wire:v8-test','-B','-u','/fixture/probe.py')
            created=True
            assert json.loads(docker('inspect',name))[0]['HostConfig']['NetworkMode']=='none'
            docker('start',name);code=docker('wait',name);logs=docker('logs',name)
            if code!='0':raise RuntimeError('Numeric wire probe failed: '+logs)
            report=json.loads(logs)
        finally:
            if created:
                info=json.loads(docker('inspect',name))[0]
                assert info['Config']['Labels'].get('clipora.numeric.test')==name
                docker('rm','-f',name)
    report.update({'network_mode':'none','owned_container_removed':True,'host_network_modified':False,
                   'public_downloads_enabled':False})
    if report_path is not None:Path(report_path).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main(report_path=sys.argv[1] if len(sys.argv)>1 else None)
