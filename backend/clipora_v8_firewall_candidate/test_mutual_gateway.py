import asyncio
import ssl
import unittest
from clipora_v8_firewall_candidate.mutual_gateway import MutualGateway


class MutualGatewayTests(unittest.IsolatedAsyncioTestCase):
    def gateway(self):return MutualGateway('10.4.0.2',ssl.create_default_context(),['example.com'])
    async def test_unverified_context_and_public_egress_rejected(self):
        with self.assertRaises(ValueError):MutualGateway('8.8.8.8',ssl.create_default_context(),['example.com'])
        insecure=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);insecure.check_hostname=False;insecure.verify_mode=ssl.CERT_NONE
        with self.assertRaises(ValueError):MutualGateway('10.4.0.2',insecure,['example.com'])
    async def test_http_10_normalization_preserves_body_stream(self):
        gateway=self.gateway();observed=[]
        async def handle(reader,writer):
            observed.append(await reader.readuntil(b'\r\n\r\n'))
            observed.append(await reader.read(4))
        gateway.relay.handle=handle
        server=await asyncio.start_server(gateway.handle,'127.0.0.1',0)
        try:
            reader,writer=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
            writer.write(b'CONNECT example.com:443 HTTP/1.0\r\n\r\nTLS!');await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.read(),1),b'')
            writer.close();await writer.wait_closed()
            self.assertEqual(observed,[b'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n',b'TLS!'])
            self.assertEqual(gateway.active,0)
        finally:server.close();await server.wait_closed()
    async def test_disallowed_hostname_never_opens_upstream(self):
        from unittest.mock import patch
        gateway=self.gateway()
        with patch('asyncio.open_connection',side_effect=AssertionError('Upstream opened')):
            with self.assertRaises(PermissionError):
                async with gateway.connection('other.example:443'):pass
