"""Local-only service for the actual-worker namespace-sharing fixture."""
import asyncio
import os
import json
import ssl
from pathlib import Path
import dns.asyncresolver
import dns.message
import dns.rrset
from .binding import Broker
from .connect_relay import ConnectRelay
from .dns_snapshot import SnapshotResolver
from .numeric_dial import NumericDial
import gateway


async def serve(listener,context,firewall):
    payload=Path('/fixture/video.mp4').read_bytes()
    async def http(reader,writer):
        try:
            request=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),3)
            first=request.split(b'\r\n',1)[0].split(b' ')
            if len(first)!=3 or first[:2]!=[b'GET',b'/video.mp4']:
                writer.write(b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            else:
                if Path('/fixture/three-tier.json').exists():
                    async with asyncio.timeout(15):
                        while not Path('/control/release').exists():await asyncio.sleep(.05)
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: video/mp4\r\nContent-Length: '+str(len(payload)).encode()+b'\r\nConnection: close\r\n\r\n'+payload)
            await writer.drain()
        except (OSError,TimeoutError,asyncio.IncompleteReadError):pass
        finally:
            writer.close()
            try:await writer.wait_closed()
            except OSError:pass
    class DNS(asyncio.DatagramProtocol):
        def connection_made(self,t):self.transport=t
        def datagram_received(self,data,peer):
            q=dns.message.from_wire(data);r=dns.message.make_response(q)
            if q.question[0].name.to_text()!='example.com.':return
            if q.question[0].rdtype==1:r.answer.append(dns.rrset.from_text('example.com.',30,'IN','A','8.8.8.8'))
            else:r.authority.append(dns.rrset.from_text('example.com.',30,'IN','SOA','ns.example.com. hostmaster.example.com. 1 60 60 60 60'))
            self.transport.sendto(r.to_wire(),peer)
    loop=asyncio.get_running_loop()
    transport,_=await loop.create_datagram_endpoint(DNS,local_addr=('127.0.0.1',0))
    resolver=dns.asyncresolver.Resolver(configure=False)
    resolver.nameservers=['127.0.0.1'];resolver.port=transport.get_extra_info('sockname')[1]
    resolver.timeout=.2;resolver.lifetime=.5
    broker=Broker(['example.com'],SnapshotResolver(resolver.resolve),firewall,NumericDial())
    relay=ConnectRelay(broker,idle_timeout=5)
    os.environ['EGRESS_IP']='127.0.0.1'
    tls=await asyncio.start_server(http,sock=listener,ssl=context)
    three_tier=Path('/fixture/three-tier.json').exists()
    if three_tier:
        from .three_tier_fixture import config
        topology=config()
        mutual=Path('/fixture/mtls-mode').exists()
        ingress=None
        if mutual:
            ingress=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ingress.minimum_version=ssl.TLSVersion.TLSv1_2
            ingress.load_cert_chain('/fixture/server/ingress.pem','/fixture/server/ingress.key')
            ingress.load_verify_locations(cafile='/fixture/trust/ca.pem')
            ingress.verify_mode=ssl.CERT_REQUIRED
        async def restricted(reader,writer):
            peer=writer.get_extra_info('peername')
            if mutual:
                cert=writer.get_extra_info('peercert')
                identities={value for kind,value in cert.get('subjectAltName',()) if kind=='DNS'} if cert else set()
                if identities!={'gateway.clipora.test'}:
                    writer.close();return
            if not peer or peer[0]!=topology['gateway_ip']:
                writer.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n')
                await writer.drain();writer.close();return
            await relay.handle(reader,writer)
        egress=await asyncio.start_server(restricted,topology['egress_ip'],8888,limit=8192,ssl=ingress)
        gateway_server=None
    else:
        egress=await asyncio.start_server(relay.handle,'127.0.0.1',8888,limit=8192)
        gateway_server=await asyncio.start_server(gateway.handle,'127.0.0.2',8888,limit=8192)
    print('CLIPORA KERNEL WORKER SERVICE READY',flush=True)
    try:
        async with asyncio.timeout(60):
            await asyncio.Event().wait()
    finally:
        if gateway_server is not None:gateway_server.close()
        egress.close();tls.close();transport.close()
        if gateway_server is not None:await gateway_server.wait_closed()
        await egress.wait_closed();await tls.wait_closed()
