import asyncio
from dataclasses import FrozenInstanceError
import unittest
from clipora_v8_firewall_candidate.binding import Broker


class Firewall:
    def __init__(self):self.grants=[];self.revoked=[];self.fail_grant=False;self.fail_revoke=False
    async def grant(self,destination):
        self.grants.append(destination)
        if self.fail_grant:raise OSError('simulated partial grant')
    async def revoke(self,destination):
        self.revoked.append(destination)
        if self.fail_revoke:raise OSError('simulated failed revoke')


class Writer:
    def __init__(self,peer):self.peer=peer;self.closed=False
    def get_extra_info(self,name):return self.peer
    def close(self):self.closed=True
    async def wait_closed(self):pass


class BindingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now=100.0;self.queries=[];self.dials=[];self.writers=[];self.firewall=Firewall()
        self.snapshot={'host':'example.com','A':['8.8.8.8'],'AAAA':[],'ttl':30}
        async def resolver(host):self.queries.append(host);return self.snapshot
        async def dial(ip,port):
            self.dials.append((ip,port));writer=Writer((ip,port));self.writers.append(writer);return object(),writer
        self.resolver,self.dial=resolver,dial
        self.broker=Broker(['example.com'],resolver,self.firewall,dial,clock=lambda:self.now)
    async def test_default_denial_precedes_dns(self):
        broker=Broker(['example.com'],self.resolver)
        with self.assertRaises(PermissionError):
            async with broker.connection('example.com:443'):pass
        self.assertEqual(self.queries,[])
    async def test_same_immutable_destination_for_firewall_socket_and_cleanup(self):
        async with self.broker.connection('example.com:443') as (_,writer,destination):
            self.assertEqual(self.dials,[('8.8.8.8',443)])
            self.assertIs(destination,self.firewall.grants[0])
            with self.assertRaises(FrozenInstanceError):destination.ip='1.1.1.1'
            self.snapshot['A'][0]='1.1.1.1'
            self.assertEqual(destination.addresses,('8.8.8.8',))
        self.assertEqual(self.queries,['example.com'])
        self.assertIs(destination,self.firewall.revoked[0]);self.assertTrue(writer.closed)
        self.assertEqual(self.broker.active,0)
    async def test_bad_dns_sets_never_reach_firewall(self):
        cases=[{'A':['8.8.8.8','127.0.0.1']},{'AAAA':['::1']},{'AAAA':['::ffff:8.8.8.8']},
               {'AAAA':['8.8.8.8']},{'host':'other.example'},{'ttl':0},{'ttl':float('nan')},
               {'A':[],'AAAA':[]},{'A':['169.254.169.254']},{'A':['8.8.8.8']*33}]
        for change in cases:
            self.snapshot={'host':'example.com','A':['8.8.8.8'],'AAAA':[],'ttl':30,**change}
            with self.subTest(change=change),self.assertRaises(ValueError):
                async with self.broker.connection('example.com:443'):pass
        self.snapshot={'host':'example.com','A':['8.8.8.8'],'ttl':30}
        with self.assertRaises(ValueError):
            async with self.broker.connection('example.com:443'):pass
        self.assertEqual(self.firewall.grants,[]);self.assertEqual(self.dials,[])
    async def test_dns_timeout_and_unapproved_host(self):
        async def slow(host):await asyncio.sleep(1)
        self.broker.resolver=slow;self.broker.dns_timeout=.01
        with self.assertRaises(TimeoutError):
            async with self.broker.connection('example.com:443'):pass
        with self.assertRaises(PermissionError):
            async with self.broker.connection('other.example:443'):pass
        self.assertEqual(self.firewall.grants,[]);self.assertEqual(self.broker.active,0)
    async def test_expiry_before_grant_and_after_grant(self):
        async def expired(host):self.now+=31;return self.snapshot
        self.broker.resolver=expired
        with self.assertRaises(ValueError):
            async with self.broker.connection('example.com:443'):pass
        self.assertEqual(self.firewall.grants,[])
        self.broker.resolver=self.resolver
        async def delayed(destination):self.firewall.grants.append(destination);self.now+=31
        self.firewall.grant=delayed
        with self.assertRaises(PermissionError):
            async with self.broker.connection('example.com:443'):pass
        self.assertEqual(self.dials,[]);self.assertEqual(len(self.firewall.revoked),1)
    async def test_partial_grant_failure_is_revoked(self):
        self.firewall.fail_grant=True
        with self.assertRaises(OSError):
            async with self.broker.connection('example.com:443'):pass
        self.assertEqual(self.firewall.grants,self.firewall.revoked);self.assertEqual(self.dials,[])
    async def test_wrong_peer_closed_and_revoked(self):
        writer=Writer(('1.1.1.1',443))
        async def wrong(ip,port):return object(),writer
        self.broker.dial=wrong
        with self.assertRaises(PermissionError):
            async with self.broker.connection('example.com:443'):pass
        self.assertTrue(writer.closed);self.assertEqual(len(self.firewall.revoked),1)
    async def test_revoke_failure_blocks_future_connections(self):
        self.firewall.fail_revoke=True
        with self.assertRaises(RuntimeError):
            async with self.broker.connection('example.com:443'):pass
        with self.assertRaises(PermissionError):
            async with self.broker.connection('example.com:443'):pass
        self.assertEqual(len(self.queries),1);self.assertTrue(self.broker.poisoned)
    async def test_cancelled_session_cleans_up(self):
        entered=asyncio.Event()
        async def work():
            async with self.broker.connection('example.com:443'):
                entered.set();await asyncio.sleep(30)
        task=asyncio.create_task(work());await entered.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(self.writers[0].closed);self.assertEqual(len(self.firewall.revoked),1)
        self.assertEqual(self.broker.active,0)
    async def test_repeated_cancellation_does_not_interrupt_revoke(self):
        entered = asyncio.Event()
        revoking = asyncio.Event()
        release = asyncio.Event()
        completed = asyncio.Event()
        async def revoke(destination):
            revoking.set()
            await release.wait()
            self.firewall.revoked.append(destination)
            completed.set()
        self.firewall.revoke = revoke
        async def work():
            async with self.broker.connection('example.com:443'):
                entered.set()
                await asyncio.Event().wait()
        task = asyncio.create_task(work())
        try:
            await asyncio.wait_for(entered.wait(), 1)
            task.cancel()
            await asyncio.wait_for(revoking.wait(), 1)
            for _ in range(3):
                task.cancel()
                await asyncio.sleep(0)
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(completed.is_set())
            self.assertEqual(self.firewall.grants, self.firewall.revoked)
            self.assertFalse(self.broker.poisoned)
            self.assertEqual(self.broker.active, 0)
        finally:
            release.set()
            if not task.done():task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_repeated_cancellation_preserves_cleanup_failure(self):
        revoking = asyncio.Event()
        release = asyncio.Event()
        async def revoke(destination):
            revoking.set()
            await release.wait()
            raise OSError('simulated kernel revoke failure')
        self.firewall.revoke = revoke
        async def work():
            async with self.broker.connection('example.com:443'):pass
        task = asyncio.create_task(work())
        try:
            await asyncio.wait_for(revoking.wait(), 1)
            for _ in range(3):
                task.cancel()
                await asyncio.sleep(0)
            release.set()
            with self.assertRaisesRegex(RuntimeError, 'Destination cleanup failed'):
                await task
            self.assertTrue(self.broker.poisoned)
            self.assertEqual(self.broker.active, 0)
            with self.assertRaises(PermissionError):
                async with self.broker.connection('example.com:443'):pass
            self.assertEqual(len(self.queries), 1)
        finally:
            release.set()
            if not task.done():task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_capacity_and_session_timeout(self):
        self.broker.capacity=1
        async with self.broker.connection('example.com:443'):
            with self.assertRaises(RuntimeError):
                async with self.broker.connection('example.com:443'):pass
        self.broker.session_timeout=.01
        with self.assertRaises(TimeoutError):
            async with self.broker.connection('example.com:443'):await asyncio.sleep(1)
        self.assertEqual(len(self.firewall.revoked),2);self.assertEqual(self.broker.active,0)

    async def test_cancelled_partial_grant_is_revoked(self):
        granting=asyncio.Event()
        async def grant(destination):
            self.firewall.grants.append(destination);granting.set();await asyncio.sleep(30)
        self.firewall.grant=grant
        async def work():
            async with self.broker.connection('example.com:443'):pass
        task=asyncio.create_task(work());await granting.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(self.firewall.grants,self.firewall.revoked)
        self.assertEqual(self.dials,[]);self.assertEqual(self.broker.active,0)
    async def test_concurrent_same_ip_has_distinct_lease_identity(self):
        first=asyncio.Event();second=asyncio.Event();release=asyncio.Event()
        async def work(entered):
            async with self.broker.connection('example.com:443'):
                entered.set();await release.wait()
        a=asyncio.create_task(work(first));b=asyncio.create_task(work(second))
        await first.wait();await second.wait()
        self.assertEqual(self.broker.active,2)
        self.assertNotEqual(self.firewall.grants[0].lease_id,self.firewall.grants[1].lease_id)
        a.cancel()
        with self.assertRaises(asyncio.CancelledError):await a
        self.assertEqual(self.broker.active,1);self.assertFalse(b.done())
        release.set();await b
        self.assertEqual({d.lease_id for d in self.firewall.grants},{d.lease_id for d in self.firewall.revoked})
    async def test_failed_socket_close_still_revokes_and_blocks_broker(self):
        class BrokenWriter(Writer):
            def close(self):raise OSError('socket close failed')
        async def dial(ip,port):return object(),BrokenWriter((ip,port))
        self.broker.dial=dial
        with self.assertRaises(RuntimeError):
            async with self.broker.connection('example.com:443'):pass
        self.assertEqual(len(self.firewall.revoked),1);self.assertTrue(self.broker.poisoned)
    async def test_cleanup_timeout_blocks_broker(self):
        async def stuck(destination):await asyncio.sleep(30)
        self.firewall.revoke=stuck;self.broker.cleanup_timeout=.01
        with self.assertRaises(RuntimeError):
            async with self.broker.connection('example.com:443'):pass
        self.assertTrue(self.broker.poisoned);self.assertEqual(self.broker.active,0)
    async def test_grant_timeout_revokes_and_never_dials(self):
        async def stuck(destination):
            self.firewall.grants.append(destination);await asyncio.sleep(30)
        self.firewall.grant=stuck;self.broker.dial_timeout=.01
        with self.assertRaises(TimeoutError):
            async with self.broker.connection('example.com:443'):pass
        self.assertEqual(self.firewall.grants,self.firewall.revoked);self.assertEqual(self.dials,[])


if __name__=='__main__':unittest.main()
