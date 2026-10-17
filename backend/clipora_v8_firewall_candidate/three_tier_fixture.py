"""Strictly offline three-tier Docker fixture, not a deployment controller."""
import asyncio
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

from .kernel_tls_fixture import command, validate, child


def config():
    raw=Path('/fixture/three-tier.json').read_text()
    if len(raw)>4096:raise ValueError('Oversized fixture config')
    value=json.loads(raw)
    if not isinstance(value,dict) or set(value)!={'mode','subnet','gateway_ip','egress_ip'}:
        raise ValueError('Invalid fixture config')
    if value['mode']!='offline-three-tier':raise ValueError('Only offline fixture mode')
    net=ipaddress.IPv4Network(value['subnet'],strict=True)
    if not 16<=net.prefixlen<=29 or not any(net.subnet_of(ipaddress.IPv4Network(n)) for n in
        ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):raise ValueError('Fixture network required')
    for field in ('gateway_ip','egress_ip'):
        ip=ipaddress.IPv4Address(value[field])
        if str(ip)!=value[field] or ip not in net or ip in (net.network_address,net.broadcast_address):
            raise ValueError('Invalid fixture endpoint')
    if value['gateway_ip']==value['egress_ip']:raise ValueError('Distinct fixture endpoints required')
    return value


def install(leases,p):
    gateway=p['gateway_ip']
    lines=['*filter',':INPUT DROP [0:0]',':FORWARD DROP [0:0]',':OUTPUT DROP [0:0]',
        '-A INPUT -i lo -s 127.0.0.0/8 -d 127.0.0.0/8 -j ACCEPT',
        '-A OUTPUT -o lo -s 127.0.0.0/8 -d 127.0.0.0/8 -j ACCEPT',
        f'-A INPUT -i eth0 -s {gateway}/32 -p tcp --dport 8888 -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT',
        f'-A OUTPUT -o eth0 -d {gateway}/32 -p tcp --sport 8888 -m conntrack --ctstate ESTABLISHED -j ACCEPT']
    if leases:
        for chain,interface in (('INPUT','-i'),('OUTPUT','-o')):
            lines += [f'-A {chain} {interface} lo -d 8.8.8.8/32 -p tcp --dport 443 -j ACCEPT',
                f'-A {chain} {interface} lo -s 8.8.8.8/32 -p tcp --sport 443 -m conntrack --ctstate ESTABLISHED -j ACCEPT']
    command(['iptables-restore','-w','2'],'\n'.join([*lines,'COMMIT','']))


def parent():
    if os.environ.get('CLIPORA_THREE_TIER_OFFLINE_TEST')!='1' or not Path('/.dockerenv').exists():
        raise PermissionError('Disposable Docker fixture guard required')
    assert os.getuid()==0
    p=config()
    interfaces=[name for _,name in socket.if_nameindex()]
    assert sorted(n for n in interfaces if int(Path('/sys/class/net',n,'flags').read_text(),16)&1)==['eth0','lo']
    routes=Path('/proc/net/route').read_text().splitlines()[1:]
    assert not any(row.split()[1]=='00000000' and row.split()[7]=='00000000' for row in routes)
    eth=subprocess.check_output(['ip','-4','addr','show','dev','eth0'],text=True)
    assert re.findall(r'\binet ([0-9.]+)/',eth)==[p['egress_ip']]
    command(['ip','addr','add','8.8.8.8/32','dev','lo'])
    listener=socket.socket();listener.bind(('8.8.8.8',443));listener.listen();listener.setblocking(False)
    command(['ip6tables-restore','-w','2'],'*filter\n:INPUT DROP [0:0]\n:FORWARD DROP [0:0]\n:OUTPUT DROP [0:0]\nCOMMIT\n')
    install({},p)
    controller,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    controller.settimeout(20)
    proc=subprocess.Popen([sys.executable,'-B','-u','-m','clipora_v8_firewall_candidate.three_tier_fixture',
        'child',str(listener.fileno()),str(peer.fileno())],pass_fds=(listener.fileno(),peer.fileno()))
    peer.close();listener.close();leases={}
    try:
        while packet:=controller.recv(4097):
            if len(packet)>4096:raise ValueError('Oversized IPC')
            operation,d=validate(json.loads(packet))
            previous=leases.get(d['lease_id'])
            if previous is not None and previous!=d:raise ValueError('Lease identity mismatch')
            updated=dict(leases)
            if operation=='grant':
                if len(updated)>=8:raise ValueError('Lease capacity exceeded')
                updated[d['lease_id']]=d
            else:updated.pop(d['lease_id'],None)
            install(updated,p);leases=updated;controller.sendall(b'{"ok":true}')
        assert proc.wait(timeout=3)==0 and not leases
    finally:install({},p);controller.close()


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='child':
        from .kernel_tls_fixture import drop_privileges
        listener=socket.socket(fileno=int(sys.argv[2]))
        channel=socket.socket(fileno=int(sys.argv[3]));channel.settimeout(8)
        drop_privileges(65534,65534)
        asyncio.run(child(listener,channel))
    else:parent()
