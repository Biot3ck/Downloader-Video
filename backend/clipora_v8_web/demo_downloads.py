"""Bundled sample media for the explicit local demo preview.

The public gate stays closed: ``/api/v8/download`` still returns 503. This module
serves three fixed files from ``assets/demo`` and never reads a caller-supplied
path, contacts the network, or starts a worker. Links are HMAC-signed and expire.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from .platforms import HOSTS, recognize_media

BASE = Path(__file__).resolve().parent
DEMO = BASE / 'assets' / 'demo'
TTL = 300
SAMPLES = {
    'video': ('sample-360p.mp4', 'video/mp4'),
    'hd': ('sample-720p.mp4', 'video/mp4'),
    'image': ('sample.jpg', 'image/jpeg'),
}
ALLOWED = {'video': frozenset({'video', 'hd'}), 'images': frozenset({'image'})}
PREVIEW = {'video': ('video', 640, 360), 'images': ('image', 1280, 720)}
PLATFORMS = frozenset(HOSTS.values())
DISPLAY = {'youtube': 'YouTube', 'tiktok': 'TikTok', 'instagram': 'Instagram', 'pinterest': 'Pinterest'}
CAPTION = """Demo caption · Clipora sample media
This text ships with the repository so the preview layout can be checked end to end. It is not the caption of the post you pasted, and Clipora did not fetch that post.

The bundled clip is three seconds of colour bars with a test tone. Use it to check line wrapping, blank lines, emoji 🙂, hashtags like #clipora #demo #sample, and how a long caption pushes the download buttons down the page.

Nothing on this page was downloaded from YouTube, TikTok, Instagram, or Pinterest."""


def _encode(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def _decode(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


async def _json_body(request, fields):
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise HTTPException(415, 'Send application/json.')
    try:
        data = await request.json()
        if not isinstance(data, dict) or set(data) != set(fields):
            raise ValueError('Send ' + ', '.join(sorted(fields)) + '.')
    except (ValueError, TypeError, UnicodeError) as exc:
        raise HTTPException(422, str(exc)) from None
    return data


def register(app, secret=None):
    """Attach demo routes. Callers must have checked loopback and the flag."""
    key = secret or secrets.token_bytes(32)

    def issue(fmt, platform):
        payload = json.dumps({'f': fmt, 'p': platform, 'e': int(time.time()) + TTL},
                             separators=(',', ':')).encode()
        return _encode(payload) + '.' + _encode(hmac.new(key, payload, hashlib.sha256).digest()[:16])

    def read(token):
        try:
            body, signature = token.split('.')
            payload = _decode(body)
            if not hmac.compare_digest(_decode(signature),
                                       hmac.new(key, payload, hashlib.sha256).digest()[:16]):
                raise ValueError('signature')
            data = json.loads(payload)
            fmt, platform, expires = data['f'], data['p'], data['e']
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise HTTPException(404, 'This sample link is not valid.') from None
        if fmt not in SAMPLES or platform not in PLATFORMS:
            raise HTTPException(404, 'This sample link is not valid.')
        if not isinstance(expires, int) or expires < time.time():
            raise HTTPException(410, 'This sample link expired. Ask for a new one.')
        return fmt, platform

    def sample_path(fmt):
        name, media_type = SAMPLES[fmt]
        path = DEMO / name
        if not path.is_file():
            raise HTTPException(503, 'The bundled sample file is missing from this checkout.')
        return path, media_type

    @app.post('/api/v8/demo/preview')
    async def demo_preview(request: Request):
        data = await _json_body(request, ('url', 'media_kind'))
        try:
            media_kind = data['media_kind']
            if media_kind not in PREVIEW:
                raise ValueError('Choose a supported media kind.')
            result = recognize_media(data['url'], media_kind)
        except (ValueError, TypeError, UnicodeError) as exc:
            raise HTTPException(422, str(exc)) from None
        fmt, width, height = PREVIEW[media_kind]
        sample_path(fmt)
        return {'sample': True, 'platform': result.platform, 'media_kind': media_kind,
                'title': f"Sample clip · {DISPLAY[result.platform]}",
                'caption': CAPTION,
                'duration_seconds': 3 if fmt == 'video' else None, 'width': width, 'height': height,
                'preview_url': '/api/v8/demo/preview/' + issue(fmt, result.platform),
                'poster_url': ('/api/v8/demo/preview/' + issue('image', result.platform)
                               if fmt != 'image' else None),
                'expires_in': TTL, 'network_access_performed': False}

    @app.post('/api/v8/demo/download')
    async def demo_download(request: Request):
        data = await _json_body(request, ('url', 'media_kind', 'format'))
        try:
            media_kind, fmt = data['media_kind'], data['format']
            if media_kind not in ALLOWED or fmt not in ALLOWED[media_kind]:
                raise ValueError('Choose a supported download type.')
            result = recognize_media(data['url'], media_kind)
        except (ValueError, TypeError, UnicodeError) as exc:
            raise HTTPException(422, str(exc)) from None
        path, _ = sample_path(fmt)
        return {'sample': True, 'format': fmt, 'platform': result.platform,
                'filename': f'clipora-sample-{result.platform}-{fmt}{path.suffix}',
                'url': '/api/v8/demo/file/' + issue(fmt, result.platform),
                'expires_in': TTL, 'network_access_performed': False}

    @app.get('/api/v8/demo/preview/{token}')
    def demo_preview_file(token: str):
        fmt, platform = read(token)
        path, media_type = sample_path(fmt)
        return FileResponse(path, media_type=media_type, content_disposition_type='inline',
                            filename=f'clipora-sample-{platform}-{fmt}{path.suffix}')

    @app.get('/api/v8/demo/file/{token}')
    def demo_file(token: str):
        fmt, platform = read(token)
        path, media_type = sample_path(fmt)
        return FileResponse(path, media_type=media_type,
                            filename=f'clipora-sample-{platform}-{fmt}{path.suffix}')
