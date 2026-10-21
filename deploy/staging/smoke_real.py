#!/usr/bin/env python3
"""End-to-end smoke test for the real download routes on a loopback origin.

This is deliberately stdlib-only so it can run on the staging host, inside CI,
or through an SSH tunnel without installing anything. It exercises the same
HTTP contract the browser uses: preview, file streaming, MP4, MP3 and the
closed public gate.

Usage:
    python deploy/staging/smoke_real.py --base-url http://127.0.0.1:8080
    python deploy/staging/smoke_real.py --base-url http://127.0.0.1:8091 \
        --url https://www.tiktok.com/@tiktok/video/7694797676306615583

Exit code 0 means every check passed. Nothing is written outside --workdir.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = 'https://www.tiktok.com/@tiktok/video/7694797676306615583'
TIMEOUT = 240


def request(method, url, *, origin, payload=None, timeout=TIMEOUT, headers=None):
    data = None
    merged = {'Origin': origin, 'Accept': '*/*'}
    if headers:
        merged.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode()
        merged['Content-Type'] = 'application/json'
    headers = merged
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read(400).decode('utf-8', 'replace')
        raise SystemExit(f'{method} {url} -> HTTP {exc.code}: {body}') from None


def json_call(base, path, payload, origin):
    with request('POST', base + path, origin=origin, payload=payload) as response:
        return response.status, json.loads(response.read())


def save(base, path, origin, destination):
    with request('GET', base + path, origin=origin) as response:
        content_type = response.headers.get('content-type', '')
        length = response.headers.get('content-length')
        destination.write_bytes(response.read())
    size = destination.stat().st_size
    if length is not None and int(length) != size:
        raise SystemExit(f'{path}: content-length {length} but read {size} bytes')
    return content_type, size


def wait_health(base, origin, deadline=90):
    end = time.monotonic() + deadline
    last = None
    while time.monotonic() < end:
        try:
            with request('GET', base + '/healthz', origin=origin, timeout=5) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = exc
            time.sleep(2)
    raise SystemExit(f'healthz did not become ready: {last}')


def probe(path):
    if not shutil.which('ffprobe'):
        return None
    result = subprocess.run(
        ['ffprobe', '-v', 'error',
         '-show_entries', 'stream=codec_name,width,height,sample_rate,bit_rate',
         '-show_entries', 'format=duration,size',
         '-of', 'json', str(path)],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'ffprobe rejected {path.name}: {result.stderr.strip()}')
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    parser.add_argument('--url', default=DEFAULT_URL)
    parser.add_argument('--workdir', type=Path, default=Path('smoke-real'))
    parser.add_argument('--hd', action='store_true', help='also download the HD variant')
    args = parser.parse_args()

    base = args.base_url.rstrip('/')
    if not base.startswith(('http://127.0.0.1:', 'http://localhost:', 'http://[::1]:')):
        raise SystemExit('The real routes only exist on a loopback origin.')
    origin = base
    args.workdir.mkdir(parents=True, exist_ok=True)

    health = wait_health(base, origin)
    checks = {'healthz': health}
    assert health.get('real_downloads_enabled') is True, health
    assert health.get('public_downloads_enabled') is False, health
    assert health.get('ready_for_public_launch') is False, health

    status, preview = json_call(base, '/api/v8/real/preview',
                                {'url': args.url, 'media_kind': 'video'}, origin)
    assert status == 200, status
    checks['preview'] = {key: preview.get(key) for key in
                         ('platform', 'media_kind', 'duration_seconds', 'width',
                          'height', 'formats')}
    assert preview.get('platform') == 'tiktok', preview
    assert set(preview.get('formats') or []) >= {'video', 'mp3'}, preview
    assert (preview.get('width') or 0) > 0 and (preview.get('height') or 0) > 0, preview

    content_type, size = save(base, preview['preview_url'], origin,
                              args.workdir / 'preview.mp4')
    checks['preview_file'] = {'content_type': content_type, 'bytes': size}
    assert content_type.startswith('video/mp4'), content_type
    assert size > 100_000, size

    with request('GET', base + preview['preview_url'], origin=origin,
                 headers={'Range': 'bytes=0-1023'}) as response:
        partial = response.read()
        checks['range'] = {'status': response.status,
                           'bytes': len(partial),
                           'content_range': response.headers.get('content-range')}
    assert checks['range']['status'] == 206, checks['range']
    assert len(partial) == 1024, checks['range']

    status, video = json_call(base, '/api/v8/real/download',
                              {'url': args.url, 'media_kind': 'video', 'format': 'video'},
                              origin)
    assert status == 200 and video.get('real') is True, video
    content_type, size = save(base, video['url'], origin,
                              args.workdir / video['filename'])
    checks['video'] = {'content_type': content_type, 'bytes': size,
                       'filename': video['filename']}
    assert content_type.startswith('video/mp4'), content_type
    assert size > 100_000, size

    if args.hd:
        status, hd = json_call(base, '/api/v8/real/download',
                               {'url': args.url, 'media_kind': 'video', 'format': 'hd'},
                               origin)
        assert status == 200 and hd.get('real') is True, hd
        content_type, size = save(base, hd['url'], origin,
                                  args.workdir / hd['filename'])
        checks['hd'] = {'content_type': content_type, 'bytes': size,
                        'filename': hd['filename']}
        assert content_type.startswith('video/mp4'), content_type
        assert size > 100_000, size

    status, audio = json_call(base, '/api/v8/real/download',
                              {'url': args.url, 'media_kind': 'video', 'format': 'mp3'},
                              origin)
    assert status == 200 and audio.get('real') is True, audio
    content_type, size = save(base, audio['url'], origin,
                              args.workdir / audio['filename'])
    checks['mp3'] = {'content_type': content_type, 'bytes': size,
                     'filename': audio['filename']}
    assert content_type.startswith('audio/mpeg'), content_type
    assert size > 50_000, size

    try:
        request('POST', base + '/api/v8/download', origin=origin,
                payload={'url': args.url, 'media_kind': 'video', 'format': 'video'})
    except SystemExit as exc:
        checks['public_gate'] = str(exc)
    else:
        raise SystemExit('the public download gate answered 200')
    assert 'HTTP 503' in checks['public_gate'], checks['public_gate']

    for name in ('video', 'mp3'):
        entry = checks[name]
        details = probe(args.workdir / entry['filename'])
        if details:
            entry['ffprobe'] = details

    print(json.dumps(checks, indent=2, sort_keys=True))
    print('SMOKE OK')


if __name__ == '__main__':
    sys.exit(main())
