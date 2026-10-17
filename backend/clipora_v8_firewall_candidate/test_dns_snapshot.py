import asyncio
import unittest
import dns.message
import dns.name
import dns.rdataclass
import dns.rdatatype
import dns.resolver
import dns.rrset
from clipora_v8_firewall_candidate.dns_snapshot import SnapshotResolver
from clipora_v8_firewall_candidate.binding import Broker
from clipora_v8_firewall_candidate.test_binding import Firewall, Writer


def answer(family, values=(), ttl=60, alias=None, alias_ttl=5):
    query = dns.message.make_query('example.com.', family)
    response = dns.message.make_response(query)
    name = 'example.com.'
    if alias:
        response.answer.append(dns.rrset.from_text(name, alias_ttl, 'IN', 'CNAME', alias))
        name = alias
    if values:response.answer.append(dns.rrset.from_text(name, ttl, 'IN', family, *values))
    else:response.authority.append(dns.rrset.from_text('example.com.', ttl, 'IN', 'SOA',
        'ns.example.com. hostmaster.example.com. 1 60 60 60 60'))
    response = dns.message.from_wire(response.to_wire())
    return dns.resolver.Answer(query.question[0].name, dns.rdatatype.from_text(family), dns.rdataclass.IN, response)


class SnapshotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = 100.0
        self.calls = []
        self.answers = {'A': answer('A', ['8.8.8.8']), 'AAAA': answer('AAAA')}
        async def query(name, family, **kw):
            self.calls.append((name, family, kw))
            result = self.answers[family]
            if isinstance(result, Exception):raise result
            return result
        self.resolver = SnapshotResolver(query, clock=lambda:self.now)

    async def test_default_denied(self):
        with self.assertRaises(PermissionError):await SnapshotResolver()('example.com')

    async def test_full_snapshot_drives_broker_without_second_lookup(self):
        firewall = Firewall(); dials = []
        async def dial(ip, port):
            dials.append((ip, port));return None, Writer((ip, port))
        broker = Broker(['example.com'], self.resolver, firewall, dial, clock=lambda:self.now)
        async with broker.connection('example.com:443') as (_, _, dest):
            self.assertEqual(dest.ip, '8.8.8.8')
        self.assertEqual([c[1] for c in self.calls], ['A','AAAA'])
        self.assertTrue(all(c[2]['search'] is False for c in self.calls))
        self.assertEqual(dials, [('8.8.8.8',443)])
        self.assertEqual(firewall.grants, firewall.revoked)

    async def test_second_family_error_invalidates_first(self):
        for exc in (dns.resolver.NXDOMAIN(), dns.resolver.NoNameservers(), dns.exception.Timeout()):
            self.answers['AAAA'] = exc
            with self.assertRaises(ValueError):await self.resolver('example.com')
            self.assertEqual(self.resolver.active, 0)

    async def test_private_mixed_answer_rejected_before_grant(self):
        self.answers['AAAA'] = answer('AAAA', ['::1'])
        firewall = Firewall()
        broker = Broker(['example.com'], self.resolver, firewall, lambda *a:None)
        with self.assertRaises(ValueError):
            async with broker.connection('example.com:443'):pass
        self.assertEqual(firewall.grants, [])

    async def test_shortest_cname_ttl_and_query_time(self):
        self.answers = {f: answer(f, ['8.8.8.8'] if f=='A' else [],
                                  alias='cdn.example.com.', alias_ttl=5) for f in ('A','AAAA')}
        old = self.resolver.query
        async def query(*a, **kw):
            result = await old(*a, **kw);self.now += 1;return result
        self.resolver.query = query
        ttl = (await self.resolver('example.com'))['ttl']
        self.assertGreater(ttl, 2.5)
        self.assertLessEqual(ttl, 3)

    async def test_cached_answer_expiration_is_not_refreshed(self):
        self.resolver.wall_clock = lambda:100.0
        self.answers['A'].expiration = 102.0
        snapshot = await self.resolver('example.com')
        self.assertEqual(snapshot['ttl'], 2.0)
        self.answers['A'].expiration = 99.0
        with self.assertRaisesRegex(ValueError, 'Cached DNS answer expired'):
            await self.resolver('example.com')

    async def test_inconsistent_alias_rejected(self):
        self.answers['AAAA'] = answer('AAAA', alias='different.example.com.')
        with self.assertRaises(ValueError):await self.resolver('example.com')

    async def test_zero_ttl_empty_and_wrong_question_rejected(self):
        for replacement in (answer('A', ['8.8.8.8'], ttl=0), answer('AAAA', ['2606:4700:4700::1111'])):
            self.answers['A'] = replacement
            with self.assertRaises(ValueError):await self.resolver('example.com')
        self.answers['A'] = answer('A')
        with self.assertRaises(ValueError):await self.resolver('example.com')

    async def test_capacity_cancel_timeout_release(self):
        entered = asyncio.Event()
        async def query(*a, **kw):entered.set();await asyncio.Event().wait()
        self.resolver.query = query;self.resolver.capacity = 1
        task = asyncio.create_task(self.resolver('example.com'))
        await entered.wait()
        with self.assertRaises(RuntimeError):await self.resolver('example.com')
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(self.resolver.active, 0)
        self.resolver.timeout = .01
        with self.assertRaises(TimeoutError):await self.resolver('example.com')
        self.assertEqual(self.resolver.active, 0)
