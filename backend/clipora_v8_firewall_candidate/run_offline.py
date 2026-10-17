"""Actual namespace firewall + capability-drop tests; all destinations internal."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

HERE = Path(__file__).resolve().parent
IMAGE = 'clipora-gateway:v8-test'
SINK = '''
import socket,threading,time
for port in (8443,8444):
 s=socket.socket();s.bind(('0.0.0.0',port));s.listen()
 def serve(s):
  while True:
   c,_=s.accept();c.sendall(b'fixture');c.close()
 threading.Thread(target=serve,args=(s,),daemon=True).start()
print('SINK READY',flush=True)
time.sleep(180)
'''
SERVICE = '''
import json,os,socket,subprocess,sys
from pathlib import Path
p=json.loads(Path('/fixture/config.json').read_text())
def connect(ip,port):
 with socket.create_connection((ip,port),timeout=1) as s: return s.recv(32)
assert connect(p['destination_ip'],p['destination_port'])==b'fixture'
def blocked(ip,port):
 try:connect(ip,port)
 except OSError:return
 raise AssertionError('Forbidden destination reached')
blocked(p['destination_ip'],8444)
blocked(p['gateway_ip'],8443)
status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
assert os.getuid()==p['uid'] and os.getgid()==p['gid']
assert os.getgroups()==[]
assert all(int(status[n],16)==0 for n in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
assert status['NoNewPrivs'].strip()=='1'
attempt=subprocess.run(['iptables','-P','OUTPUT','ACCEPT'],capture_output=True,timeout=3)
assert attempt.returncode!=0
blocked(p['destination_ip'],8444)
result={'allowed_ip_port_reachable':True,'different_port_denied':True,'different_ip_denied':True,
 'firewall_mutation_denied':True,'policy_still_enforced_after_mutation_attempt':True,
 'all_capability_sets_zero':True,'no_new_privileges':True,'uid':os.getuid(),'gid':os.getgid(),
 'supplementary_groups_empty':True}
s=socket.socket();s.bind(('0.0.0.0',8888));s.listen()
print('SERVICE READY',flush=True)
while True:
 c,_=s.accept();c.sendall(json.dumps(result).encode());c.close()
'''


def docker(args, timeout=20, check=True):
    p = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError('Disposable firewall command failed: ' + p.stderr[-1500:])
    return p.stdout.strip() if check else p


def main():
    run_id = uuid4().hex
    prefix = 'clipora-fw-' + run_id[:10]
    label = 'clipora.firewall.test=' + run_id
    containers = []
    network = None
    before = set(docker(['ps', '-aq', '--no-trunc']).split())
    results = {}
    with tempfile.TemporaryDirectory(prefix='clipora-firewall-fixture-') as tmp:
        root = Path(tmp)
        for name in ('policy.py', 'bootstrap.py'):
            shutil.copyfile(HERE / name, root / name)
        (root / 'service.py').write_text(SERVICE)
        def create(name, command, bootstrap=False, admin=True, config=None):
            args = ['create', '--pull', 'never', '--name', name, '--label', label,
                    '--network', network, '--read-only', '--cap-drop', 'ALL',
                    '--security-opt', 'no-new-privileges', '--memory', '128m', '--cpus', '1', '--pids-limit', '32']
            if bootstrap:
                for cap in ('SETPCAP', 'SETUID', 'SETGID', *(['NET_ADMIN'] if admin else [])):
                    args.extend(['--cap-add', cap])
                args.extend(['--user', '0:0', '-e', 'CLIPORA_DISPOSABLE_FIREWALL_TEST=1',
                             '-v', str(config or root) + ':/fixture:ro'])
            else:
                args.extend(['--user', '65534:65534'])
            docker([*args, '--entrypoint', 'python3', IMAGE, '-B', '-u', *command])
            containers.append(name)
            docker(['start', name])
        def info(name): return json.loads(docker(['inspect', name]))[0]
        def ip(name): return info(name)['NetworkSettings']['Networks'][network]['IPAddress']
        def ready(name, marker):
            for _ in range(80):
                if marker in docker(['logs', name]):return
                state = info(name)['State']
                if not state['Running']:
                    p = docker(['logs', name], check=False)
                    raise RuntimeError('Fixture stopped: ' + p.stderr[-1600:])
                time.sleep(.1)
            raise TimeoutError('Fixture readiness timeout')
        try:
            docker(['image', 'inspect', IMAGE])
            network = prefix + '-internal'
            docker(['network', 'create', '--internal', '--label', label, network])
            topology = json.loads(docker(['network', 'inspect', network]))[0]
            assert topology['Internal'] is True
            subnet = topology['IPAM']['Config'][0]['Subnet']
            gateway, target, stranger = [prefix + '-' + n for n in ('gateway', 'target', 'stranger')]
            for name in (gateway, target, stranger):
                create(name, ['-c', SINK]); ready(name, 'SINK READY')
            config = {'mode': 'offline-fixture', 'network': subnet, 'gateway_ip': ip(gateway),
                      'destination_ip': ip(target), 'destination_port': 8443, 'uid': 65534, 'gid': 65534}
            (root / 'config.json').write_text(json.dumps(config))
            # Positive controls establish that each blocked TCP listener is live.
            for host, port in ((ip(target), 8443), (ip(target), 8444), (ip(gateway), 8443)):
                script = f"import socket;s=socket.create_connection(({host!r},{port}),2);assert s.recv(32)==b'fixture';s.close()"
                docker(['exec', stranger, 'python3', '-B', '-c', script])
            fw = prefix + '-egress'
            create(fw, ['/fixture/bootstrap.py', '/fixture/config.json', '/usr/bin/python3', '-B', '-u', '/fixture/service.py'], bootstrap=True)
            ready(fw, 'SERVICE READY')
            fw_info = info(fw)
            assert not fw_info['HostConfig']['Privileged'] and not fw_info['HostConfig'].get('PortBindings')
            assert fw_info['HostConfig']['ReadonlyRootfs']
            assert len(fw_info['NetworkSettings']['Networks']) == 1
            assert len(fw_info['Mounts']) == 1 and fw_info['Mounts'][0]['RW'] is False
            fetch = f"import socket;s=socket.create_connection(({ip(fw)!r},8888),2);print(s.recv(4096).decode());s.close()"
            results['service'] = json.loads(docker(['exec', gateway, 'python3', '-B', '-c', fetch]))
            reject = f"""import socket
try:socket.create_connection(({ip(fw)!r},8888),1)
except OSError:print('DENIED')
else:raise AssertionError('Unexpected inbound access')
"""
            assert docker(['exec', stranger, 'python3', '-B', '-c', reject]) == 'DENIED'
            results['unapproved_inbound_source_denied'] = True
            for case in ('invalid-config', 'missing-net-admin'):
                folder = root / case;folder.mkdir()
                for filename in ('bootstrap.py', 'policy.py', 'service.py'):
                    shutil.copyfile(root / filename, folder / filename)
                bad = {**config, 'mode': 'public'} if case == 'invalid-config' else config
                (folder / 'config.json').write_text(json.dumps(bad))
                name = prefix + '-' + case
                create(name, ['/fixture/bootstrap.py', '/fixture/config.json', '/usr/bin/python3', '-B', '-u', '/fixture/service.py'],
                       bootstrap=True, admin=case != 'missing-net-admin', config=folder)
                assert docker(['wait', name]) != '0'
                assert 'SERVICE READY' not in docker(['logs', name])
                results[case + '_service_not_started'] = True
            results.update({'offline_only': True, 'environment': docker(['info', '--format', '{{.OSType}} / {{.OperatingSystem}}']),
                            'public_egress_enabled': False, 'host_firewall_modified': False,
                            'net_admin_scope': 'Bootstrap in disposable container network namespace only',
                            'production_gate_closure': False, 'image_id': fw_info['Image']})
        finally:
            errors = []
            for name in reversed(containers):
                try:
                    assert info(name)['Config']['Labels'].get('clipora.firewall.test') == run_id
                    docker(['rm', '-f', name])
                except Exception as exc:errors.append(str(exc))
            if network:
                try:
                    data = json.loads(docker(['network', 'inspect', network]))[0]
                    assert data['Labels'].get('clipora.firewall.test') == run_id
                    docker(['network', 'rm', network])
                except Exception as exc:errors.append(str(exc))
            if errors:raise RuntimeError('Fixture cleanup incomplete: ' + '; '.join(errors))
            assert before <= set(docker(['ps', '-aq', '--no-trunc']).split())
    assert not docker(['ps', '-aq', '--filter', 'label=' + label])
    assert not docker(['network', 'ls', '-q', '--filter', 'label=' + label])
    results['owned_resources_removed'] = True
    results['preexisting_containers_preserved'] = True
    if len(sys.argv) > 1:Path(sys.argv[1]).write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__': main()
