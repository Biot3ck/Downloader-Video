"""Prove kernel ENOSPC enforcement in a disposable, networkless worker."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


def main():
    name='clipora-quota-'+uuid.uuid4().hex[:10]
    script='''import errno,json,os
v=os.statvfs('/output')
assert v.f_blocks*v.f_frsize<=1024*1024
try:
    with open('/output/fill','wb',buffering=0) as f:
        for _ in range(3): f.write(b'x'*(1024*1024))
except OSError as e:
    assert e.errno==errno.ENOSPC
else:
    raise AssertionError('Workspace exceeded kernel quota')
try:
    open('/outside-workspace','wb')
except OSError as e:
    assert e.errno==errno.EROFS
else:
    raise AssertionError('Root filesystem writable')
print(json.dumps({'enospc_enforced':True,'root_read_only':True,'network':'none','workspace_limit_bytes':v.f_blocks*v.f_frsize}))
'''
    args=['docker','run','--rm','--pull','never','--name',name,'--network','none',
          '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
          '--memory','128m','--cpus','1','--pids-limit','32','--user',f'{os.getuid()}:{os.getgid()}',
          '--tmpfs',f'/output:rw,nosuid,nodev,noexec,size=1m,uid={os.getuid()},gid={os.getgid()},mode=0700',
          '--entrypoint','python3','clipora-worker:v8-dns','-B','-c',script]
    try:
        result=subprocess.run(args,capture_output=True,text=True,timeout=30,check=True)
        report=json.loads(result.stdout)
        if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)


if __name__=='__main__':main()
