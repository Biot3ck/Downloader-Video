"""Candidate gateway transport requiring authenticated TLS to fixed egress.

No default listener, resolver or certificate store is installed by this module.
"""
import asyncio
from contextlib import asynccontextmanager,suppress
import ipaddress
import ssl
from .connect_relay import ConnectRelay
from clipora_v8_secure_egress_stage.connect_policy import validate_connect_target


class HeaderReader:
    def __init__(self,header,reader):self.header,self.reader=header,reader
    async def readuntil(self,separator):
        if self.header is not None:
            header,self.header=self.header,None
            return header
        return await self.reader.readuntil(separator)
    async def read(self,size):return await self.reader.read(size)


class MutualGateway:
    def __init__(self,egress_ip,context,allowed_hosts,*,server_name='egress.clipora.test',capacity=8):
        ip=ipaddress.IPv4Address(egress_ip)
        private=any(ip in ipaddress.IPv4Network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
        if str(ip)!=egress_ip or not private:raise ValueError('Explicit private egress IP required')
        if not isinstance(context,ssl.SSLContext) or not context.check_hostname or context.verify_mode!=ssl.CERT_REQUIRED:
            raise ValueError('Verified TLS context required')
        self.ip,self.context,self.server_name=egress_ip,context,validate_connect_target(server_name+':443')[0]
        self.allowed=frozenset(validate_connect_target(h+':443')[0] for h in allowed_hosts)
        if not self.allowed or len(self.allowed)>128:raise ValueError('Explicit gateway host policy required')
        self.relay=ConnectRelay(self,capacity=capacity)
        self.capacity,self.active=capacity,0

    @asynccontextmanager
    async def connection(self,target):
        host,port=validate_connect_target(target)
        if host not in self.allowed:raise PermissionError('Target not allowed')
        writer=None
        try:
            reader,writer=await asyncio.wait_for(asyncio.open_connection(self.ip,8888,
                ssl=self.context,server_hostname=self.server_name,ssl_handshake_timeout=3),4)
            writer.write(('CONNECT '+target+' HTTP/1.1\r\nHost: '+target+'\r\n\r\n').encode('ascii'))
            await asyncio.wait_for(writer.drain(),3)
            reply=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),4)
            if reply!=b'HTTP/1.1 200 Connection Established\r\n\r\n':raise PermissionError('Egress denied tunnel')
            async with asyncio.timeout(90):
                yield reader,writer,None
        finally:
            if writer is not None:
                writer.close()
                with suppress(OSError,TimeoutError):await asyncio.wait_for(writer.wait_closed(),1)

    async def handle(self,reader,writer):
        admitted=False
        try:
            if self.active>=self.capacity:
                writer.write(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n')
                await asyncio.wait_for(writer.drain(),3);return
            self.active+=1;admitted=True
            raw=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),5)
            if len(raw)>8192:raise ValueError('Oversized gateway request')
            first,*headers=raw[:-4].split(b'\r\n')
            parts=first.split(b' ')
            if len(parts)!=3 or parts[0]!=b'CONNECT' or parts[2] not in (b'HTTP/1.0',b'HTTP/1.1'):
                raise ValueError('Invalid gateway CONNECT')
            # Python/yt-dlp may send HTTP/1.0 CONNECT without Host. Normalize
            # only this case, then reuse the strict shared HTTP/1.1 parser.
            if parts[2]==b'HTTP/1.0' and not any(line.lower().startswith(b'host:') for line in headers):
                headers.append(b'Host: '+parts[1])
            header=b'CONNECT '+parts[1]+b' HTTP/1.1\r\n'+b'\r\n'.join(headers)+b'\r\n\r\n'
            await self.relay.handle(HeaderReader(header,reader),writer)
        except (ValueError,TimeoutError,OSError,asyncio.IncompleteReadError,asyncio.LimitOverrunError):
            with suppress(OSError):
                writer.write(b'HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n');await writer.drain()
        finally:
            writer.close()
            if admitted:self.active-=1
