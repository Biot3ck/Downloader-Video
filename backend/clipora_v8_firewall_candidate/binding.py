"""Bounded destination transaction for a future egress adapter.

Default transport is deny-all, before DNS. No live resolver, firewall updater,
or socket dialer is installed here. Adapters must implement idempotent revoke.
"""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import ipaddress
import math
import time
from uuid import uuid4

from clipora_v8_secure_egress_stage.connect_policy import validate_connect_target
from clipora_v8_secure_egress_stage.ip_policy import validate_destination_ip


@dataclass(frozen=True)
class Destination:
    lease_id: str
    host: str
    port: int
    ip: str
    addresses: tuple[str, ...]
    expires_at: float


def validate_snapshot(host, snapshot, started, clock):
    if not isinstance(snapshot, dict) or set(snapshot) != {'host', 'A', 'AAAA', 'ttl'}:
        raise ValueError('Incomplete DNS snapshot')
    if snapshot['host'] != host:
        raise ValueError('DNS hostname mismatch')
    ttl = snapshot['ttl']
    if type(ttl) not in (int, float) or not math.isfinite(ttl) or not 0 < ttl <= 86400:
        raise ValueError('Invalid DNS TTL')
    addresses = []
    for field, version in (('A', 4), ('AAAA', 6)):
        values = snapshot[field]
        if not isinstance(values, (list, tuple)) or len(values) > 32:
            raise ValueError('Invalid DNS address set')
        for value in values:
            if not isinstance(value, str):raise ValueError('Invalid DNS address')
            ip = ipaddress.ip_address(value)
            if ip.version != version or '%' in value or (version == 6 and ip.ipv4_mapped):
                raise ValueError('DNS address family mismatch or ambiguous address')
            canonical = validate_destination_ip(value)
            if canonical not in addresses:addresses.append(canonical)
    if not addresses:raise ValueError('No DNS addresses')
    expires = started + min(float(ttl), 30.0)
    if clock() >= expires:raise ValueError('DNS snapshot expired')
    return Destination(uuid4().hex, host, 443, addresses[0], tuple(addresses), expires)


class Broker:
    def __init__(self, allowed_hosts, resolver=None, firewall=None, dial=None, *, clock=time.monotonic,
                 capacity=8, dns_timeout=3, dial_timeout=4, session_timeout=90, cleanup_timeout=3):
        normalized = frozenset(validate_connect_target(h + ':443')[0] for h in allowed_hosts)
        if not normalized or len(normalized) > 128:raise ValueError('Explicit bounded host policy required')
        if not 1 <= capacity <= 32:raise ValueError('Invalid capacity')
        self.allowed_hosts = normalized
        self.resolver, self.firewall, self.dial, self.clock = resolver, firewall, dial, clock
        self.capacity, self.active = capacity, 0
        self.dns_timeout, self.dial_timeout = dns_timeout, dial_timeout
        self.session_timeout, self.cleanup_timeout = session_timeout, cleanup_timeout
        self.poisoned = False

    async def _cleanup(self, destination, writer):
        # Closing a socket cannot be allowed to skip removal of its firewall permit.
        failure = None
        if writer is not None:
            try:
                writer.close()
                await asyncio.wait_for(writer.wait_closed(), self.cleanup_timeout)
            except BaseException as exc:
                self.poisoned = True
                failure = exc
        try:
            await asyncio.wait_for(self.firewall.revoke(destination), self.cleanup_timeout)
        except BaseException as exc:
            self.poisoned = True
            failure = exc
        if failure is not None:raise RuntimeError('Destination cleanup failed') from failure

    @asynccontextmanager
    async def connection(self, target):
        if self.resolver is None or self.firewall is None or self.dial is None:
            raise PermissionError('Live egress adapter is not enabled')
        if self.poisoned:raise PermissionError('Firewall cleanup requires recovery')
        host, port = validate_connect_target(target)
        if host not in self.allowed_hosts:raise PermissionError('Hostname not authorized')
        if self.active >= self.capacity:raise RuntimeError('Destination capacity reached')
        # No await between admission check and increment; one event loop owns a broker.
        self.active += 1
        destination = writer = None
        try:
            started = self.clock()
            snapshot = await asyncio.wait_for(self.resolver(host), self.dns_timeout)
            destination = validate_snapshot(host, snapshot, started, self.clock)
            if self.poisoned:raise PermissionError('Firewall cleanup requires recovery')
            # Grant receives the same immutable object that identifies socket and revoke.
            await asyncio.wait_for(self.firewall.grant(destination), self.dial_timeout)
            if self.poisoned or self.clock() >= destination.expires_at:
                raise PermissionError('Destination permission expired or broker unhealthy')
            reader, writer = await asyncio.wait_for(self.dial(destination.ip, port), self.dial_timeout)
            peer = writer.get_extra_info('peername')
            if (not peer or ipaddress.ip_address(peer[0]) != ipaddress.ip_address(destination.ip)
                    or peer[1] != port):
                raise PermissionError('Socket peer differs from authorized destination')
            if self.poisoned or self.clock() >= destination.expires_at:
                raise PermissionError('Destination expired during connection')
            async with asyncio.timeout(self.session_timeout):
                yield reader, writer, destination
        finally:
            try:
                if destination is not None:
                    cleanup = asyncio.create_task(self._cleanup(destination, writer))
                    cancelled = False
                    while not cleanup.done():
                        try:
                            await asyncio.wait({cleanup})
                        except asyncio.CancelledError:
                            # asyncio.wait does not cancel its child on cancellation.
                            # Adapter cleanup still has its own bounded timeout.
                            cancelled = True
                    cleanup.result()
                    if cancelled:raise asyncio.CancelledError
            finally:
                self.active -= 1
