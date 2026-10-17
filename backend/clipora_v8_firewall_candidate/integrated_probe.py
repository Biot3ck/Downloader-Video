"""Offline executable fixture; never import into application runtime."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from unittest.mock import patch

import dns.asyncresolver
import dns.message
import dns.rcode
import dns.rrset

sys.path.insert(0, '/fixture/clipora_v8_firewall_candidate')
from bootstrap import drop_privileges
from clipora_v8_firewall_candidate.binding import Broker
from clipora_v8_firewall_candidate.dns_snapshot import SnapshotResolver
from clipora_v8_firewall_candidate.numeric_dial import NumericDial


def bootstrap():
    if os.environ.get('CLIPORA_NUMERIC_OFFLINE_TEST') != '1':
        raise PermissionError('Disposable offline harness required')
    interfaces = [name for _, name in socket.if_nameindex()]
    assert [n for n in interfaces if int(Path('/sys/class/net', n, 'flags').read_text(), 16) & 1] == ['lo']
    for name in interfaces:
        if name != 'lo':
            lines = subprocess.check_output(['ip', 'addr', 'show', 'dev', name], text=True).splitlines()
            assert not any(line.strip().startswith(('inet ', 'inet6 ')) for line in lines)
    assert not subprocess.check_output(['ip', 'route', 'show', 'default']).strip()
    subprocess.run(['ip', 'addr', 'add', '8.8.8.8/32', 'dev', 'lo'], check=True, timeout=3)
    listener = socket.socket()
    listener.bind(('8.8.8.8', 443))
    listener.listen()
    listener.setblocking(False)
    drop_privileges(65534, 65534)
    return listener


async def run(listener, *, server_context=None, client_context=None, tls_hostname=None, expect_tls_failure=False, firewall_adapter=None):
    queries, grants, revoked, accepted = [], [], [], []
    active = set()
    empty = asyncio.Event()

    class Firewall:
        async def grant(self, destination):
            grants.append(destination)
            if firewall_adapter is not None:await firewall_adapter.grant(destination)
        async def revoke(self, destination):
            revoked.append(destination)
            if firewall_adapter is not None:await firewall_adapter.revoke(destination)

    class DNS(asyncio.DatagramProtocol):
        def connection_made(self, transport):self.transport = transport
        def datagram_received(self, packet, peer):
            query = dns.message.from_wire(packet)
            response = dns.message.make_response(query)
            name, family = query.question[0].name.to_text(), query.question[0].rdtype
            queries.append((name, family))
            if name == 'failed.example.' and family == 28:
                response.set_rcode(dns.rcode.SERVFAIL)
            elif family == 1:
                response.answer.append(dns.rrset.from_text(name, 30, 'IN', 'A', '8.8.8.8'))
            elif name == 'mixed.example.':
                response.answer.append(dns.rrset.from_text(name, 30, 'IN', 'AAAA', '::1'))
            else:
                response.authority.append(dns.rrset.from_text('example.', 30, 'IN', 'SOA',
                    'ns.example. hostmaster.example. 1 60 60 60 60'))
            self.transport.sendto(response.to_wire(), peer)

    async def echo(reader, writer):
        accepted.append(writer.get_extra_info('peername'))
        active.add(writer)
        empty.clear()
        try:
            while data := await reader.read(1024):
                writer.write(data)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            active.remove(writer)
            if not active:empty.set()

    loop = asyncio.get_running_loop()
    dns_transport, _ = await loop.create_datagram_endpoint(DNS, local_addr=('127.0.0.1', 0))
    server = await asyncio.start_server(echo, sock=listener, ssl=server_context)
    resolver = dns.asyncresolver.Resolver(configure=False)
    resolver.nameservers = ['127.0.0.1']
    resolver.port = dns_transport.get_extra_info('sockname')[1]
    resolver.timeout = .2
    resolver.lifetime = .5
    snapshot = SnapshotResolver(resolver.resolve, timeout=1)
    safe_host = tls_hostname if client_context is not None else 'safe.example'
    broker = Broker([safe_host, 'mixed.example', 'failed.example'], snapshot, Firewall(), NumericDial())
    try:
        with patch.object(loop, 'getaddrinfo', side_effect=AssertionError('Unexpected hostname lookup')):
            async with broker.connection(safe_host + ':443') as (reader, writer, destination):
                if client_context is not None:
                    await writer.start_tls(client_context, server_hostname=tls_hostname, ssl_handshake_timeout=2)
                assert destination.ip == '8.8.8.8'
                assert writer.get_extra_info('peername') == ('8.8.8.8', 443)
                writer.write(b'clipora-integrated')
                await writer.drain()
                assert await asyncio.wait_for(reader.readexactly(18), 2) == b'clipora-integrated'
            await asyncio.wait_for(empty.wait(), 2)
            assert len(accepted) == 1 and grants == revoked
            for target in ('mixed.example:443', 'failed.example:443'):
                before = len(grants), len(accepted)
                try:
                    async with broker.connection(target):pass
                except ValueError:pass
                else:raise AssertionError('Invalid DNS accepted')
                assert before == (len(grants), len(accepted))
            entered = asyncio.Event()
            async def session():
                async with broker.connection(safe_host + ':443') as (reader, writer, _):
                    if client_context is not None:
                        await writer.start_tls(client_context, server_hostname=tls_hostname, ssl_handshake_timeout=2)
                    writer.write(b'x')
                    await writer.drain()
                    assert await reader.readexactly(1) == b'x'
                    entered.set()
                    await asyncio.Event().wait()
            task = asyncio.create_task(session())
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
            else:raise AssertionError('Expected cancellation')
            await asyncio.wait_for(empty.wait(), 2)
        assert len(grants) == 2 and grants == revoked
        assert len(accepted) == 2 and broker.active == snapshot.active == 0 and not active
        assert queries == [(host, family) for host in
            (safe_host + '.', 'mixed.example.', 'failed.example.', safe_host + '.') for family in (1, 28)]
        return {'real_dns_and_numeric_socket_same_broker': True, 'actual_bytes_roundtrip': True,
                'no_second_dns_lookup': True, 'unsafe_dns_denied_before_socket_and_grant': True,
                'AAAA_failure_discards_partial_A': True, 'cancel_closes_real_socket_and_revokes': True,
                'nonroot_zero_capabilities': True, 'dns_server_loopback_only': True,
                'global_ip_is_loopback_alias': True, 'firewall_simulated': firewall_adapter is None,
                'kernel_integrated': firewall_adapter is not None, 'tls_tested': client_context is not None, 'public_network_used': False}
    except BaseException as exc:
        if not expect_tls_failure:raise
        import ssl
        cause = exc
        while cause is not None and not isinstance(cause, ssl.SSLCertVerificationError):
            cause = cause.__cause__
        if cause is None:raise
        assert len(grants) == 1 and grants == revoked and broker.active == 0
        assert len(accepted) == 0
        return {'tls_verification_failure_observed': True, 'no_application_bytes_accepted': True,
                'lease_revoked_after_tls_failure': True, 'firewall_simulated': firewall_adapter is None,
                'kernel_integrated': firewall_adapter is not None, 'public_network_used': False}
    finally:
        dns_transport.close()
        server.close()
        await server.wait_closed()


if __name__ == '__main__':
    print(json.dumps(asyncio.run(run(bootstrap()))))
