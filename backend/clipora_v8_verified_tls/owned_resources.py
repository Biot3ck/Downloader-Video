"""Ownership labels let restart recovery remove only this queue's fixture resources."""
import json
import os
import re
import subprocess
from uuid import uuid4

OWNER = 'clipora-v8-verified-offline'
JOB = os.environ.get('CLIPORA_OFFLINE_JOB_ID', uuid4().hex)
if not re.fullmatch(r'[0-9a-f]{32}', JOB):
    raise RuntimeError('Invalid offline resource owner')


def labels():
    return {'clipora.offline.owner': OWNER, 'clipora.offline.job': JOB}


def label_args():
    return [part for key,value in labels().items() for part in ('--label', key+'='+value)]


def cleanup_job(job_id):
    if not re.fullmatch(r'[0-9a-f]{32}', job_id):
        raise ValueError('Invalid recovery job')
    expected = {'clipora.offline.owner':OWNER, 'clipora.offline.job':job_id}
    filters = [part for key,value in expected.items() for part in ('--filter','label='+key+'='+value)]
    def run(args):
        result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise RuntimeError('Offline resource recovery failed')
        return result.stdout
    for kind in ('container','network'):
        args = ['ps','-aq'] if kind=='container' else ['network','ls','-q']
        for identity in run(args+filters).split():
            if not re.fullmatch(r'[0-9a-f]{12,64}', identity):
                raise RuntimeError('Invalid Docker resource identity')
            info = json.loads(run(['inspect',identity]))[0]
            actual = info.get('Config',{}).get('Labels',{}) if kind=='container' else info.get('Labels',{})
            if not all(actual.get(k)==v for k,v in expected.items()):
                raise RuntimeError('Recovery ownership mismatch')
            run(['rm','-f',identity] if kind=='container' else ['network','rm',identity])
