"""Real DNS UDP/TCP packets on loopback, inside network=none Docker."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

PROBE = r'''
import asyncio,json,socket
from pathlib import Path
import dns.asyncresolver,dns.flags,dns.message,dns.rcode,dns.rrset
from clipora_v8_firewall_candidate.dns_snapshot import SnapshotResolver
from clipora_v8_firewall_candidate.binding import Broker

queries=[];grants=[];dials=[];revoked=[]
def response(data,tcp=False):
 q=dns.message.from_wire(data);r=dns.message.make_response(q)
 name=q.question[0].name.to_text();family=q.question[0].rdtype
 queries.append((name,family,'tcp' if tcp else 'udp'))
 if name=='truncated.example.' and not tcp:
  r.flags|=dns.flags.TC;return r.to_wire()
 if family==28 and name in ('nxdomain.example.','servfail.example.'):
  r.set_rcode(dns.rcode.NXDOMAIN if name.startswith('nxdomain') else dns.rcode.SERVFAIL)
  return r.to_wire()
 target=name
 if name=='alias.example.':
  target='cdn.example.'
  r.answer.append(dns.rrset.from_text(name,4,'IN','CNAME',target))
 if family==1:
  ip='127.0.0.1' if name=='private.example.' else '8.8.8.8'
  r.answer.append(dns.rrset.from_text(target,0 if name=='zero.example.' else 60,'IN','A',ip))
 elif name=='mixed.example.':r.answer.append(dns.rrset.from_text(name,60,'IN','AAAA','::1'))
 else:r.authority.append(dns.rrset.from_text('example.',60,'IN','SOA','ns.example. hostmaster.example. 1 60 60 60 60'))
 return r.to_wire()
class UDP(asyncio.DatagramProtocol):
 def connection_made(self,transport):self.transport=transport
 def datagram_received(self,data,addr):self.transport.sendto(response(data),addr)
async def tcp(reader,writer):
 try:
  size=int.from_bytes(await reader.readexactly(2),'big')
  data=response(await reader.readexactly(size),True)
  writer.write(len(data).to_bytes(2,'big')+data);await writer.drain()
 finally:writer.close();await writer.wait_closed()
class Firewall:
 async def grant(self,d):grants.append(d)
 async def revoke(self,d):revoked.append(d)
class Writer:
 def __init__(self,peer):self.peer=peer
 def get_extra_info(self,name):return self.peer
 def close(self):pass
 async def wait_closed(self):pass
async def dial(ip,port):dials.append((ip,port));return None,Writer((ip,port))
async def main():
 status=dict(l.split(':',1) for l in Path('/proc/self/status').read_text().splitlines() if ':' in l)
 assert all(int(status[n],16)==0 for n in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
 loop=asyncio.get_running_loop()
 transport,_=await loop.create_datagram_endpoint(UDP,local_addr=('127.0.0.1',0))
 port=transport.get_extra_info('sockname')[1]
 server=await asyncio.start_server(tcp,'127.0.0.1',port)
 resolver=dns.asyncresolver.Resolver(configure=False)
 resolver.nameservers=['127.0.0.1'];resolver.port=port;resolver.timeout=.2;resolver.lifetime=.5
 adapter=SnapshotResolver(resolver.resolve,timeout=1)
 hosts=[n+'.example' for n in ('safe','truncated','alias','mixed','private','nxdomain','servfail','zero')]
 broker=Broker(hosts,adapter,Firewall(),dial)
 try:
  for host in hosts[:3]:
   async with broker.connection(host+':443') as (_,_,dest):
    assert dest.ip=='8.8.8.8'
    if host=='alias.example':
     import time
     assert 0<dest.expires_at-time.monotonic()<=4
  assert len(grants)==3 and grants==revoked and len(dials)==3
  for host in hosts[3:]:
   before=(len(grants),len(dials))
   try:
    async with broker.connection(host+':443'):pass
   except ValueError:pass
   else:raise AssertionError('Unsafe DNS answer accepted: '+host)
   assert before==(len(grants),len(dials))
  assert any(n=='truncated.example.' and t=='tcp' for n,_,t in queries)
  assert broker.active==0 and adapter.active==0
  print(json.dumps({'dns_udp_packets':True,'dns_tcp_fallback':True,'complete_A_AAAA_snapshot':True,
   'cname_ttl_preserved':True,'private_and_mixed_addresses_denied_before_grant':True,
   'partial_A_discarded_on_AAAA_NXDOMAIN_or_SERVFAIL':True,'zero_ttl_rejected':True,
   'broker_grant_dial_revoke_contract':True,'firewall_and_media_dial_simulated':True,
   'dns_server_loopback_only':True,'public_dns_used':False,'nonroot_zero_capabilities':True}))
 finally:
  transport.close();server.close();await server.wait_closed()
asyncio.run(main())
'''

def main():
    backend=Path(__file__).resolve().parent.parent
    name='clipora-dns-snapshot-'+uuid4().hex[:10]
    label='clipora.dns.snapshot='+name
    def docker(*args):
        p=subprocess.run(['docker',*args],capture_output=True,text=True,timeout=25)
        if p.returncode:raise RuntimeError(p.stderr[-2000:])
        return p.stdout.strip()
    with tempfile.TemporaryDirectory(prefix='clipora-dns-snapshot-') as tmp:
        root=Path(tmp)
        files=['clipora_v8_firewall_candidate/'+n for n in ('dns_snapshot.py','binding.py')]
        files+=['clipora_v8_secure_egress_stage/'+n for n in ('connect_policy.py','ip_policy.py')]
        for relative in files:
            target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(backend/relative,target)
        (root/'probe.py').write_text(PROBE)
        created=False
        try:
            docker('create','--pull','never','--name',name,'--label',label,'--network','none',
                   '--read-only','--cap-drop','ALL','--user','65534:65534',
                   '--security-opt','no-new-privileges','--memory','128m','--cpus','1','--pids-limit','32',
                   '--mount',f'type=bind,source={root},target=/fixture,readonly','--workdir','/fixture',
                   '--entrypoint','python3','clipora-dns-wire:v8-test','-B','-u','/fixture/probe.py')
            created=True
            info=json.loads(docker('inspect',name))[0]
            assert info['HostConfig']['NetworkMode']=='none'
            docker('start',name)
            code=docker('wait',name)
            logs=docker('logs',name)
            if code!='0':raise RuntimeError('DNS wire fixture failed: '+logs)
            report=json.loads(logs)
        finally:
            if created:
                info=json.loads(docker('inspect',name))[0]
                assert info['Config']['Labels'].get('clipora.dns.snapshot')==name
                docker('rm','-f',name)
    report.update({'network_mode':'none','owned_container_removed':True,'public_downloads_enabled':False})
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
