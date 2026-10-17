import asyncio
from contextlib import asynccontextmanager
import unittest
from clipora_v8_firewall_candidate.connect_relay import ConnectRelay


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_denies_without_reading_or_dns(self):
        relay=ConnectRelay()
        server=await asyncio.start_server(relay.handle,'127.0.0.1',0)
        try:
            reader,writer=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
            self.assertTrue((await asyncio.wait_for(reader.read(),1)).startswith(b'HTTP/1.1 403'))
            writer.close();await writer.wait_closed()
        finally:server.close();await server.wait_closed()

    async def test_malformed_connect_never_enters_broker(self):
        class Broker:
            def connection(self,target):raise AssertionError('Malformed request reached broker')
        relay=ConnectRelay(Broker())
        server=await asyncio.start_server(relay.handle,'127.0.0.1',0,limit=8192)
        try:
            for raw in (b'GET / HTTP/1.1\r\nHost: example.com\r\n\r\n',
                        b'CONNECT example.com:443 HTTP/1.1\r\nHost: other.com:443\r\n\r\n',
                        b'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\nContent-Length: 1\r\n\r\n'):
                reader,writer=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
                writer.write(raw);await writer.drain()
                self.assertTrue((await asyncio.wait_for(reader.read(),1)).startswith(b'HTTP/1.1 400'))
                writer.close();await writer.wait_closed()
        finally:server.close();await server.wait_closed()

    async def test_byte_budget_closes_and_cleans_up(self):
        closed=asyncio.Event()
        async def echo(reader,writer):
            try:
                while data:=await reader.read(1024):writer.write(data);await writer.drain()
            finally:writer.close();await writer.wait_closed()
        upstream=await asyncio.start_server(echo,'127.0.0.1',0)
        class Broker:
            @asynccontextmanager
            async def connection(self,target):
                reader,writer=await asyncio.open_connection('127.0.0.1',upstream.sockets[0].getsockname()[1])
                try:yield reader,writer,None
                finally:writer.close();await writer.wait_closed();closed.set()
        relay=ConnectRelay(Broker(),byte_limit=4,idle_timeout=.05)
        server=await asyncio.start_server(relay.handle,'127.0.0.1',0,limit=8192)
        writer=None
        try:
            reader,writer=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
            writer.write(b'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n')
            await writer.drain()
            self.assertIn(b'200',await reader.readuntil(b'\r\n\r\n'))
            writer.write(b'12345');await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.read(),1),b'')
            await asyncio.wait_for(closed.wait(),1)
            await asyncio.sleep(0)
            self.assertEqual(relay.active,0)
        finally:
            if writer is not None:writer.close();await writer.wait_closed()
            server.close();upstream.close();await server.wait_closed();await upstream.wait_closed()

    async def test_admission_rejects_without_waiting_for_slot(self):
        class Broker:
            def connection(self,target):raise AssertionError('No request was sent')
        relay=ConnectRelay(Broker(),capacity=1)
        server=await asyncio.start_server(relay.handle,'127.0.0.1',0,limit=8192)
        writers=[]
        try:
            first,writer=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1]);writers.append(writer)
            while relay.active!=1:await asyncio.sleep(0)
            second,writer=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1]);writers.append(writer)
            self.assertTrue((await asyncio.wait_for(second.read(),1)).startswith(b'HTTP/1.1 503'))
            writers[0].close();await writers[0].wait_closed()
            async with asyncio.timeout(1):
                while relay.active:await asyncio.sleep(.01)
        finally:
            for writer in writers:writer.close()
            server.close();await server.wait_closed()
