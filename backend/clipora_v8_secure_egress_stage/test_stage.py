import asyncio
import unittest
from unittest.mock import patch
import server_stage

REQ = b'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n'

class StageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.srv = await asyncio.start_server(self.handle, '127.0.0.1', 0)
        self.port = self.srv.sockets[0].getsockname()[1]
        self.calls = []
        self.echo_server = await asyncio.start_server(self.echo, '127.0.0.1', 0)

    async def asyncTearDown(self):
        self.srv.close()
        await self.srv.wait_closed()
        self.echo_server.close()
        await self.echo_server.wait_closed()

    async def echo(self, r, w):
        d = await r.read(100)
        w.write(d[::-1]); await w.drain()
        w.close()

    async def handle(self, reader, writer):
        await server_stage.handle(reader, writer, resolver=self.resolve, dial=self.dial)

    async def resolve(self, target):
        return {'host':'example.com','port':443,'addresses':['8.8.8.8']}

    async def dial(self, ip, port):
        self.calls.append((ip, port))
        return await asyncio.open_connection('127.0.0.1', self.echo_server.sockets[0].getsockname()[1])

    async def req(self, request=REQ):
        r,w=await asyncio.open_connection('127.0.0.1',self.port)
        w.write(request);await w.drain()
        return r,w

    async def test_pinned_ip_and_bidirectional_relay(self):
        r,w=await self.req()
        result=await asyncio.wait_for(r.readuntil(b'\r\n\r\n'),3)
        self.assertEqual(result,b'HTTP/1.1 200 Connection Established\r\n\r\n')
        w.write(b'abcd');await w.drain()
        self.assertEqual(await asyncio.wait_for(r.readexactly(4),3),b'dcba')
        self.assertEqual(self.calls,[('8.8.8.8',443)])
        w.close();await w.wait_closed()

    async def test_invalid_ip_never_dialed(self):
        async def bad(_):return {'host':'example.com','port':443,'addresses':['127.0.0.1']}
        self.resolve=bad
        r,w=await self.req()
        self.assertIn(b'400 Bad Request',await asyncio.wait_for(r.read(256),3))
        self.assertEqual(self.calls,[])
        w.close();await w.wait_closed()

    async def test_resolver_mismatch_never_dialed(self):
        async def bad(_):return {'host':'evil.example','port':443,'addresses':['8.8.8.8']}
        self.resolve=bad
        r,w=await self.req()
        self.assertIn(b'400 Bad Request',await asyncio.wait_for(r.read(256),3))
        self.assertEqual(self.calls,[])
        w.close();await w.wait_closed()

    async def test_invalid_port_never_dialed(self):
        r,w=await self.req(REQ.replace(b':443',b':8443'))
        self.assertIn(b'400 Bad Request',await asyncio.wait_for(r.read(256),3))
        self.assertEqual(self.calls,[])
        w.close();await w.wait_closed()

    async def test_default_real_dial_is_forbidden(self):
        async def original_handle(reader,writer):
            await server_stage.handle(reader,writer,resolver=self.resolve)
        self.srv.close();await self.srv.wait_closed()
        self.srv=await asyncio.start_server(original_handle,'127.0.0.1',0)
        self.port=self.srv.sockets[0].getsockname()[1]
        r,w=await self.req()
        self.assertIn(b'403 Forbidden',await asyncio.wait_for(r.read(256),3))
        self.assertEqual(self.calls,[])
        w.close();await w.wait_closed()

if __name__=='__main__':unittest.main()
