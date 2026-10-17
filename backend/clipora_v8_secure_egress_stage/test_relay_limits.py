"""Resource-limit regression tests. No sockets, DNS queries or Docker needed."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server_stage as stage


class Reader:
    def __init__(self, chunks=(), *, blocked=False):
        self.chunks = list(chunks)
        self.blocked = blocked
        self.cancelled = asyncio.Event()
        self.started = asyncio.Event()

    async def read(self, size):
        self.started.set()
        if self.blocked:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
        return self.chunks.pop(0) if self.chunks else b''


class Writer:
    def __init__(self, *, blocked=False):
        self.data = bytearray()
        self.blocked = blocked
        self.eof = False

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        if self.blocked:
            await asyncio.Event().wait()

    def write_eof(self):
        self.eof = True


class RelayLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_transfer_reports_limit_failure(self):
        budget = {'bytes': 0, 'lock': asyncio.Lock()}
        with patch.object(stage, 'MAX_TUNNEL_BYTES', 4):
            with self.assertRaises(ValueError):
                await stage.transfer(Reader([b'12345']), Writer(), budget)

    async def test_byte_limit_cancels_opposite_reader(self):
        stalled = Reader(blocked=True)
        destination = Writer()
        with patch.object(stage, 'MAX_TUNNEL_BYTES', 4):
            with self.assertRaises(ValueError):
                await stage.relay_session(Reader([b'12345']), Writer(), stalled, destination)
        self.assertEqual(destination.data, b'')
        self.assertTrue(stalled.cancelled.is_set())

    async def test_budget_is_shared_between_directions(self):
        client, upstream = Writer(), Writer()
        with patch.object(stage, 'MAX_TUNNEL_BYTES', 5):
            with self.assertRaises(ValueError):
                await stage.relay_session(Reader([b'abc']), client, Reader([b'def']), upstream)
        self.assertLessEqual(len(client.data) + len(upstream.data), 5)

    async def test_exact_budget_and_half_close_succeed(self):
        client, upstream = Writer(), Writer()
        with patch.object(stage, 'MAX_TUNNEL_BYTES', 6):
            await stage.relay_session(Reader([b'abc']), client, Reader([b'def']), upstream)
        self.assertEqual(client.data, b'def')
        self.assertEqual(upstream.data, b'abc')
        self.assertTrue(client.eof and upstream.eof)

    async def test_idle_timeout_cleans_up_both_directions(self):
        first, second = Reader(blocked=True), Reader(blocked=True)
        with patch.object(stage, 'IDLE_TIMEOUT', .02):
            with self.assertRaises(TimeoutError):
                await stage.relay_session(first, Writer(), second, Writer())
        self.assertTrue(first.cancelled.is_set())
        self.assertTrue(second.cancelled.is_set())

    async def test_backpressure_timeout_cancels_opposite_reader(self):
        stalled = Reader(blocked=True)
        with patch.object(stage, 'IDLE_TIMEOUT', .02):
            with self.assertRaises(TimeoutError):
                await stage.relay_session(Reader([b'abc']), Writer(), stalled, Writer(blocked=True))
        self.assertTrue(stalled.cancelled.is_set())

    async def test_session_deadline_cleans_up_both_directions(self):
        first, second = Reader(blocked=True), Reader(blocked=True)
        with patch.object(stage, 'SESSION_TIMEOUT', .02):
            with self.assertRaises(TimeoutError):
                await stage.relay_session(first, Writer(), second, Writer())
        self.assertTrue(first.cancelled.is_set())
        self.assertTrue(second.cancelled.is_set())

    async def test_parent_cancellation_cleans_up_both_directions(self):
        first, second = Reader(blocked=True), Reader(blocked=True)
        task = asyncio.create_task(stage.relay_session(first, Writer(), second, Writer()))
        await first.started.wait()
        await second.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(first.cancelled.is_set())
        self.assertTrue(second.cancelled.is_set())


class RelaySocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_limit_closes_client_and_upstream_connections(self):
        upstream_closed = asyncio.Event()
        connections = []

        async def upstream_handle(reader, writer):
            connections.append(writer)
            try:
                await reader.read()
                upstream_closed.set()
            finally:
                writer.close()
                await writer.wait_closed()

        upstream = await asyncio.start_server(upstream_handle, '127.0.0.1', 0)
        upstream_port = upstream.sockets[0].getsockname()[1]

        async def resolver(target):
            return {'host': 'example.com', 'port': 443, 'addresses': ['8.8.8.8']}

        async def dial(ip, port):
            self.assertEqual((ip, port), ('8.8.8.8', 443))
            return await asyncio.open_connection('127.0.0.1', upstream_port)

        handlers = set()
        async def handle(reader, writer):
            task = asyncio.current_task()
            handlers.add(task)
            try:
                await stage.handle(reader, writer, resolver=resolver, dial=dial)
            finally:
                handlers.discard(task)

        proxy = await asyncio.start_server(handle, '127.0.0.1', 0)
        writer = None
        try:
            with patch.object(stage, 'MAX_TUNNEL_BYTES', 4):
                reader, writer = await asyncio.open_connection('127.0.0.1', proxy.sockets[0].getsockname()[1])
                writer.write(b'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n')
                await writer.drain()
                reply = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 1)
                self.assertIn(b'200 Connection Established', reply)
                writer.write(b'12345')
                await writer.drain()
                self.assertEqual(await asyncio.wait_for(reader.read(), 1), b'')
                await asyncio.wait_for(upstream_closed.wait(), 1)
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()
            proxy.close()
            upstream.close()
            await proxy.wait_closed()
            await upstream.wait_closed()
            for connection in connections:
                connection.close()
            pending = list(handlers)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)


if __name__ == '__main__':
    unittest.main()
