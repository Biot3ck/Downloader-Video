"""Candidate web boundary, with public downloads unconditionally disabled.

No legacy routers, Docker access, scheduler, or outbound network dependency.
"""
import asyncio
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from .platforms import recognize_media, MEDIA_PLATFORMS
from .rate_limit import Limiter, LimitReached

BASE = Path(__file__).resolve().parent
CSP = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; connect-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'"
HEADERS = {'Content-Security-Policy': CSP, 'X-Content-Type-Options': 'nosniff',
           'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer',
           'Permissions-Policy': 'camera=(), microphone=(), geolocation=()', 'Cache-Control': 'no-store'}


def validate_origin(value):
    p = urlsplit(value)
    if (p.scheme not in ('http', 'https') or not p.hostname or p.username is not None or p.password is not None
            or p.path or p.query or p.fragment or p.netloc != p.netloc.lower()
            or '*' in value or any(ord(c) <= 32 or ord(c) == 127 for c in value)):
        raise ValueError('Configure one exact canonical origin without a path')
    if p.scheme == 'http' and p.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('Non-loopback origins require HTTPS')
    _ = p.port
    return p


class Boundary:
    def __init__(self, app, origin, limiter=None):
        self.app, self.origin, self.limiter = app, origin, limiter
        self.authority = validate_origin(origin).netloc

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        async def secured(message):
            if message['type'] == 'http.response.start':
                message = {**message, 'headers': list(message.get('headers', []))}
                protected = {k.lower().encode() for k in HEADERS}
                message['headers'] = [(k,v) for k,v in message['headers'] if k.lower() not in protected]
                message['headers'].extend((k.lower().encode(),v.encode()) for k,v in HEADERS.items())
            await send(message)
        async def reject(code, detail, extra=None):
            await JSONResponse({'detail': detail}, status_code=code, headers=extra)(scope, receive, secured)
        headers = scope.get('headers', [])
        hosts = [v.decode('latin-1') for k,v in headers if k.lower() == b'host']
        if hosts != [self.authority]:
            return await reject(400, 'Invalid host.')
        if scope['method'] not in ('GET', 'HEAD', 'POST'):
            return await reject(405, 'Method not allowed.')
        if scope['method'] == 'POST':
            origins = [v.decode('latin-1') for k,v in headers if k.lower() == b'origin']
            if origins != [self.origin]:
                return await reject(403, 'Same-origin request required.')
            if any(k.lower() == b'content-encoding' for k,v in headers):
                return await reject(415, 'Encoded request bodies are not supported.')
            lengths = [v for k,v in headers if k.lower() == b'content-length']
            if len(lengths) > 1 or (lengths and (not lengths[0].isdigit() or int(lengths[0]) > 4096)):
                return await reject(413, 'Request body exceeds 4096 bytes.')
            if self.limiter is not None:
                try:
                    client = scope.get('client')
                    if not client:raise ValueError('Missing client')
                    await asyncio.to_thread(self.limiter.admit, client[0])
                except LimitReached as exc:
                    return await reject(429, 'Too many requests. Please try again shortly.', {'Retry-After':str(exc.retry_after)})
                except (OSError, ValueError, sqlite3.Error):
                    return await reject(503, 'Request admission is temporarily unavailable.')
            body = bytearray()
            try:
                async with asyncio.timeout(5):
                    while True:
                        message = await receive()
                        if message['type'] == 'http.disconnect':return
                        chunk = message.get('body', b'')
                        if len(body) + len(chunk) > 4096:
                            return await reject(413, 'Request body exceeds 4096 bytes.')
                        body.extend(chunk)
                        if not message.get('more_body', False):break
            except TimeoutError:
                return await reject(408, 'Request body timed out.')
            delivered = False
            async def buffered():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()
            return await self.app(scope, buffered, secured)
        return await self.app(scope, receive, secured)


def create_app(origin='http://127.0.0.1:8090', state_dir=None, *, offline_sample_enabled=False):
    validate_origin(origin)
    app = FastAPI(title='Clipora staging', docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(Boundary, origin=origin, limiter=Limiter(state_dir or BASE.parent / 'clipora_v8_web_runtime'))
    @app.get('/healthz')
    def health():
        return {'status': 'ok', 'public_downloads_enabled': False, 'ready_for_public_launch': False}
    @app.get('/api/v8/ui/config')
    def config():
        return {'public_downloads_enabled': False, 'offline_sample_enabled': offline_sample_enabled,
                'planned_platforms': ['youtube', 'tiktok', 'instagram', 'pinterest'],
                'planned_media': {kind: list(platforms) for kind, platforms in MEDIA_PLATFORMS.items()}}
    @app.get('/')
    @app.get('/app')
    def page():return FileResponse(BASE / 'index.html', media_type='text/html')
    @app.get('/assets/app.js')
    def script():return FileResponse(BASE / 'assets/app.js', media_type='text/javascript')
    @app.get('/assets/style.css')
    def style():return FileResponse(BASE / 'assets/style.css', media_type='text/css')
    # Developer utilities are only served by the explicit offline loopback
    # preview. Default/HTTPS/container product entrypoints keep returning 404.
    parsed_origin = validate_origin(origin)
    if (offline_sample_enabled and parsed_origin.scheme == 'http'
            and parsed_origin.hostname in ('127.0.0.1', 'localhost', '::1')):
        @app.get('/dev')
        def developer_page():return FileResponse(BASE / 'dev.html', media_type='text/html')
        @app.get('/assets/dev.js')
        def developer_script():return FileResponse(BASE / 'assets/dev.js', media_type='text/javascript')
        @app.get('/assets/dev.css')
        def developer_style():return FileResponse(BASE / 'assets/dev.css', media_type='text/css')
    @app.post('/api/v8/validate')
    async def validate_url(request: Request):
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            raise HTTPException(415, 'Send application/json.')
        try:
            data = await request.json()
            if not isinstance(data, dict) or set(data) not in ({'url'}, {'url', 'media_kind'}):
                raise ValueError('Send one post URL and an optional media kind.')
            media_kind = data.get('media_kind', 'video')
            result = recognize_media(data['url'], media_kind)
        except (ValueError, TypeError, UnicodeError) as exc:
            raise HTTPException(422, str(exc)) from None
        return {'platform': result.platform, 'normalized_url': result.url, 'media_kind': media_kind,
                'public_downloads_enabled': False, 'network_access_performed': False}
    @app.post('/api/v8/download')
    def disabled():
        raise HTTPException(503, 'Public downloads are not available yet.')
    return app


app = create_app(os.environ.get('CLIPORA_WEB_ORIGIN', 'http://127.0.0.1:8090'), os.environ.get('CLIPORA_WEB_STATE'))
