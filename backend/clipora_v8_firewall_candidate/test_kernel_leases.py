import asyncio
from dataclasses import replace
import threading
import unittest
from unittest.mock import patch
from clipora_v8_firewall_candidate.binding import Destination
from clipora_v8_firewall_candidate.kernel_leases import KernelLeases


class KernelLeaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.guard=patch.dict('os.environ',{'CLIPORA_DISPOSABLE_FIREWALL_TEST':'1'});self.guard.start();self.addCleanup(self.guard.stop)
        self.calls=[]
        config={'mode':'offline-fixture','network':'10.83.0.0/24','gateway_ip':'10.83.0.2',
                'destination_ip':'10.83.0.3','destination_port':8443,'uid':65534,'gid':65534}
        self.fw=KernelLeases(config,clock=lambda:100,command=lambda args,data=None:self.calls.append((args,data)))
        self.a=Destination('a'*32,'example.com',8443,'10.83.0.3',('10.83.0.3',),120)
        self.b=replace(self.a,lease_id='b'*32)
        await self.fw.initialize()
    async def test_shared_endpoint_and_idempotent_revoke(self):
        await self.fw.grant(self.a);await self.fw.grant(self.b)
        self.assertEqual(self.calls[-1][1].count('-A OUTPUT'),1)
        await self.fw.revoke(self.a)
        self.assertIn('-A OUTPUT',self.calls[-1][1]);self.assertEqual(len(self.fw.leases),1)
        await self.fw.revoke(self.b)
        self.assertNotIn('ACCEPT',self.calls[-1][1])
        n=len(self.calls);await self.fw.revoke(self.b);self.assertEqual(len(self.calls),n)
    async def test_invalid_and_expired_destination(self):
        for d in (replace(self.a,ip='8.8.8.8'),replace(self.a,port=443),replace(self.a,expires_at=99),
                  replace(self.a,expires_at=200),replace(self.a,lease_id='bad'),replace(self.a,host='evil.example')):
            with self.assertRaises(PermissionError):await self.fw.grant(d)
        self.assertFalse(self.fw.leases)
    async def test_reused_identity_cannot_remove_other_lease(self):
        await self.fw.grant(self.a)
        with self.assertRaises(PermissionError):await self.fw.revoke(replace(self.a,expires_at=121))
        self.assertEqual(len(self.fw.leases),1)
    async def test_install_failure_denies_all_and_poisoned(self):
        await self.fw.grant(self.a)
        original=self.fw.command
        failed=False
        def fail_once(args,data=None):
            nonlocal failed
            if not failed:failed=True;raise OSError('kernel update failed')
            original(args,data)
        self.fw.command=fail_once
        with self.assertRaises(OSError):await self.fw.grant(self.b)
        self.assertTrue(self.fw.poisoned);self.assertFalse(self.fw.leases)
        self.assertNotIn('ACCEPT',self.calls[-1][1])
        with self.assertRaises(PermissionError):await self.fw.grant(self.b)
    async def test_failed_fallback_preserves_unresolved_state(self):
        await self.fw.grant(self.a)
        def fail(args,data=None):raise OSError('firewall unavailable')
        self.fw.command=fail
        with self.assertRaises(OSError):await self.fw.revoke(self.a)
        self.assertTrue(self.fw.poisoned)
        self.assertIn(self.a.lease_id,self.fw.leases)
        with self.assertRaises(PermissionError):await self.fw.grant(self.b)
    async def test_mutable_destination_rejected(self):
        with self.assertRaises(PermissionError):await self.fw.grant(object())
    async def test_repeated_cancel_does_not_release_lock_during_mutation(self):
        entered=threading.Event();release=threading.Event();original=self.fw.command
        def slow(args,data=None):entered.set();release.wait(2);original(args,data)
        self.fw.command=slow
        task=asyncio.create_task(self.fw.grant(self.a))
        await asyncio.to_thread(entered.wait,1)
        task.cancel();await asyncio.sleep(.01);task.cancel();await asyncio.sleep(.01)
        self.assertTrue(self.fw.lock.locked());self.assertFalse(task.done())
        release.set()
        with self.assertRaises(asyncio.CancelledError):await task
        await self.fw.revoke(self.a);self.assertFalse(self.fw.leases)


if __name__=='__main__':unittest.main()
