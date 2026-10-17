"""Numeric TCP transport for explicitly assembled broker candidates.

No default installation. TLS remains the responsibility of the CONNECT client.
"""
import asyncio
import ipaddress
import socket
from clipora_v8_secure_egress_stage.ip_policy import validate_destination_ip


class NumericDial:
    def __init__(self, *, timeout=3):
        if type(timeout) not in (int, float) or not 0 < timeout <= 4:
            raise ValueError('Invalid numeric dial deadline')
        self.timeout = timeout

    async def __call__(self, ip, port):
        if type(ip) is not str or type(port) is not int or port != 443:
            raise ValueError('Only validated numeric IP and port 443 accepted')
        canonical = validate_destination_ip(ip)
        if canonical != ip:raise ValueError('Canonical numeric address required')
        address = ipaddress.ip_address(canonical)
        family = socket.AF_INET if address.version == 4 else socket.AF_INET6
        raw = socket.socket(family, socket.SOCK_STREAM)
        raw.setblocking(False)
        protocol = transport = None
        try:
            async with asyncio.timeout(self.timeout):
                loop = asyncio.get_running_loop()
                # sock_connect uses inet_pton for this canonical numeric address.
                # No hostname, fallback address, or resolver is supplied.
                await loop.sock_connect(raw, (canonical, port))
                peer = raw.getpeername()
                if ipaddress.ip_address(peer[0]) != address or peer[1] != port:
                    raise PermissionError('Numeric socket peer mismatch')
                reader = asyncio.StreamReader(limit=65536)
                protocol = asyncio.StreamReaderProtocol(reader)
                transport, _ = await loop.create_connection(lambda: protocol, sock=raw)
                writer = asyncio.StreamWriter(transport, protocol, reader, loop)
                return reader, writer
        except BaseException:
            # StreamReaderProtocol records connection_made even if cancellation
            # happens while create_connection is handing ownership to us.
            owned = transport or (getattr(protocol, '_transport', None) if protocol else None)
            if owned is not None:owned.abort()
            raw.close()
            raise
