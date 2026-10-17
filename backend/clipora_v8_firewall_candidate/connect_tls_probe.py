"""Only invoked by the isolated kernel fixture, never the web runtime."""
import asyncio
import hashlib
from pathlib import Path
import ssl
from unittest.mock import patch
import dns.asyncresolver
import dns.message
import dns.rrset
from .binding import Broker
from .connect_relay import ConnectRelay
from .dns_snapshot import SnapshotResolver
from .numeric_dial import NumericDial


async def probe(listener, server_context, client_context, firewall, case):
    payload=Path('/fixture/sample.mp4').read_bytes()
    assert payload[4:8]==b'ftyp'
    requests=[];queries=[];handlers=set()
    async def http(reader,writer):
        try:
            request=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),2)
            assert request==b'GET /sample.mp4 HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n'
            requests.append(request)
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: video/mp4\r\nContent-Length: '+str(len(payload)).encode()+b'\r\nConnection: close\r\n\r\n'+payload)
            await writer.drain()
        finally:
            writer.close()
            try:await writer.wait_closed()
            except OSError:pass
    class DNS(asyncio.DatagramProtocol):
        def connection_made(self,t):self.transport=t
        def datagram_received(self,data,peer):
            q=dns.message.from_wire(data);r=dns.message.make_response(q)
            name=q.question[0].name.to_text();family=q.question[0].rdtype
            assert name=='example.com.'
            queries.append(family)
            if family==1:r.answer.append(dns.rrset.from_text(name,30,'IN','A','8.8.8.8'))
            else:r.authority.append(dns.rrset.from_text(name,30,'IN','SOA','ns.example.com. hostmaster.example.com. 1 60 60 60 60'))
            self.transport.sendto(r.to_wire(),peer)
    loop=asyncio.get_running_loop()
    dns_transport,_=await loop.create_datagram_endpoint(DNS,local_addr=('127.0.0.1',0))
    resolver=dns.asyncresolver.Resolver(configure=False)
    resolver.nameservers=['127.0.0.1'];resolver.port=dns_transport.get_extra_info('sockname')[1]
    resolver.timeout=.2;resolver.lifetime=.5
    broker=Broker(['example.com'],SnapshotResolver(resolver.resolve),firewall,NumericDial())
    relay=ConnectRelay(broker,idle_timeout=2)
    async def handle(reader,writer):
        task=asyncio.current_task();handlers.add(task)
        try:await relay.handle(reader,writer)
        finally:handlers.remove(task)
    upstream=await asyncio.start_server(http,sock=listener,ssl=server_context)
    proxy=await asyncio.start_server(handle,'127.0.0.1',0,limit=8192)
    writer=None
    try:
        with patch.object(loop,'getaddrinfo',side_effect=AssertionError('Unexpected resolver fallback')):
            reader,writer=await asyncio.open_connection('127.0.0.1',proxy.sockets[0].getsockname()[1])
            writer.write(b'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n')
            await writer.drain()
            assert await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),3)==b'HTTP/1.1 200 Connection Established\r\n\r\n'
            try:
                await writer.start_tls(client_context,server_hostname='example.com',ssl_handshake_timeout=2)
            except ssl.SSLCertVerificationError:
                if case=='valid':raise
                assert not requests
            else:
                assert case=='valid'
                writer.write(b'GET /sample.mp4 HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n')
                await writer.drain()
                header=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),3)
                assert header.startswith(b'HTTP/1.1 200 OK\r\n')
                assert b'Content-Length: '+str(len(payload)).encode()+b'\r\n' in header
                media=await asyncio.wait_for(reader.readexactly(len(payload)),3)
                assert hashlib.sha256(media).digest()==hashlib.sha256(payload).digest()
        writer.close()
        try:await asyncio.wait_for(writer.wait_closed(),2)
        except OSError:pass
        async with asyncio.timeout(5):
            while handlers:await asyncio.sleep(.01)
        assert broker.active==relay.active==0 and queries==[1,28]
        return {'real_DNS_broker_kernel_CONNECT_TLS_HTTP':True,'case':case,
                'mp4_bytes_verified':case=='valid','application_request_blocked_by_TLS':case!='valid',
                'certificate_verification_enabled':True,'relay_sessions_cleaned':True,
                'firewall_simulated':False,'public_network_used':False,
                'worker_and_gateway_integrated':False,'offline_fixture_only':True}
    finally:
        if writer is not None:writer.close()
        proxy.close();upstream.close();dns_transport.close()
        await proxy.wait_closed();await upstream.wait_closed()
        for task in list(handlers):task.cancel()
        if handlers:await asyncio.gather(*list(handlers),return_exceptions=True)
