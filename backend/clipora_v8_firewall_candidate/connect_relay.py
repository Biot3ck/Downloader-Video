"""Bounded CONNECT handler for an explicitly supplied Broker; no listener CLI."""
import asyncio
from contextlib import suppress
from clipora_v8_secure_egress_stage.http_parser import read_connect_request


class ConnectRelay:
    def __init__(self, broker=None, *, capacity=8, byte_limit=64*1024*1024, idle_timeout=15):
        if type(capacity) is not int or not 1<=capacity<=32:raise ValueError('Invalid relay capacity')
        if type(byte_limit) is not int or not 1<=byte_limit<=64*1024*1024:raise ValueError('Invalid relay byte limit')
        if type(idle_timeout) not in (int,float) or not 0<idle_timeout<=15:raise ValueError('Invalid idle deadline')
        self.broker,self.capacity,self.byte_limit,self.idle_timeout=broker,capacity,byte_limit,idle_timeout
        self.active=0

    async def handle(self, reader, writer):
        established=False
        admitted=False
        code=b'400 Bad Request'
        try:
            if self.active>=self.capacity:
                code=b'503 Service Unavailable';return
            self.active+=1;admitted=True
            if self.broker is None:
                code=b'403 Forbidden';return
            target=await read_connect_request(reader)
            async with self.broker.connection(target) as (upreader,upwriter,_):
                # Grant, numeric connect and peer verification have completed.
                writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                await asyncio.wait_for(writer.drain(),self.idle_timeout)
                established=True
                transferred=0
                async def pump(source,destination):
                    nonlocal transferred
                    while True:
                        chunk=await asyncio.wait_for(source.read(32768),self.idle_timeout)
                        if not chunk:
                            if destination.can_write_eof():destination.write_eof()
                            await asyncio.wait_for(destination.drain(),self.idle_timeout)
                            return
                        transferred+=len(chunk)
                        if transferred>self.byte_limit:raise ValueError('Relay budget exceeded')
                        destination.write(chunk)
                        await asyncio.wait_for(destination.drain(),self.idle_timeout)
                tasks=[asyncio.create_task(pump(reader,upwriter)),asyncio.create_task(pump(upreader,writer))]
                try:await asyncio.gather(*tasks)
                finally:
                    for task in tasks:
                        if not task.done():task.cancel()
                    cancelled=False
                    while any(not task.done() for task in tasks):
                        try:await asyncio.wait(tasks)
                        except asyncio.CancelledError:cancelled=True
                    for task in tasks:
                        if not task.cancelled():task.exception()
                    if cancelled:raise asyncio.CancelledError
        except PermissionError:code=b'403 Forbidden'
        except (ValueError,TypeError,KeyError,UnicodeError,asyncio.IncompleteReadError):pass
        except (TimeoutError,OSError,RuntimeError):code=b'502 Bad Gateway'
        finally:
            if not established:
                with suppress(OSError,TimeoutError):
                    writer.write(b'HTTP/1.1 '+code+b'\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                    await asyncio.wait_for(writer.drain(),self.idle_timeout)
            try:
                writer.close()
                with suppress(OSError,TimeoutError):await asyncio.wait_for(writer.wait_closed(),1)
            finally:
                if admitted:self.active-=1
