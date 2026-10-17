"""Exercise actual v8 process_video against *only* the local HTTPS fixture."""
import json
import os
from pathlib import Path
import real_download_worker_v8 as worker

URL = 'https://example.com/video.mp4'

def fixture_url_only(value):
    if value != URL:
        raise ValueError('Only fixed synthetic fixture permitted')
    return 'OfflineFixture'

worker.validate_video_url = fixture_url_only
base_options = worker.ydl_options

def local_options(folder=None):
    opts = base_options(folder)
    opts.update({'nocheckcertificate': True, 'retries': 0,
                 'fragment_retries': 0, 'socket_timeout': 8})
    return opts

worker.ydl_options = local_options
job_id = os.environ['CLIPORA_TEST_JOB_ID']
result = worker.process_video(URL, job_id)
output = Path(os.environ['CLIPORA_TEST_DOWNLOAD_DIR']) / job_id / 'video.mp4'
assert result['success'] is True, result
assert output.is_file(), 'No output video'
assert 3000 < output.stat().st_size < 100000, 'Unexpected fixture size'
assert output.read_bytes()[4:8] == b'ftyp', 'Not MP4'
print('PASS: actual v8 process_video downloaded MP4 through local Gateway/Egress',flush=True)
