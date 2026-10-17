"""Offline-only firewall bootstrap in a disposable network namespace.

Requires NET_ADMIN/SETPCAP/SETUID/SETGID during bootstrap only. No shell commands,
public mode, DNS rule, dynamic allowlist, or host-network support is provided.
"""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
from policy import rules, validate


def run(argv, data=None):
    subprocess.run(argv, input=data, text=True, capture_output=True, check=True, timeout=5)


def deny_first():
    for tool in ('iptables', 'ip6tables'):
        for chain in ('INPUT', 'OUTPUT', 'FORWARD'):
            run([tool, '-w', '2', '-P', chain, 'DROP'])


def drop_privileges(uid, gid):
    libc = ctypes.CDLL(None, use_errno=True)
    def prctl(option, value):
        if libc.prctl(option, value, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'Privilege reduction failed')
    prctl(38, 1)  # PR_SET_NO_NEW_PRIVS
    last = int(Path('/proc/sys/kernel/cap_last_cap').read_text())
    if not 0 <= last <= 63:
        raise ValueError('Unsupported Linux capability range')
    for cap in range(last + 1):
        prctl(24, cap)  # PR_CAPBSET_DROP, while SETPCAP is still effective
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    for name in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'):
        if int(status[name], 16):
            raise RuntimeError('Capabilities survived privilege drop')
    if status['NoNewPrivs'].strip() != '1' or os.getuid() == 0 or os.getgid() == 0:
        raise RuntimeError('Unsafe service credentials')


def main():
    if os.environ.get('CLIPORA_DISPOSABLE_FIREWALL_TEST') != '1':
        raise SystemExit('Offline disposable harness guard required')
    if len(sys.argv) < 3 or os.getuid() != 0:
        raise SystemExit('Expected root bootstrap, config path and service command')
    deny_first()
    data = validate(json.loads(Path(sys.argv[1]).read_text()))
    ipv4, ipv6 = rules(data)
    run(['ip6tables-restore', '-w', '2'], ipv6)
    run(['iptables-restore', '-w', '2'], ipv4)
    drop_privileges(data['uid'], data['gid'])
    os.execv(sys.argv[2], sys.argv[2:])


if __name__ == '__main__':
    main()
