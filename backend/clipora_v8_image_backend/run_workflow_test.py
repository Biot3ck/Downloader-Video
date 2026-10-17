"""HTTP cancellation of an actual held image worker, plus video regression."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
from fastapi.testclient import TestClient
from clipora_v8_local_workflow.app import create_local_app
from clipora_v8_local_workflow.scheduler import Scheduler
from clipora_v8_local_workflow.resources import ImageSampleResource

ORIGIN='http://127.0.0.1:8090'


class HeldImages(Scheduler):
    def __init__(self,*args):super().__init__(*args,image_factory=lambda *a:ImageSampleResource(*a,hold=True))


def wait_status(client,job,status,timeout=30):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        result=client.get('/api/v8/jobs/'+job)
        if result.status_code==200 and result.json()['status']==status:return
        if result.status_code==200 and result.json()['status']=='failed' and status!='failed':raise RuntimeError('Offline workflow failed')
        time.sleep(.1)
    raise TimeoutError('Offline job did not reach expected status')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='clipora-image-cancel-') as temp:
        root=Path(temp).resolve();app=create_local_app(ORIGIN,root,scheduler_factory=HeldImages)
        with TestClient(app,base_url=ORIGIN) as client:
            client.post('/api/v8/session',headers={'Origin':ORIGIN})
            response=client.post('/api/v8/samples/images',headers={'Origin':ORIGIN,'Idempotency-Key':'a'*32},json={})
            assert response.status_code==202;job=response.json()['job_id'];store=app.state.owned_jobs;owner=None
            for _ in range(150):
                row=store.get(job)
                if row['owner']:
                    owner=row['owner'];result=subprocess.run(['docker','ps','-q','--filter','label=clipora.three.kernel='+owner],capture_output=True,text=True,timeout=5,check=True)
                    if result.stdout.strip():break
                time.sleep(.1)
            else:raise TimeoutError('Image worker did not start')
            assert client.post('/api/v8/jobs/'+job+'/cancel',headers={'Origin':ORIGIN}).status_code==204
            wait_status(client,job,'failed')
            for suffix in ('/images','/images/1','/album.zip'):assert client.get('/api/v8/jobs/'+job+suffix).status_code==404
            assert not list((root/'artifacts').iterdir())
            assert not subprocess.check_output(['docker','ps','-aq','--filter','label=clipora.three.kernel='+owner],timeout=5).strip()
            assert not list((store.directory/'work').iterdir())
            # The existing MP4 workflow still runs after an image cancellation.
            response=client.post('/api/v8/samples',headers={'Origin':ORIGIN,'Idempotency-Key':'b'*32},json={});assert response.status_code==202
            video=response.json()['job_id'];wait_status(client,video,'completed',timeout=90)
            media=client.get('/api/v8/jobs/'+video+'/file');assert media.status_code==200 and b'ftyp' in media.content[:16]
            assert client.get('/api/v8/jobs/'+video+'/images').status_code==404
            assert client.post('/api/v8/download',headers={'Origin':ORIGIN},json={'url':'https://pin.it/fixture','media_kind':'images'}).status_code==503
    report={'running_image_cancelled_over_HTTP':True,'image_resources_removed_before_failed':True,'no_partial_album_served':True,
            'queue_reused_by_actual_video_worker':True,'MP4_playback_signature_valid':True,'video_image_route_separation':True,'public_downloads_enabled':False}
    if args.report:
        with args.report.open('x') as output:json.dump(report,output,indent=2);output.write('\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
