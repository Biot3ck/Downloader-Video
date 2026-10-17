"""DNS answer adapter for Broker; no default resolver or network access.

Supply an explicitly configured async dnspython Resolver.resolve callable.
The deployment must constrain its DNS server and route independently.
"""
import asyncio
import math
import time
import dns.exception
import dns.name
import dns.rdatatype
import dns.resolver
from .binding import validate_snapshot
from clipora_v8_secure_egress_stage.connect_policy import validate_connect_target


class SnapshotResolver:
    def __init__(self, query=None, *, timeout=2.5, capacity=8, clock=time.monotonic, wall_clock=time.time):
        if type(capacity) is not int or not 1 <= capacity <= 32:
            raise ValueError('Invalid DNS capacity')
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 3:
            raise ValueError('Invalid DNS deadline')
        self.query, self.timeout, self.capacity, self.clock = query, timeout, capacity, clock
        self.wall_clock = wall_clock
        self.active = 0

    async def __call__(self, host):
        if self.query is None:raise PermissionError('DNS transport is not enabled')
        host = validate_connect_target(host + ':443')[0]
        if self.active >= self.capacity:raise RuntimeError('DNS capacity reached')
        self.active += 1
        started = self.clock()
        snapshot = {'host': host, 'A': [], 'AAAA': [], 'ttl': 30.0}
        qname = dns.name.from_text(host + '.')
        canonical = None
        try:
            async with asyncio.timeout(self.timeout):
                for family in ('A', 'AAAA'):
                    answer = await self.query(qname, family, search=False,
                                              raise_on_no_answer=False, lifetime=self.timeout)
                    # NoAnswer is represented by rrset=None. NXDOMAIN, SERVFAIL,
                    # timeout and other exceptions must never preserve partial A.
                    if (not isinstance(answer, dns.resolver.Answer) or answer.qname != qname
                            or answer.rdtype != dns.rdatatype.from_text(family)):
                        raise ValueError('DNS answer does not match query')
                    if canonical is not None and canonical != answer.canonical_name:
                        raise ValueError('Inconsistent DNS alias across address families')
                    canonical = answer.canonical_name
                    ttl = answer.chaining_result.minimum_ttl
                    if type(ttl) is not int or ttl <= 0:
                        raise ValueError('DNS answer has no usable lifetime')
                    # Cached Answer objects retain the original RR TTL; never
                    # turn that into a fresh lease after cache expiry.
                    remaining = answer.expiration - self.wall_clock()
                    if not math.isfinite(remaining) or remaining <= 0:
                        raise ValueError('Cached DNS answer expired')
                    snapshot['ttl'] = min(snapshot['ttl'], ttl, remaining)
                    if answer.rrset is not None:
                        if len(answer) > 32:raise ValueError('DNS answer exceeds address limit')
                        snapshot[family] = [r.address for r in answer]
            # Includes all A/AAAA addresses, CNAME TTL and time spent querying.
            # Broker independently revalidates before installing a lease.
            validate_snapshot(host, snapshot, started, self.clock)
            snapshot['ttl'] -= max(0, self.clock() - started)
            if snapshot['ttl'] <= 0:raise ValueError('DNS snapshot expired')
            return snapshot
        except dns.exception.DNSException as exc:
            raise ValueError('DNS resolution failed') from exc
        finally:
            self.active -= 1
