"""Strict offline fixture policy. This module cannot authorize public egress."""
import ipaddress


def address(value, network):
    if not isinstance(value, str):
        raise ValueError('Address must be a string')
    ip = ipaddress.IPv4Address(value)
    if str(ip) != value or ip not in network or ip in (network.network_address, network.broadcast_address):
        raise ValueError('Address outside configured network')
    return str(ip)


def validate(data):
    if not isinstance(data, dict) or set(data) != {'mode', 'network', 'gateway_ip', 'destination_ip', 'destination_port', 'uid', 'gid'}:
        raise ValueError('Unexpected or missing configuration fields')
    if data['mode'] != 'offline-fixture':
        raise ValueError('Only offline fixture mode exists')
    network = ipaddress.IPv4Network(data['network'], strict=True)
    private_blocks = [ipaddress.IPv4Network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
    if not any(network.subnet_of(n) for n in private_blocks) or not 16 <= network.prefixlen <= 29:
        raise ValueError('Only bounded RFC1918 fixture networks permitted')
    gateway = address(data['gateway_ip'], network)
    destination = address(data['destination_ip'], network)
    if gateway == destination:
        raise ValueError('Gateway and destination must differ')
    if type(data['destination_port']) is not int or not 1024 <= data['destination_port'] <= 65535:
        raise ValueError('Invalid fixture TCP port')
    for name in ('uid', 'gid'):
        if type(data[name]) is not int or not 1 <= data[name] <= 65534:
            raise ValueError('Non-root uid/gid required')
    return {**data, 'network': str(network), 'gateway_ip': gateway, 'destination_ip': destination}


def rules(data):
    p = validate(data)
    ipv4 = '\n'.join([
        '*filter', ':INPUT DROP [0:0]', ':FORWARD DROP [0:0]', ':OUTPUT DROP [0:0]',
        '-A INPUT -m conntrack --ctstate ESTABLISHED -j ACCEPT',
        f'-A INPUT -s {p["gateway_ip"]}/32 -p tcp --dport 8888 -m conntrack --ctstate NEW -j ACCEPT',
        '-A OUTPUT -m conntrack --ctstate ESTABLISHED -j ACCEPT',
        f'-A OUTPUT -d {p["destination_ip"]}/32 -p tcp --dport {p["destination_port"]} -m conntrack --ctstate NEW -j ACCEPT',
        'COMMIT', '',
    ])
    ipv6 = '*filter\n:INPUT DROP [0:0]\n:FORWARD DROP [0:0]\n:OUTPUT DROP [0:0]\nCOMMIT\n'
    return ipv4, ipv6
