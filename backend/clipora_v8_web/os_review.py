"""Read-only Debian image review against a separately retrieved tracker snapshot.

No downloads, package installation, Docker context changes or activation.
Only this file is copied into a readonly mount; containers have network=none.
Tracker findings are source-package/version matches, not exploit proof.
"""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from uuid import uuid4

TRACKER_URL='https://security-tracker.debian.org/tracker/data/json'


def version(value):
    if type(value) is not str or not re.fullmatch(r'[0-9][A-Za-z0-9.+:~\-]{0,199}',value):
        raise ValueError('Invalid Debian version')
    return value


@lru_cache(maxsize=8192)
def at_least(installed,fixed):
    result=subprocess.run(['dpkg','--compare-versions',version(installed),'ge',version(fixed)],
                          capture_output=True,timeout=2)
    if result.returncode not in (0,1):raise ValueError('Debian version comparison failed')
    return result.returncode==0


def review(inventory,tracker,compare=at_least):
    if type(inventory) is not dict or type(tracker) is not dict or not tracker:
        raise ValueError('Invalid review input')
    system=inventory.get('os',{})
    if type(system) is not dict:raise ValueError('Invalid OS inventory')
    release=system.get('VERSION_CODENAME')
    if system.get('ID')!='debian' or type(release) is not str or not re.fullmatch('[a-z]{2,24}',release):
        raise ValueError('Debian release required')
    rows=inventory.get('packages')
    if type(rows) is not list or not 1<=len(rows)<=4096:raise ValueError('Invalid package inventory')
    grouped=defaultdict(list);installed_count=0
    for row in rows:
        if type(row) is not dict:raise ValueError('Invalid package row')
        if row.get('status')!='installed':continue
        name=row.get('source');binary=row.get('binary')
        if (type(name) is not str or not re.fullmatch('[a-z0-9][a-z0-9+.-]{0,127}',name)
                or type(binary) is not str or not re.fullmatch('[a-z0-9][a-z0-9+.:-]{0,159}',binary)):
            raise ValueError('Invalid source package mapping')
        grouped[(name,version(row.get('source_version')))].append(binary);installed_count+=1
    if not grouped:raise ValueError('No installed packages')
    counts=Counter();findings=[];without_source=[];without_release=[]
    for (name,installed),binaries in sorted(grouped.items()):
        if name not in tracker:without_source.append(name);continue
        entries=tracker[name]
        if type(entries) is not dict:raise ValueError('Invalid source tracker record')
        matched=0
        for identifier,entry in sorted(entries.items()):
            if type(entry) is not dict or type(entry.get('releases')) is not dict:
                raise ValueError('Invalid advisory')
            state=entry['releases'].get(release)
            if state is None:continue
            if type(state) is not dict:raise ValueError('Invalid release record')
            matched+=1;status=state.get('status');fixed=state.get('fixed_version')
            if status=='resolved' and fixed=='0':classification='not_affected_marker'
            elif status in ('open','resolved') and state.get('urgency')=='unimportant':classification='debian_unimportant'
            elif status=='resolved' and type(fixed) is str and fixed:
                classification='fixed_in_installed_version' if compare(installed,version(fixed)) else 'upgrade_required'
            elif status=='open':classification='open_review_required'
            else:classification='undetermined'
            counts[classification]+=1
            if classification not in ('not_affected_marker','fixed_in_installed_version'):
                findings.append({'source':name,'installed_source_version':installed,'binaries':sorted(binaries),
                    'id':identifier,'classification':classification,'fixed_version':fixed,
                    'urgency':state.get('urgency'),'nodsa':state.get('nodsa'),'nodsa_reason':state.get('nodsa_reason')})
        if not matched:without_release.append(name)
    return {'scope':'Debian installed source package/version matching only','release':release,
        'installed_binaries':installed_count,'source_versions':len(grouped),'counts':dict(counts),
        'sources_without_tracker_record':sorted(set(without_source)),
        'sources_without_release_record':sorted(set(without_release)),'findings':findings,
        'triage_complete':False,'production_security_approved':False,'public_downloads_enabled':False,
        'limitations':['Open/undetermined records require reachability review; no-dsa is not a waiver.',
          'Unimportant is Debian classification, not a blanket risk acceptance by Clipora.',
          'Missing records do not prove absence of vulnerabilities.',
          'Does not cover kernel/host, Python or manually built/embedded libraries.']}


def probe():
    fields=['binary','binary_version','source','source_version','status']
    result=subprocess.run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\t${db:Status-Status}\n'],
                          capture_output=True,text=True,check=True,timeout=10)
    system=platform.freedesktop_os_release()
    return {'os':{k:system.get(k) for k in ('ID','VERSION_ID','VERSION_CODENAME')},
            'architecture':platform.machine(),'python':platform.python_version(),
            'packages':[dict(zip(fields,line.split('\t'))) for line in result.stdout.splitlines()]}


def run_worker(image,folder,mode,payload=None):
    name='clipora-os-review-'+uuid4().hex
    try:
        result=subprocess.run(['docker','run','-i','--rm','--pull','never','--name',name,
            '--label','clipora.os.review='+name,'--network','none','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--user','10001:10001','--memory','256m',
            '--cpus','1','--pids-limit','32','--mount',f'type=bind,source={folder},target=/audit,readonly',
            '--entrypoint','python3',image,'-B','/audit/os_review.py',mode],
            input=json.dumps(payload) if payload is not None else None,
            capture_output=True,text=True,timeout=60)
        if result.returncode:raise RuntimeError('Isolated OS review failed')
        if len(result.stdout)>8*1024*1024:raise ValueError('Review output exceeds bound')
        return json.loads(result.stdout)
    finally:
        check=subprocess.run(['docker','inspect',name,'--format','{{json .Config.Labels}}'],capture_output=True,text=True,timeout=10)
        if check.returncode==0:
            if json.loads(check.stdout).get('clipora.os.review')!=name:raise RuntimeError('Cleanup ownership mismatch')
            subprocess.run(['docker','rm','-f',name],capture_output=True,check=True,timeout=10)


def main():
    if sys.argv[1:]==['--probe']:
        print(json.dumps(probe()));return 0
    if sys.argv[1:]==['--evaluate']:
        value=json.load(sys.stdin);print(json.dumps(review(value['inventory'],value['tracker'])));return 0
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-id',required=True)
    parser.add_argument('--tracker',type=Path,required=True)
    parser.add_argument('--tracker-sha256',required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch('sha256:[a-f0-9]{64}',args.image_id):parser.error('Exact local image ID required')
    if not re.fullmatch('[a-f0-9]{64}',args.tracker_sha256):parser.error('Tracker SHA256 required')
    if args.tracker.is_symlink() or not 1<=args.tracker.stat().st_size<=128*1024*1024:
        raise ValueError('Tracker file exceeds policy')
    with args.tracker.open('rb') as stream:raw=stream.read(128*1024*1024+1)
    if len(raw)>128*1024*1024 or hashlib.sha256(raw).hexdigest()!=args.tracker_sha256:
        raise ValueError('Tracker size or SHA256 mismatch')
    tracker=json.loads(raw)
    def terminate(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,terminate)
    with tempfile.TemporaryDirectory(prefix='clipora-os-review-') as temporary:
        folder=Path(temporary).resolve();folder.chmod(0o755)
        shutil.copyfile(Path(__file__),folder/'os_review.py');(folder/'os_review.py').chmod(0o444)
        inventory=run_worker(args.image_id,folder,'--probe')
        # Validate inventory first and transfer only relevant advisory records.
        review(inventory,{'__validation__':{}})
        relevant={p['source']:tracker[p['source']] for p in inventory['packages'] if p['status']=='installed' and p['source'] in tracker}
        report=run_worker(args.image_id,folder,'--evaluate',{'inventory':inventory,'tracker':relevant})
    report.update(reviewed_at=datetime.now(timezone.utc).isoformat(),image_id=args.image_id,
                  tracker_url=TRACKER_URL,tracker_sha256=args.tracker_sha256,
                  isolated_network='none',inventory=inventory)
    fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:stream.write(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'installed_binaries':report['installed_binaries'],'source_versions':report['source_versions'],
                      'counts':report['counts'],'production_security_approved':False}))
    return 2  # Review tool never issues a production/security approval.


if __name__=='__main__':sys.exit(main())
