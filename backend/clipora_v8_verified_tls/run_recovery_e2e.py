"""Disposable Docker ownership/restart test. Never targets pre-existing resources."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4
from unittest.mock import patch

BACKEND=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(BACKEND))
from clipora_v8_verified_tls.owned_resources import OWNER,cleanup_job
from clipora_v8_browser_real_mp4.job_store import JobStore
from clipora_v8_browser_real_mp4 import routes


def docker(*args):
    result=subprocess.run(['docker',*args],capture_output=True,text=True,timeout=15)
    if result.returncode:raise RuntimeError('Recovery test Docker command failed: '+result.stderr[-500:])
    return result.stdout.strip()


def exists(identity):
    return subprocess.run(['docker','inspect',identity],capture_output=True,timeout=15).returncode==0


def main():
    foreign=uuid4().hex
    known_jobs=[foreign]
    try:
        with tempfile.TemporaryDirectory(prefix='clipora-recovery-e2e-') as tmp:
            root=Path(tmp);db=JobStore(root/'state')
            interrupted=db.create();queued=db.create();db.claim('dead-owner');known_jobs.append(interrupted['job_id'])
            resources=[]
            for job in (interrupted['job_id'],foreign):
                labels=['--label','clipora.offline.owner='+OWNER,'--label','clipora.offline.job='+job]
                network=docker('network','create','--internal',*labels,'clipora-recovery-net-'+job[:10])
                container=docker('create','--pull','never','--name','clipora-recovery-worker-'+job[:10],
                                 '--network',network,*labels,'--read-only','--cap-drop','ALL',
                                 '--security-opt','no-new-privileges','--memory','64m','--cpus','.25','--pids-limit','32',
                                 '--user',f'{os.getuid()}:{os.getgid()}','--entrypoint','python3',
                                 'clipora-worker:v8-dns','-B','-c','import time;time.sleep(60)')
                docker('start',container)
                resources.append((container,network))
            def complete(job,owner,fd):
                assert not exists(resources[0][0]) and not exists(resources[0][1])
                db.finish(job['job_id'],owner,False,'Test successor admitted after recovery')
            with patch.object(routes,'STORE',db),patch.object(routes,'STAGING',root/'staging'),patch.object(routes,'execute',side_effect=complete):
                assert routes.dispatch_once()
            assert db.get(interrupted['job_id'])['status']=='failed'
            assert exists(resources[1][0]) and exists(resources[1][1])
            report={'interrupted_job_failed_after_cleanup':True,'owned_container_and_network_removed':True,'different_job_container_and_network_preserved':True,'successor_claimed_only_after_recovery':True}
        if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
        print('PASS: Docker ownership recovery, foreign job resources preserved, successor fenced')
    finally:
        for job in known_jobs:cleanup_job(job)


if __name__=='__main__':main()
