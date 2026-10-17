import asyncio
import unittest
from unittest.mock import patch
from clipora_v8_firewall_candidate.numeric_dial import NumericDial


class NumericDialTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_destinations_rejected_before_socket_creation(self):
        with patch('clipora_v8_firewall_candidate.numeric_dial.socket.socket') as create:
            for ip,port in [('example.com',443),('127.0.0.1',443),('169.254.169.254',443),
                            ('8.8.8.8',80),('8.8.8.8',True),('::ffff:8.8.8.8',443),
                            ('2001:4860:4860:0:0:0:0:8888',443)]:
                with self.subTest(ip=ip,port=port), self.assertRaises(ValueError):
                    await NumericDial()(ip,port)
            create.assert_not_called()

    async def test_cancel_during_connect_closes_socket(self):
        loop=asyncio.get_running_loop();entered=asyncio.Event()
        async def connect(raw,peer):entered.set();await asyncio.Event().wait()
        with patch('clipora_v8_firewall_candidate.numeric_dial.socket.socket') as create, patch.object(loop,'sock_connect',connect):
            task=asyncio.create_task(NumericDial()('8.8.8.8',443))
            await entered.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            create.return_value.close.assert_called_once()

    async def test_connect_timeout_closes_socket(self):
        loop=asyncio.get_running_loop()
        async def connect(*a):await asyncio.Event().wait()
        with patch('clipora_v8_firewall_candidate.numeric_dial.socket.socket') as create, patch.object(loop,'sock_connect',connect):
            with self.assertRaises(TimeoutError):await NumericDial(timeout=.01)('8.8.8.8',443)
            create.return_value.close.assert_called_once()

    async def test_cancel_during_stream_handoff_aborts_transport(self):
        loop=asyncio.get_running_loop();entered=asyncio.Event()
        from unittest.mock import Mock
        transport=Mock()
        async def connect(*a):pass
        async def handoff(factory,**kw):
            protocol=factory();protocol._transport=transport
            entered.set();await asyncio.Event().wait()
        with patch('clipora_v8_firewall_candidate.numeric_dial.socket.socket') as create, patch.object(loop,'sock_connect',connect), patch.object(loop,'create_connection',handoff):
            create.return_value.getpeername.return_value=('8.8.8.8',443)
            task=asyncio.create_task(NumericDial()('8.8.8.8',443))
            await entered.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            transport.abort.assert_called_once();create.return_value.close.assert_called_once()
