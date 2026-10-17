"""Real per-destination leases, restricted to an offline fixture namespace.

Owns the entire filter table of its disposable namespace. Never run on a host
or alongside another firewall manager. No daemon, IPC listener, or public mode.
"""
import asyncio
import os
import re
import subprocess
import time
from .policy import validate
from .binding import Destination


class KernelLeases:
    def __init__(self, config, *, clock=time.monotonic, command=None):
        if os.environ.get('CLIPORA_DISPOSABLE_FIREWALL_TEST') != '1':
            raise PermissionError('Disposable offline guard required')
        self.config = validate(config)
        self.clock = clock
        self.command = command or self._command
        self.leases = {}
        self.lock = asyncio.Lock()
        self.ready = False
        self.poisoned = False

    @staticmethod
    def _command(argv, data=None):
        subprocess.run(argv, input=data, text=True, capture_output=True, check=True, timeout=3)

    def _render(self, leases):
        # No general ESTABLISHED rule: removing the last permit blocks existing
        # flows in both directions too. The test controller has no network API.
        lines = ['*filter', ':INPUT DROP [0:0]', ':FORWARD DROP [0:0]', ':OUTPUT DROP [0:0]']
        destinations = sorted({(d.ip, d.port) for d in leases.values()})
        for ip, port in destinations:
            lines += [f'-A INPUT -s {ip}/32 -p tcp --sport {port} -m conntrack --ctstate ESTABLISHED -j ACCEPT',
                      f'-A OUTPUT -d {ip}/32 -p tcp --dport {port} -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT']
        return '\n'.join([*lines, 'COMMIT', ''])

    def _install(self, leases):
        self.command(['iptables-restore', '-w', '2'], self._render(leases))

    async def _serialized(self, operation):
        async with self.lock:
            # Subprocesses are bounded; cancellation waits for the mutation to
            # finish before releasing serialization. The broker then revokes.
            task = asyncio.create_task(asyncio.to_thread(operation))
            cancelled = False
            while not task.done():
                try:await asyncio.shield(task)
                except asyncio.CancelledError:cancelled = True
            result = task.result()
            if cancelled:raise asyncio.CancelledError
            return result

    def _failed(self):
        self.poisoned = True
        self._install({})
        self.leases.clear()

    async def initialize(self):
        def operation():
            if self.ready or self.poisoned:raise PermissionError('Cannot reinitialize controller')
            try:
                for binary in ('iptables', 'ip6tables'):
                    for chain in ('INPUT', 'OUTPUT', 'FORWARD'):
                        self.command([binary, '-w', '2', '-P', chain, 'DROP'])
                self.command(['ip6tables-restore', '-w', '2'],
                             '*filter\n:INPUT DROP [0:0]\n:FORWARD DROP [0:0]\n:OUTPUT DROP [0:0]\nCOMMIT\n')
                self._install({})
                self.ready = True
            except BaseException:
                self._failed()
                raise
        await self._serialized(operation)

    def _validate(self, destination):
        if type(destination) is not Destination:raise PermissionError('Immutable Destination required')
        if (not re.fullmatch(r'[0-9a-f]{32}', destination.lease_id)
                or destination.host != 'example.com'
                or destination.ip != self.config['destination_ip']
                or destination.port != self.config['destination_port']
                or destination.addresses != (destination.ip,)):
            raise PermissionError('Destination outside explicit offline fixture policy')

    async def grant(self, destination):
        self._validate(destination)
        def operation():
            if not self.ready or self.poisoned:raise PermissionError('Controller unavailable')
            if not self.clock() < destination.expires_at <= self.clock() + 30:
                raise PermissionError('Invalid lease admission deadline')
            if destination.lease_id in self.leases:
                if self.leases[destination.lease_id] != destination:raise PermissionError('Lease ID reused')
                return
            if len(self.leases) >= 32:raise RuntimeError('Firewall lease capacity reached')
            updated = {**self.leases, destination.lease_id: destination}
            try:self._install(updated)
            except BaseException:
                self._failed()
                raise
            self.leases = updated
        await self._serialized(operation)

    async def revoke(self, destination):
        self._validate(destination)
        def operation():
            existing = self.leases.get(destination.lease_id)
            if existing is not None and existing != destination:raise PermissionError('Lease identity mismatch')
            if self.poisoned:raise PermissionError('Namespace recovery required')
            if existing is None:return
            updated = {key:value for key,value in self.leases.items() if key != destination.lease_id}
            try:self._install(updated)
            except BaseException:
                self._failed()
                raise
            self.leases = updated
        await self._serialized(operation)
