"""Offline kernel isolation evidence in disposable Docker network namespaces.

No public sockets, image pulls, host firewall changes, privileged containers,
Docker socket mounts, or NET_ADMIN grants. Not a production firewall audit.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

IMAGE = 'clipora-worker:v8-dns'
SINK = '''
import socket
s=socket.socket();s.bind(('0.0.0.0',8888));s.listen()
print('ISOLATION SINK READY',flush=True)
while True:
 c,_=s.accept();c.sendall(b'clipora-isolation-fixture');c.close()
'''
PROBE = '''
import errno,json,os,socket,subprocess,sys
from pathlib import Path
expected_uid=int(sys.argv[1]);gateway=sys.argv[2];egress=sys.argv[3]
status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
assert os.getuid()==expected_uid and expected_uid!=0
for name in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'):
 assert int(status[name].strip(),16)==0,(name,status[name])
assert status['NoNewPrivs'].strip()=='1'
try: os.setuid(0)
except OSError as e: assert e.errno==errno.EPERM
else: raise AssertionError('UID escalation allowed')
try: socket.socket(socket.AF_INET,socket.SOCK_RAW,socket.IPPROTO_ICMP)
except OSError as e: assert e.errno==errno.EPERM
else: raise AssertionError('Raw socket allowed')
with socket.create_connection((gateway,8888),timeout=2) as s:
 assert s.recv(64)==b'clipora-isolation-fixture'
try:
 with socket.create_connection((egress,8888),timeout=2): pass
except OSError: pass
else: raise AssertionError('Worker reached egress directly')
routes=Path('/proc/net/route').read_text().splitlines()[1:]
assert all(row.split()[1]!='00000000' for row in routes),'IPv4 default route present'
v6=Path('/proc/net/ipv6_route').read_text().splitlines()
# Reject any usable IPv6 default route, ignoring the kernel unreachable entry.
assert all(not(row.split()[0]=='0'*32 and row.split()[1]=='00' and
               int(row.split()[8],16)&1 and not int(row.split()[8],16)&0x200)
           for row in v6),'Usable IPv6 default route present'
try: Path('/clipora-root-write-probe').write_text('blocked')
except OSError as e: assert e.errno==errno.EROFS
else: raise AssertionError('Root filesystem writable')
mounts=[line.split() for line in Path('/proc/mounts').read_text().splitlines()]
output=next(row for row in mounts if row[1]=='/output')
assert output[2]=='tmpfs' and {'noexec','nosuid','nodev'}<=set(output[3].split(','))
limit=os.statvfs('/output');capacity=limit.f_blocks*limit.f_frsize
assert capacity<=1024*1024
p=Path('/output/executable');p.write_text('#!/bin/sh\\nexit 0\\n');p.chmod(0o700)
try: subprocess.run([str(p)],check=True,timeout=2)
except OSError as e: assert e.errno==errno.EACCES
else: raise AssertionError('tmpfs execution allowed')
try:
 with open('/output/fill','wb',buffering=0) as f:
  for _ in range(3):f.write(b'x'*(1024*1024))
except OSError as e: assert e.errno==errno.ENOSPC
else: raise AssertionError('Workspace quota bypassed')
assert not Path('/var/run/docker.sock').exists()
print(json.dumps({'uid':os.getuid(),'all_capability_sets_zero':True,'no_new_privileges':True,
 'setuid_and_raw_socket_denied':True,'gateway_reachable':True,'direct_egress_denied':True,
 'ipv4_default_route_absent':True,'ipv6_usable_default_route_absent':True,
 'root_write_errno':'EROFS','workspace_fill_errno':'ENOSPC','workspace_exec_errno':'EACCES',
 'workspace_limit_bytes':capacity,'workspace_mount_flags':['noexec','nosuid','nodev'],
 'docker_socket_absent':True}))
'''


def command(args, timeout=20):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Docker fixture command failed: ' + result.stderr[-1200:])
    return result.stdout.strip()


def main():
    identity = uuid4().hex
    prefix = 'clipora-isolation-' + identity[:10]
    label = 'clipora.isolation.run=' + identity
    before = set(command(['ps', '-aq', '--no-trunc']).split())
    networks, containers = [], []
    report = None
    try:
        command(['image', 'inspect', IMAGE])
        for suffix in ('front', 'back'):
            name = prefix + '-' + suffix
            command(['network', 'create', '--internal', '--label', label, name])
            networks.append(name)
            info = json.loads(command(['network', 'inspect', name]))[0]
            assert info['Internal'] is True
        uid = os.getuid() if os.getuid() else 65534
        gid = os.getgid() if os.getuid() else 65534
        for suffix, network in (('gateway', networks[0]), ('egress', networks[1])):
            name = prefix + '-' + suffix
            command(['create', '--pull', 'never', '--name', name, '--label', label,
                     '--network', network, '--read-only', '--cap-drop', 'ALL',
                     '--security-opt', 'no-new-privileges', '--user', f'{uid}:{gid}',
                     '--memory', '128m', '--cpus', '1', '--pids-limit', '32',
                     '--entrypoint', 'python3', IMAGE, '-B', '-u', '-c', SINK])
            containers.append(name)
            if suffix == 'gateway':
                command(['network', 'connect', networks[1], name])
            command(['start', name])
            for _ in range(40):
                if 'ISOLATION SINK READY' in command(['logs', name]): break
                time.sleep(.1)
            else: raise TimeoutError('Sink failed to start')
        def ip(name, network):
            return json.loads(command(['inspect', name]))[0]['NetworkSettings']['Networks'][network]['IPAddress']
        gateway, egress = ip(containers[0], networks[0]), ip(containers[1], networks[1])
        worker = prefix + '-worker'
        command(['create', '--pull', 'never', '--name', worker, '--label', label,
                 '--network', networks[0], '--read-only', '--cap-drop', 'ALL',
                 '--security-opt', 'no-new-privileges', '--user', f'{uid}:{gid}',
                 '--memory', '128m', '--cpus', '1', '--pids-limit', '32',
                 '--tmpfs', f'/output:rw,noexec,nosuid,nodev,size=1m,uid={uid},gid={gid},mode=0700',
                 '--entrypoint', 'python3', IMAGE, '-B', '-c', PROBE, str(uid), gateway, egress])
        containers.append(worker)
        info = json.loads(command(['inspect', worker]))[0]
        host = info['HostConfig']
        assert host['ReadonlyRootfs'] and not host['Privileged']
        assert host['CapDrop'] == ['ALL'] and not host.get('CapAdd')
        assert not host.get('PortBindings') and not host.get('Binds')
        assert len(info['NetworkSettings']['Networks']) == 1
        assert host['Memory'] == 128 * 1024 * 1024 and host['PidsLimit'] == 32
        assert host['NanoCpus'] == 1_000_000_000
        command(['start', worker])
        assert command(['wait', worker]) == '0', command(['logs', worker])
        evidence = json.loads(command(['logs', worker]))
        # Positive control: the egress sink itself must work on its own network.
        positive = "import socket; s=socket.create_connection((" + repr(egress) + ",8888),2); assert s.recv(64)==b'clipora-isolation-fixture';s.close()"
        command(['exec', containers[0], 'python3', '-B', '-c', positive])
        report = {'offline_only': True, 'environment': command(['info', '--format', '{{.OSType}} / {{.OperatingSystem}}']),
                  'scope': 'Disposable Linux container namespaces on Docker Desktop; not production-host firewall attestation',
                  'image_id': info['Image'], 'worker_probe': evidence,
                  'egress_sink_positive_control': True, 'internal_networks': 2,
                  'resource_limits_inspected': True, 'public_sockets_attempted': False,
                  'host_firewall_modified': False, 'net_admin_granted': False,
                  'production_blockers_closed': 0}
    finally:
        errors = []
        for kind, names in (('container', containers), ('network', networks)):
            for name in reversed(names):
                try:
                    info = json.loads(command(['inspect', name]))[0]
                    labels = info.get('Config', {}).get('Labels', {}) if kind == 'container' else info.get('Labels', {})
                    assert labels.get('clipora.isolation.run') == identity
                    command(['rm', '-f', name] if kind == 'container' else ['network', 'rm', name])
                except Exception as exc:
                    errors.append(str(exc))
        if errors: raise RuntimeError('Isolation fixture cleanup failed: ' + '; '.join(errors))
        assert not command(['ps', '-aq', '--filter', 'label=' + label])
        assert not command(['network', 'ls', '-q', '--filter', 'label=' + label])
        after = set(command(['ps', '-aq', '--no-trunc']).split())
        assert before <= after, 'Preexisting container removed during test'
    report['owned_resources_removed'] = True
    report['preexisting_containers_preserved'] = True
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
