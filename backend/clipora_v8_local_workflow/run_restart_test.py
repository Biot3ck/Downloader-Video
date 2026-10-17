"""SIGKILL a disposable loopback web process while its owned helper is active."""
import asyncio
import fcntl
import http.client
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from fastapi.testclient import TestClient
from .app import create_local_app
from .resources import cleanup
from clipora_v8_web.owned_jobs import OwnedJobs

BACKEND=Path(__file__).resolve().parent.parent
BOOT='''import sys,uvicorn
from clipora_v8_local_workflow.app import create_local_app
from clipora_v8_local_workflow.scheduler import Scheduler
from clipora_v8_local_workflow.resources import SampleResource
class HeldScheduler(Scheduler):
 def __init__(self,store,artifacts):super().__init__(store,artifacts,factory=lambda *a:SampleResource(*a,hold=True))
uvicorn.run(create_local_app(sys.argv[1],sys.argv[2],scheduler_factory=HeldScheduler),host='127.0.0.1',port=int(sys.argv[3]),access_log=False,proxy_headers=False,log_level='error')
'''


def main():
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
    origin='http://127.0.0.1:'+str(port)
    with tempfile.TemporaryDirectory(prefix='clipora-web-restart-') as tmp:
        root=Path(tmp).resolve();process=None;owner=None;helper_released=False
        def request(method,path,body=None,cookie=None,key=None):
            connection=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
            headers={'Origin':origin,'Content-Type':'application/json'}
            if cookie:headers['Cookie']=cookie
            if key:headers['Idempotency-Key']=key
            try:
                connection.request(method,path,body=body,headers=headers)
                response=connection.getresponse();return response.status,response.read(),dict(response.getheaders())
            finally:connection.close()
        try:
            process=subprocess.Popen([sys.executable,'-B','-c',BOOT,origin,str(root),str(port)],cwd=BACKEND,
                                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            for _ in range(60):
                try:
                    if request('GET','/healthz')[0]==200:break
                except OSError:pass
                if process.poll() is not None:raise RuntimeError('Disposable web failed to start')
                time.sleep(.1)
            else:raise TimeoutError('Disposable web readiness')
            code,_,headers=request('POST','/api/v8/session');assert code==204
            cookie=headers['set-cookie'].split(';',1)[0]
            code,data,_=request('POST','/api/v8/samples',body='{}',cookie=cookie,key='c'*32);assert code==202
            job=json.loads(data);store=OwnedJobs(root)
            for _ in range(100):
                row=store.get(job['job_id'])
                if row['owner']:
                    owner=row['owner']
                    names=subprocess.check_output(['docker','ps','-q','--filter','label=clipora.three.kernel='+owner],text=True,timeout=5)
                    if names.strip():break
                time.sleep(.1)
            else:raise TimeoutError('Owned sample helper did not launch')
            # Kill only our disposable web process. Its helper must retain the
            # inherited flock and finish/clean before recovery can claim work.
            process.kill();process.wait(timeout=3)
            lock_path=store.directory/'scheduler.lock'
            fd=lock_path.open('rb')
            try:
                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:blocked=True
                else:blocked=False
                assert blocked,'Helper did not preserve leadership after web death'
                for _ in range(300):
                    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError:time.sleep(.1)
                    else:helper_released=True;break
                assert helper_released,'Helper did not terminate within test deadline'
            finally:fd.close()
            assert store.get(job['job_id'])['status']=='processing'
            app=create_local_app(origin,root)
            with TestClient(app,base_url=origin) as client:
                response=client.get('/api/v8/jobs/'+job['job_id'],headers={'Cookie':cookie})
                assert response.status_code==200 and response.json()['status']=='failed'
                assert client.get('/api/v8/jobs/'+job['job_id']+'/file',headers={'Cookie':cookie}).status_code==404
                assert not list((root/'artifacts').iterdir())
                assert not list((store.directory/'work').iterdir())
            report={'web_SIGKILL_during_owned_job':True,'helper_retained_leader_lock':True,
                    'recovery_waited_for_helper_completion':True,'interrupted_job_failed_without_retry':True,
                    'unfinished_file_not_served':True,'private_work_cleaned':True,'public_downloads_enabled':False}
            if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report,indent=2))
        finally:
            if process is not None and process.poll() is None:process.kill();process.wait(timeout=3)
            if owner and helper_released:asyncio.run(cleanup(owner))

if __name__=='__main__':main()
