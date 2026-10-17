"""Test-only worker adapter. Certificate validation remains enabled."""
import os
from pathlib import Path
import real_download_worker_v8 as worker

URL = 'https://example.com/video.mp4'
if os.environ.get('CLIPORA_VERIFIED_TLS_OFFLINE_ONLY') != '1':
    raise SystemExit('Offline verified TLS fixture is disabled')

def fixture_only(value):
    if value != URL:
        raise ValueError('Only fixed offline fixture allowed')
    return 'OfflineFixture'

worker.validate_video_url = fixture_only
original_options = worker.ydl_options

def verified_options(folder=None):
    options = original_options(folder)
    options.update({'nocheckcertificate': False, 'retries': 0,
                    'fragment_retries': 0, 'extractor_retries': 0,
                    'socket_timeout': 5, 'compat_opts': {'no-certifi'}})
    return options

# no-certifi selects system trust loading. SSL_CERT_FILE points only to the
# ephemeral fixture CA in this test process; no host/container store is changed.
worker.ydl_options = verified_options
job_id = os.environ['CLIPORA_TEST_JOB_ID']
result = worker.process_video(URL, job_id)
output = Path(os.environ['CLIPORA_TEST_DOWNLOAD_DIR']) / job_id / 'video.mp4'
if result.get('success') is not True or not output.is_file() or output.stat().st_size < 3000:
    raise RuntimeError('Invalid actual worker result')
if output.read_bytes()[4:8] != b'ftyp':
    raise RuntimeError('Invalid MP4 output')
print('PASS: actual v8 worker MP4 with certificate and hostname verification', flush=True)

# Keep tmpfs alive only long enough for the runner to export the verified file.
# Runner always removes this container; this deadline is a second safety bound.
if os.environ.get('CLIPORA_HOLD_VERIFIED_OUTPUT') == '1':
    import time
    time.sleep(90)
