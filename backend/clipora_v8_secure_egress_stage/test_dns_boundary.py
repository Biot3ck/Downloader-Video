"""Synthetic DNS tests: no public DNS requests are sent."""
import asyncio
import unittest
from unittest.mock import patch
import dns.resolver
import dns.exception
import connect_policy
import dns_policy_v2
import server_stage


class DNSBoundaryTests(unittest.TestCase):
    def test_ambiguous_authorities_rejected(self):
        for host in ('127.1', '2130706433', '0x7f000001', '0177.0.0.1',
                     'example.com.', '-foo.example', 'foo-.example',
                     'a..example', 'a'*64+'.com', 'localhost', 'foo_bar.com'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                connect_policy.validate_connect_target(host + ':443')

    def test_valid_hostname_canonicalization(self):
        self.assertEqual(connect_policy.validate_connect_target('CDN-1.Example.COM:443'), ('cdn-1.example.com',443))

    def resolve(self, records):
        class FakeResolver:
            def resolve(self, host, kind):
                value = records[kind]
                if isinstance(value, Exception): raise value
                return value
        with patch.object(dns_policy_v2.dns.resolver, 'Resolver', FakeResolver):
            return dns_policy_v2.resolve_safe_host_v2('example.com')

    def test_all_answers_must_be_public(self):
        with self.assertRaises(ValueError):
            self.resolve({'A':['8.8.8.8'], 'AAAA':['::1']})

    def test_metadata_answer_rejected(self):
        with self.assertRaises(ValueError):
            self.resolve({'A':['169.254.169.254'], 'AAAA':dns.resolver.NoAnswer()})

    def test_nxdomain_discards_partial_result(self):
        with self.assertRaises(ValueError):
            self.resolve({'A':['8.8.8.8'], 'AAAA':dns.resolver.NXDOMAIN()})

    def test_timeout_discards_partial_result(self):
        with self.assertRaises(ValueError):
            self.resolve({'A':['8.8.8.8'], 'AAAA':dns.exception.Timeout()})

    def test_no_aaaa_answer_can_use_safe_a(self):
        self.assertEqual(self.resolve({'A':['8.8.8.8','8.8.8.8'], 'AAAA':dns.resolver.NoAnswer()}), ['8.8.8.8'])

    def test_safe_dual_stack(self):
        self.assertEqual(self.resolve({'A':['8.8.8.8'], 'AAAA':['2606:4700::1111']}), ['2606:4700::1111','8.8.8.8'])


class DenyBeforeDNSTests(unittest.IsolatedAsyncioTestCase):
    async def simulate_pinned_failure(self, addresses):
        calls=[]
        async def resolve(target):
            calls.append(('resolve', target))
            return {'host':'example.com','port':443,'addresses':addresses}
        async def dial(ip,port):
            calls.append(('dial',ip,port))
            raise OSError('Synthetic connect failure')
        reader=asyncio.StreamReader()
        reader.feed_data(b'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n')
        reader.feed_eof()
        class Writer:
            data=b''
            def write(self,data):self.data+=data
            async def drain(self):pass
            def close(self):pass
            async def wait_closed(self):pass
        writer=Writer()
        await server_stage.handle(reader,writer,resolver=resolve,dial=dial)
        return calls,writer.data

    async def test_numeric_snapshot_used_once_without_fallback(self):
        calls,reply=await self.simulate_pinned_failure(['8.8.8.8','1.1.1.1'])
        self.assertEqual(calls,[('resolve','example.com:443'),('dial','8.8.8.8',443)])
        self.assertIn(b'502 Bad Gateway',reply)

    async def test_all_addresses_validated_before_dial(self):
        calls,reply=await self.simulate_pinned_failure(['8.8.8.8','127.0.0.1'])
        self.assertEqual(calls,[('resolve','example.com:443')])
        self.assertIn(b'400 Bad Request',reply)

    async def test_default_transport_denied_without_resolving(self):
        calls=[]
        async def resolve(target):
            calls.append(target)
            raise AssertionError('Default denied transport must not resolve')
        reader=asyncio.StreamReader()
        reader.feed_data(b'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n')
        reader.feed_eof()
        class Writer:
            data=b''
            def write(self,data):self.data+=data
            async def drain(self):pass
            def close(self):pass
            async def wait_closed(self):pass
        writer=Writer()
        await server_stage.handle(reader,writer,resolver=resolve)
        self.assertEqual(calls,[])
        self.assertIn(b'403 Forbidden',writer.data)


if __name__=='__main__':unittest.main()
