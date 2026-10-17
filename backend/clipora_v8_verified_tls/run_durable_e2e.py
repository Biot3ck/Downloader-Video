"""Actual Docker job + web lifecycle restart, using isolated SQLite and staging."""
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import time
from unittest.mock import patch

BACKEND=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(BACKEND))


def main():
    os.environ['CLIPORA_V8_OFFLINE_BROWSER_TEST']='1'
    os.environ['CLIPORA_V8_USE_COMPOSE']='1'
    # Only suppress unrelated legacy sweeper during import, not the scheduler.
    with patch('threading.Thread.start'):
        from clipora_v8_fastapi_mvp.main_v8 import app
    from clipora_v8_browser_real_mp4 import routes
    from clipora_v8_browser_real_mp4.job_store import JobStore
    from fastapi.testclient import TestClient
    with tempfile.TemporaryDirectory(prefix='clipora-durable-e2e-') as tmp:
        root=Path(tmp);staging=root/'staging';staging.mkdir()
        database=JobStore(root/'state')
        with patch.object(routes,'STORE',database),patch.object(routes,'STAGING',staging):
            with TestClient(app) as client:
                created=client.post('/api/v8/real-offline/jobs');assert created.status_code==202,created.text
                job=created.json()['job_id'];status_url=created.json()['status_url']
                deadline=time.monotonic()+100
                while time.monotonic()<deadline:
                    state=client.get(status_url).json()
                    if state['status'] in ('completed','failed'):break
                    time.sleep(.2)
                assert state['status']=='completed',state
                data=client.get(state['download_url']).content
                expected=(BACKEND/'clipora_v8_real_guarded_e2e/fixtures/video.mp4').read_bytes()
                assert data==expected
            # A fresh Python process must see the committed completed result.
            script = ('import sys;sys.path.insert(0,sys.argv[1]);'
                      'from clipora_v8_browser_real_mp4.job_store import JobStore;'
                      'assert JobStore(sys.argv[2]).get(sys.argv[3])["status"]=="completed"')
            subprocess.run([sys.executable,'-B','-c',script,str(BACKEND),str(root/'state'),job],check=True,capture_output=True,timeout=10)
            # Recreate the store and web lifespan; no in-memory job data exists.
            reopened=JobStore(root/'state')
            with patch.object(routes,'STORE',reopened):
                with TestClient(app) as client:
                    state=client.get(status_url).json();assert state['status']=='completed'
                    part=client.get(state['download_url'],headers={'Range':'bytes=0-15'})
                    assert part.status_code==206 and part.content==expected[:16]
                    assert client.post('/api/v8/download',json={'url':'https://example.com/video.mp4'}).status_code==503
            report={'actual_compose_job':True,'fresh_process_reads_completed':True,'durable_status_after_reopen':True,'web_lifespan_restarted':True,'mp4_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'range_after_restart':206,'public_download_status':503}
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: durable actual Compose job, web lifecycle restart, unchanged MP4, HTTP Range')


if __name__=='__main__':main()
