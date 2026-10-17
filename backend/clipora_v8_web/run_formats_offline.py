"""Exercise dormant video quality/MP3 policy in a disposable networkless worker.

No media is exported, jobs created, packages installed or public routes changed.
Only explicit candidate source files enter a temporary readonly Docker mount.
"""
import argparse
import json
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
from uuid import uuid4

HERE=Path(__file__).resolve().parent
EXPECTED='sha256:c0e3e82ca62c54eadf25137f4bc520bce1e42a73760a6655aa67c168b7f18432'


def command(args,timeout=15):
    result=subprocess.run(['docker',*args],capture_output=True,timeout=timeout)
    if result.returncode:raise RuntimeError('Offline format worker command failed')
    return result.stdout.decode().strip()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path);args=parser.parse_args()
    def terminate(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,terminate)
    if command(['image','inspect','clipora-worker:v8-dns','--format','{{.Id}}'])!=EXPECTED:
        raise RuntimeError('Worker base changed; review required')
    name='clipora-formats-'+uuid4().hex;identity=None;report=None
    with tempfile.TemporaryDirectory(prefix='clipora-formats-') as temporary:
        root=Path(temporary).resolve();root.chmod(0o755)
        for filename in ('video_formats.py','offline_formats_probe.py'):
            source=HERE/filename
            if source.is_symlink():raise ValueError('Source symlink rejected')
            shutil.copyfile(source,root/filename);(root/filename).chmod(0o444)
        try:
            identity=command(['create','--pull','never','--name',name,'--label','clipora.format.fixture='+name,
                '--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                '--user','10001:10001','--memory','384m','--cpus','1','--pids-limit','64',
                '--tmpfs','/work:rw,nosuid,nodev,noexec,size=64m,uid=10001,gid=10001,mode=0700',
                '--mount',f'type=bind,source={root},target=/candidate,readonly','--workdir','/candidate',
                '--entrypoint','python3',EXPECTED,'-B','offline_formats_probe.py'])
            info=json.loads(command(['inspect',identity]))[0];host=info['HostConfig']
            assert host['NetworkMode']=='none' and host['ReadonlyRootfs'] and host['CapDrop']==['ALL']
            assert not host['Privileged'] and not host.get('CapAdd') and not host.get('PortBindings')
            assert host['Memory']==384*1024*1024 and host['PidsLimit']==64
            assert host['NanoCpus']==1000000000 and 'size=64m' in host['Tmpfs']['/work']
            binds=[m for m in info['Mounts'] if m['Type']=='bind']
            assert len(binds)==1 and binds[0]['Destination']=='/candidate' and not binds[0]['RW']
            output=command(['start','-a',identity],timeout=90)
            assert json.loads(command(['inspect',identity]))[0]['State']['ExitCode']==0
            report=json.loads(output)
            assert set(report['outputs'])=={'video','hd','portrait_hd','mp3'}
            assert report['wrong_outputs_rejected']==['480p_as_hd','mp4_as_mp3']
            report.update(network='none',readonly_nonroot_cap_drop_all=True,workspace_limit_bytes=64*1024*1024)
        finally:
            if identity:command(['rm','-f',identity])
    report['owned_worker_removed']=True
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: offline native 480p/720p/portrait 1080p and actual MP3; no network or public activation')


if __name__=='__main__':main()
