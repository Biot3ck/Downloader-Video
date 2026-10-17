"""Disposable network=none integration fixture, never a production controller.

The parent owns this namespace's complete filter table. Its only RPC endpoint
is one inherited SOCK_SEQPACKET pair; the unprivileged child cannot obtain it
through a path or network listener. Policy authorizes exactly one local alias.
"""
import asyncio
from dataclasses import asdict
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

sys.path.insert(0, '/fixture')
sys.path.insert(0, '/fixture/clipora_v8_firewall_candidate')
from bootstrap import drop_privileges
from clipora_v8_firewall_candidate.numeric_dial import NumericDial
from clipora_v8_firewall_candidate.integrated_probe import run


def command(argv, data=None):
    subprocess.run(argv, input=data, text=True, capture_output=True, check=True, timeout=3)


def install(leases):
    lines = ['*filter', ':INPUT DROP [0:0]', ':FORWARD DROP [0:0]', ':OUTPUT DROP [0:0]',
             '-A INPUT -i lo -s 127.0.0.0/8 -d 127.0.0.0/8 -j ACCEPT',
             '-A OUTPUT -o lo -s 127.0.0.0/8 -d 127.0.0.0/8 -j ACCEPT']
    if leases:
        # Both endpoints exist in this one namespace: request and reply must
        # traverse both INPUT and OUTPUT. This is fixture-only local policy.
        for chain, interface in (('INPUT', '-i'), ('OUTPUT', '-o')):
            lines += [f'-A {chain} {interface} lo -d 8.8.8.8/32 -p tcp --dport 443 -j ACCEPT',
                      f'-A {chain} {interface} lo -s 8.8.8.8/32 -p tcp --sport 443 -m conntrack --ctstate ESTABLISHED -j ACCEPT']
    command(['iptables-restore', '-w', '2'], '\n'.join([*lines, 'COMMIT', '']))


def validate(request):
    if not isinstance(request, dict) or set(request) != {'operation', 'destination'}:
        raise ValueError('Invalid request fields')
    if request['operation'] not in ('grant', 'revoke'):raise ValueError('Invalid operation')
    d = request['destination']
    if not isinstance(d, dict) or set(d) != {'lease_id', 'host', 'port', 'ip', 'addresses', 'expires_at'}:
        raise ValueError('Invalid destination fields')
    if (type(d['lease_id']) is not str or not re.fullmatch('[0-9a-f]{32}', d['lease_id'])
            or d['host'] != 'example.com' or type(d['port']) is not int or d['port'] != 443
            or d['ip'] != '8.8.8.8' or d['addresses'] != ['8.8.8.8']
            or type(d['expires_at']) not in (int, float) or not math.isfinite(d['expires_at'])):
        raise ValueError('Destination outside loopback fixture policy')
    if request['operation'] == 'grant' and not time.monotonic() < d['expires_at'] <= time.monotonic() + 30:
        raise ValueError('Expired lease')
    return request['operation'], d


class Client:
    def __init__(self, channel):self.channel, self.lock = channel, asyncio.Lock()
    async def request(self, operation, destination):
        payload = json.dumps({'operation': operation, 'destination': asdict(destination)}).encode()
        async with self.lock:
            # Cancellation cannot release serialization while a request is in
            # flight. Parent subprocess updates have bounded execution times.
            def exchange():
                self.channel.sendall(payload)
                reply = self.channel.recv(4097)
                if reply != b'{"ok":true}':raise RuntimeError('Fixture firewall request failed')
            task = asyncio.create_task(asyncio.to_thread(exchange))
            cancelled = False
            while not task.done():
                try:await asyncio.wait({task})
                except asyncio.CancelledError:cancelled = True
            task.result()
            if cancelled:raise asyncio.CancelledError
    async def grant(self, d):await self.request('grant', d)
    async def revoke(self, d):await self.request('revoke', d)


async def child(listener, channel):
    import ssl
    case = Path('/fixture/tls-case.txt').read_text()
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.minimum_version = ssl.TLSVersion.TLSv1_2
    cert = 'wrong-host' if case == 'wrong-host' else 'valid'
    server.load_cert_chain('/fixture/server/' + cert + '.pem', '/fixture/server/' + cert + '.key')
    client = ssl.create_default_context(cafile='/fixture/trust/' + ('other' if case == 'untrusted-ca' else 'ca') + '.pem')
    assert client.check_hostname and client.verify_mode == ssl.CERT_REQUIRED
    async def blocked():
        try:
            reader, writer = await NumericDial(timeout=.1)('8.8.8.8',443)
        except TimeoutError:return
        else:
            writer.close();await writer.wait_closed()
            raise AssertionError('Kernel permit was not required')
    await blocked()
    if Path('/fixture/worker-mode').exists():
        from clipora_v8_firewall_candidate.worker_kernel_service import serve
        await serve(listener,server,Client(channel))
        return
    if Path('/fixture/connect-mode').exists():
        from clipora_v8_firewall_candidate.connect_tls_probe import probe
        report = await probe(listener, server, client, Client(channel), case)
    else:
        report = await run(listener, server_context=server, client_context=client,
                           tls_hostname='example.com', expect_tls_failure=case != 'valid',
                           firewall_adapter=Client(channel))
    await blocked()
    report.update({'kernel_blocks_before_grant_and_after_revoke': True,
                   'controller_uses_inherited_private_channel': True,
                   'case': case, 'hostname_and_CA_verification_enabled': True})
    print(json.dumps(report), flush=True)


def parent():
    if os.environ.get('CLIPORA_NUMERIC_OFFLINE_TEST') != '1' or not Path('/.dockerenv').exists():
        raise PermissionError('Disposable Docker fixture guard required')
    assert os.getuid() == 0
    interfaces = [name for _,name in socket.if_nameindex()]
    assert [n for n in interfaces if int(Path('/sys/class/net',n,'flags').read_text(),16)&1] == ['lo']
    for name in interfaces:
        if name != 'lo':
            assert not re.search(r'\binet6? ',subprocess.check_output(['ip','addr','show','dev',name],text=True))
    assert not subprocess.check_output(['ip','route','show','default']).strip()
    command(['ip','addr','add','8.8.8.8/32','dev','lo'])
    listener = socket.socket()
    listener.bind(('8.8.8.8',443));listener.listen();listener.setblocking(False)
    command(['ip6tables-restore','-w','2'], '*filter\n:INPUT DROP [0:0]\n:FORWARD DROP [0:0]\n:OUTPUT DROP [0:0]\nCOMMIT\n')
    install({})
    controller, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    controller.settimeout(15)
    process = subprocess.Popen([sys.executable,'-B','-u',__file__,'child',str(listener.fileno()),str(peer.fileno())],
                               pass_fds=(listener.fileno(),peer.fileno()))
    peer.close();listener.close()
    leases = {}
    try:
        while packet := controller.recv(4097):
            if len(packet)>4096:raise ValueError('Oversized firewall message')
            operation, d = validate(json.loads(packet))
            previous = leases.get(d['lease_id'])
            if previous is not None and previous != d:raise ValueError('Lease identity mismatch')
            updated = dict(leases)
            if operation == 'grant':
                if len(updated)>=8:raise ValueError('Capacity exceeded')
                updated[d['lease_id']] = d
            else:updated.pop(d['lease_id'],None)
            install(updated)
            leases = updated
            controller.sendall(b'{"ok":true}')
        if process.wait(timeout=3) != 0:raise RuntimeError('Unprivileged TLS probe failed')
        assert not leases
    finally:
        # Deny even when JSON validation, IPC, child, or rule update fails.
        install({})
        controller.close()


if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='child':
        listener=socket.socket(fileno=int(sys.argv[2]))
        channel=socket.socket(fileno=int(sys.argv[3]));channel.settimeout(8)
        drop_privileges(65534,65534)
        asyncio.run(child(listener,channel))
    else:parent()
