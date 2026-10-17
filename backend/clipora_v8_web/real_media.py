"""Loopback-only real extraction and download helpers.

The public gate stays closed: ``/api/v8/download`` still returns 503 and these
routes are registered only when ``create_app(real_downloads_enabled=True)`` is
combined with a loopback origin. This module is therefore never imported by the
recognition-only entrypoints or the container image.

Two extraction paths are used:

* yt-dlp for video and audio posts (all four platforms);
* per-platform post readers for image posts, because yt-dlp only understands
  video. TikTok and Instagram reuse yt-dlp's own signed web session; Pinterest
  is read from the public pin page.

Every preview and file URL is HMAC-signed and expires. Tokens never carry a
caller-supplied filesystem path, and proxied CDN hosts are checked to be public.
"""
import asyncio
import base64
import hashlib
import hmac
import html
import ipaddress
import json
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from .platforms import recognize_media

MAX_BYTES = 100 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_TOTAL = 50 * 1024 * 1024
MAX_IMAGES = 20
MAX_DURATION = 600
TTL = 900
CACHE_SECONDS = 3600
MAX_REDIRECTS = 3
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36')
MEDIA_TYPES = ('image/', 'video/', 'audio/', 'application/octet-stream')

SELECTORS = {
    'video': ('bv*+ba/b', 'res:720'),
    'hd': ('bv*+ba/b', 'res:1080'),
    'mp3': ('ba/b', None),
}
KINDS = {'video': ('video', 'hd', 'mp3'), 'audio': ('mp3',), 'images': ('image',)}
REFERERS = {
    'tiktok': 'https://www.tiktok.com/',
    'instagram': 'https://www.instagram.com/',
    'pinterest': 'https://www.pinterest.com/',
    'youtube': 'https://www.youtube.com/',
}
IMAGE_MIME = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}


class MediaError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def _impersonation_target():
    """Return a browser TLS fingerprint target, or None when curl_cffi is absent.

    TikTok serves an anti-bot page to datacenter IPs when the TLS handshake
    looks like Python. The GitHub Actions spike went from 0/14 to 14/14 on
    TikTok purely by adding ``--impersonate chrome``, so production needs the
    same. curl_cffi stays optional: demo mode and the test suite must keep
    working on a machine that never installed it.
    """
    try:
        import curl_cffi  # noqa: F401
        from yt_dlp.networking.impersonate import ImpersonateTarget
    except ImportError:
        return None
    return ImpersonateTarget.from_str('chrome')


def _ytdl_opts():
    options = {'quiet': True, 'no_warnings': True, 'noprogress': True,
               'noplaylist': True, 'socket_timeout': 20, 'retries': 2,
               'extractor_retries': 2}
    target = _impersonation_target()
    if target is not None:
        options['impersonate'] = target
    return options


def _ytdl_url(url, platform):
    # yt-dlp's TikTok extractor only matches /video/ URLs, but the same post id
    # serves the slideshow payload. Image posts are read separately.
    if platform == 'tiktok' and '/photo/' in url:
        return url.replace('/photo/', '/video/', 1)
    return url


def _public_url(url):
    """Reject non-HTTPS, credential and private-address URLs before dialing."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise MediaError('The platform returned an invalid media link.', 502) from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.port not in (None, 443)):
        raise MediaError('The platform returned an invalid media link.', 502)
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise MediaError('The platform media host could not be resolved.', 502) from None
    for entry in addresses:
        address = ipaddress.ip_address(entry[4][0])
        if not address.is_global or address.is_multicast:
            raise MediaError('The platform returned a non-public media host.', 502)
    return url


def _duration_of(path):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                 '-of', 'json', str(path)], capture_output=True, text=True,
                                timeout=20, check=True)
        return float(json.loads(result.stdout)['format']['duration'])
    except (subprocess.SubprocessError, OSError, KeyError, ValueError, TypeError):
        return None


def _to_mp4(source, output):
    """Make the file playable in browsers: H.264 + AAC in a faststart MP4."""
    try:
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                                'stream=codec_type,codec_name,pix_fmt', '-of', 'json',
                                str(source)], capture_output=True, text=True, timeout=20,
                               check=True)
        streams = json.loads(probe.stdout).get('streams', [])
    except (subprocess.SubprocessError, OSError, ValueError):
        raise MediaError('The downloaded file could not be inspected.', 502) from None
    video = next((s for s in streams if s.get('codec_type') == 'video'), None)
    audio = next((s for s in streams if s.get('codec_type') == 'audio'), None)
    if video is None:
        raise MediaError('The platform returned audio only; use the Audio Downloader.', 422)
    if (source.suffix.lower() == '.mp4' and video.get('codec_name') == 'h264'
            and video.get('pix_fmt') == 'yuv420p'
            and (audio is None or audio.get('codec_name') == 'aac')):
        shutil.copy2(source, output)
        return
    command = ['ffmpeg', '-y', '-i', str(source), '-map', '0:v:0', '-map', '0:a:0?',
               '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(output)]
    try:
        subprocess.run(command, capture_output=True, text=True, timeout=300, check=True)
    except (subprocess.SubprocessError, OSError):
        raise MediaError('The downloaded video could not be converted.', 502) from None


def _to_mp3(source, output):
    try:
        subprocess.run(['ffmpeg', '-y', '-i', str(source), '-vn', '-c:a', 'libmp3lame',
                        '-b:a', '192k', str(output)], capture_output=True, text=True,
                       timeout=300, check=True)
    except (subprocess.SubprocessError, OSError):
        raise MediaError('The downloaded audio could not be converted to MP3.', 502) from None


def _progress_hook(progress):
    downloaded = progress.get('downloaded_bytes') or 0
    total = progress.get('total_bytes') or progress.get('total_bytes_estimate') or 0
    if max(downloaded, total) > MAX_BYTES:
        raise MediaError('This file is larger than the 100 MB limit.', 413)


def _ydl_error(exc):
    """Translate yt-dlp failures into answers a visitor can act on."""
    text = str(exc).lower()
    if 'no video formats' in text or 'there is no video' in text:
        return MediaError('This post contains photos only. Use the Photo Downloader.', 422)
    if 'private' in text or 'login' in text or 'not available' in text:
        return MediaError('This post is private or unavailable.', 422)
    return MediaError('The platform did not return this post. It may be private or removed.', 502)


def _download_media(url, platform, fmt, folder):
    """Run one yt-dlp download pass and return a browser-ready local file."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    options = _ytdl_opts()
    selector, target = SELECTORS[fmt]
    options.update({'outtmpl': str(folder / 'source.%(ext)s'),
                    'format': selector, 'merge_output_format': 'mp4',
                    'max_filesize': MAX_BYTES, 'progress_hooks': [_progress_hook]})
    if target:
        # ``res`` sorts on the short side, so portrait posts are not mistaken
        # for 1080p when their long side is 1920.
        options['format_sort'] = [target]
    with YoutubeDL(options) as ydl:
        try:
            info = ydl.extract_info(_ytdl_url(url, platform), download=True)
        except DownloadError as exc:
            raise _ydl_error(exc) from None
        if info.get('_type') == 'playlist':
            info = next((entry for entry in info.get('entries') or [] if entry), info) or {}
        downloads = info.get('requested_downloads') or []
        candidate = downloads[0].get('filepath') if downloads else None
        path = Path(candidate) if candidate else Path(ydl.prepare_filename(info))
    if not path.is_file():
        merged = sorted(folder.glob('source.*'))
        if not merged:
            raise MediaError('The platform did not return a downloadable file.', 502)
        path = merged[0]
    if path.stat().st_size > MAX_BYTES:
        raise MediaError('This file is larger than the 100 MB limit.', 413)
    if fmt == 'mp3':
        output = folder / 'audio.mp3'
        _to_mp3(path, output)
        return output
    output = folder / 'video.mp4'
    _to_mp4(path, output)
    return output


def probe_video(url, platform):
    """Read post metadata without downloading. Raises MediaError on unusable posts."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    with YoutubeDL(_ytdl_opts()) as ydl:
        try:
            info = ydl.extract_info(_ytdl_url(url, platform), download=False)
        except DownloadError as exc:
            raise _ydl_error(exc) from None
        if info.get('_type') == 'playlist':
            entries = [entry for entry in info.get('entries') or [] if entry]
            info = next((entry for entry in entries if entry.get('formats')), entries[0] if entries else {})
    formats = info.get('formats') or []
    has_video = any((item.get('vcodec') or 'none') != 'none' for item in formats)
    if not has_video:
        raise MediaError('This post contains photos only. Use the Photo Downloader.', 422)
    duration = info.get('duration')
    if isinstance(duration, (int, float)) and duration > MAX_DURATION:
        raise MediaError('This video is longer than the 10-minute limit.', 413)
    caption = info.get('description') or info.get('title') or ''
    width, height = info.get('width'), info.get('height')
    def short_side(item):
        sides = [item.get('width'), item.get('height')]
        sides = [side for side in sides if isinstance(side, int) and side > 0]
        return min(sides) if sides else 0
    video_formats = [item for item in formats
                     if (item.get('vcodec') or 'none') != 'none' and short_side(item)]
    if video_formats:
        # Report the stream the standard download actually picks, not the largest one.
        capped = [item for item in video_formats if short_side(item) <= 720] or video_formats
        best = max(capped, key=lambda item: (short_side(item), item.get('tbr') or 0))
        width, height = best.get('width'), best.get('height')
    return {'title': info.get('title') or '', 'caption': caption,
            'duration_seconds': int(duration) if isinstance(duration, (int, float)) else None,
            'width': width, 'height': height,
            'thumbnail': info.get('thumbnail'),
            'formats': list(KINDS['video'])}


def _tiktok_id(url):
    match = re.search(r'/(?:video|photo)/(\d+)', url)
    return match.group(1) if match else None


def _tiktok_images(url, platform):
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    video_id = _tiktok_id(url)
    if not video_id:
        raise MediaError('Paste a TikTok post link that includes the post id.', 422)
    with YoutubeDL(_ytdl_opts()) as ydl:
        extractor = ydl.get_info_extractor('TikTok')
        try:
            data, _status = extractor._extract_web_data_and_status(_ytdl_url(url, platform),
                                                                   video_id)
        except DownloadError as exc:
            raise _ydl_error(exc) from None
    if not isinstance(data, dict):
        raise MediaError('TikTok did not return this post. It may be private or removed.', 502)
    post = data.get('imagePost') or {}
    images = []
    for item in post.get('images') or []:
        links = ((item.get('imageURL') or {}).get('urlList') or [])
        if links:
            images.append({'url': links[0], 'width': item.get('imageWidth'),
                           'height': item.get('imageHeight')})
    if not images:
        if data.get('video'):
            raise MediaError('This TikTok post is a video. Use the Video Downloader.', 422)
        raise MediaError('TikTok did not return any images for this post.', 422)
    return {'title': data.get('desc') or 'TikTok photo post',
            'caption': data.get('desc') or '', 'images': images}


def _instagram_media(page):
    from yt_dlp.extractor.instagram import InstagramIE

    found = None
    for raw in InstagramIE._SJS_RE.findall(page):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        stack = [data]
        while stack and not found:
            node = stack.pop()
            if isinstance(node, dict):
                if isinstance(node.get('xig_polaris_media'), dict):
                    found = node['xig_polaris_media']
                    break
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
        if found:
            break
    return found


def _instagram_images(url, platform):
    from yt_dlp import YoutubeDL

    shortcode = re.search(r'/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
    if not shortcode:
        raise MediaError('Paste an Instagram post link that includes the post code.', 422)
    with YoutubeDL(_ytdl_opts()) as ydl:
        extractor = ydl.get_info_extractor('Instagram')
        extractor._real_initialize()
        page, _response = extractor._download_webpage_handle(url, shortcode.group(1))
    media = _instagram_media(page)
    if not media:
        raise MediaError('Instagram did not return this post without a login.', 502)
    product = media.get('if_not_gated_logged_out') or {}
    items = product.get('carousel_media') or [product]
    images = []
    for item in items:
        candidates = (item.get('image_versions2') or {}).get('candidates') or []
        if not candidates:
            continue
        images.append({'url': candidates[0]['url'], 'width': item.get('original_width'),
                       'height': item.get('original_height')})
    if not images:
        if product.get('video_versions'):
            raise MediaError('This Instagram post is a video. Use the Video Downloader.', 422)
        raise MediaError('Instagram did not return any images for this post.', 422)
    caption = ((product.get('caption') or {}).get('text') or '')
    return {'title': caption.splitlines()[0][:120] if caption else 'Instagram photo post',
            'caption': caption, 'images': images}


def _pinterest_images(url, platform):
    page = _fetch_text(url, REFERERS['pinterest'])
    images = []
    original = re.search(r'"image":"(https://i\.pinimg\.com/originals/[^"]+)"', page)
    if original:
        images.append({'url': original.group(1).replace('\\/', '/'), 'width': None, 'height': None})
    else:
        link = _meta(page, 'og:image')
        if link:
            link = link.replace('\\/', '/')
            link = re.sub(r'/736x/', '/originals/', link)
            images.append({'url': link, 'width': None, 'height': None})
    if not images:
        raise MediaError('Pinterest did not return an image for this pin.', 422)
    title = _meta(page, 'og:title') or (re.search(r'<title[^>]*>(.*?)</title>', page, re.S) or [None, ''])[1]
    description = _meta(page, 'og:description')
    if not description:
        match = re.search(r'"description":"([^"]{0,300})"', page)
        description = match.group(1) if match else ''
    return {'title': _unescape(title).strip() if title else 'Pinterest pin',
            'caption': _unescape(description).strip() if description else '',
            'images': images}


def _meta(page, prop):
    """Read a meta tag in either attribute order; Pinterest emits both."""
    for pattern in (rf'<meta[^>]+property="{prop}"[^>]+content="([^"]*)"',
                    rf'<meta[^>]+content="([^"]*)"[^>]+property="{prop}"'):
        match = re.search(pattern, page)
        if match:
            return match.group(1)
    return None


def _unescape(value):
    return html.unescape(value)


def extract_images(url, platform):
    if platform == 'tiktok':
        return _tiktok_images(url, platform)
    if platform == 'instagram':
        return _instagram_images(url, platform)
    if platform == 'pinterest':
        return _pinterest_images(url, platform)
    raise MediaError('Image links must be from TikTok, Instagram, or Pinterest.', 422)


def _fetch_text(url, referer):
    try:
        with httpx.Client(timeout=30, follow_redirects=False, headers={
                'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9',
                'Referer': referer}) as client:
            response = client.get(url)
    except httpx.HTTPError:
        raise MediaError('The platform could not be reached right now.', 502) from None
    if response.status_code != 200 or len(response.content) > 8 * 1024 * 1024:
        raise MediaError('The platform did not return this post.', 502)
    return response.text


def _fetch_bytes(url, referer):
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        _public_url(current)
        try:
            with httpx.Client(timeout=45, follow_redirects=False, headers={
                    'User-Agent': UA, 'Accept': '*/*',
                    **({'Referer': referer} if referer else {})}) as client:
                response = client.get(current)
        except httpx.HTTPError:
            raise MediaError('The platform image could not be downloaded.', 502) from None
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get('location')
            if not location:
                raise MediaError('The platform image link was invalid.', 502)
            current = urljoin(current, location)
            continue
        if response.status_code != 200:
            raise MediaError('The platform image could not be downloaded.', 502)
        content_type = response.headers.get('content-type', '').split(';')[0].strip().lower()
        if not content_type.startswith('image/'):
            raise MediaError('The platform did not return an image.', 502)
        if len(response.content) > MAX_IMAGE_BYTES:
            raise MediaError('This image is larger than the 10 MB limit.', 413)
        return response.content, content_type
    raise MediaError('The platform image redirected too many times.', 502)


def _image_suffix(content_type, data):
    if content_type == 'image/png' or data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png', 'image/png'
    if content_type == 'image/webp' or data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp', 'image/webp'
    if content_type == 'image/jpeg' or data.startswith(b'\xff\xd8'):
        return 'jpg', 'image/jpeg'
    raise MediaError('The platform returned an unsupported image format.', 422)


class MediaStore:
    """Signed-token store plus a bounded download cache."""

    def __init__(self, directory, *, slots=2, clock=time.time):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.secret = secrets.token_bytes(32)
        self.slots = threading.BoundedSemaphore(slots)
        self.clock = clock
        self._locks = {}
        self._guard = threading.Lock()

    def _lock(self, key):
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def sweep(self):
        cutoff = self.clock() - CACHE_SECONDS
        for path in self.directory.iterdir():
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass

    def sign(self, payload):
        raw = json.dumps(payload, separators=(',', ':')).encode()
        body = base64.urlsafe_b64encode(raw).decode().rstrip('=')
        signature = hmac.new(self.secret, raw, hashlib.sha256).digest()[:16]
        return body + '.' + base64.urlsafe_b64encode(signature).decode().rstrip('=')

    def read(self, token):
        try:
            body, signature = token.split('.')
            raw = base64.urlsafe_b64decode(body + '=' * (-len(body) % 4))
            expected = hmac.new(self.secret, raw, hashlib.sha256).digest()[:16]
            given = base64.urlsafe_b64decode(signature + '=' * (-len(signature) % 4))
            if not hmac.compare_digest(given, expected):
                raise ValueError('signature')
            payload = json.loads(raw)
        except (ValueError, TypeError, UnicodeError):
            raise HTTPException(404, 'This media link is not valid.') from None
        if not isinstance(payload, dict) or not isinstance(payload.get('e'), int):
            raise HTTPException(404, 'This media link is not valid.')
        if payload['e'] < self.clock():
            raise HTTPException(410, 'This media link expired. Check the link again.')
        return payload

    def inspect(self, url, media_kind, platform):
        if media_kind == 'images':
            result = extract_images(url, platform)
            result['image_count'] = len(result['images'])
            first = result['images'][0]
            result['preview_source'] = first['url']
            result['width'] = first.get('width')
            result['height'] = first.get('height')
            result['formats'] = list(KINDS['images'])
            result['duration_seconds'] = None
            return result
        result = probe_video(url, platform)
        result['images'] = []
        result['image_count'] = 0
        result['preview_source'] = url
        if media_kind == 'audio':
            result['formats'] = list(KINDS['audio'])
        return result

    def _cache_path(self, url, media_kind):
        key = hashlib.sha256(f'{url}\0{media_kind}'.encode()).hexdigest()
        return self.directory / (key + ('.mp3' if media_kind == 'audio' else '.mp4'))

    def preview_file(self, url, media_kind, platform):
        target = self._cache_path(url, media_kind)
        if target.is_file() and target.stat().st_size:
            return target, ('audio/mpeg' if media_kind == 'audio' else 'video/mp4')
        with self._lock(target.name):
            if target.is_file() and target.stat().st_size:
                return target, ('audio/mpeg' if media_kind == 'audio' else 'video/mp4')
            with self.slots, tempfile.TemporaryDirectory(dir=self.directory) as work:
                fmt = 'mp3' if media_kind == 'audio' else 'video'
                source = _download_media(url, platform, fmt, Path(work))
                shutil.move(str(source), target)
        return target, ('audio/mpeg' if media_kind == 'audio' else 'video/mp4')

    def download(self, url, media_kind, fmt, platform):
        if media_kind == 'images':
            return self._download_images(url, platform)
        if fmt in ('video', 'mp3'):
            # Reuse the preview file instead of transferring the same bytes twice.
            preview_kind = 'audio' if fmt == 'mp3' else 'video'
            path, mime = self.preview_file(url, preview_kind, platform)
            label = 'audio' if fmt == 'mp3' else 'video'
            return path, mime, f'clipora-{platform}-{label}{path.suffix}'
        with self.slots, tempfile.TemporaryDirectory(dir=self.directory) as work:
            source = _download_media(url, platform, fmt, Path(work))
            target = self.directory / (hashlib.sha256(
                f'{url}\0{fmt}'.encode()).hexdigest() + source.suffix)
            shutil.move(str(source), target)
        return target, 'video/mp4', f'clipora-{platform}-{fmt}.mp4'

    def _download_images(self, url, platform):
        result = extract_images(url, platform)
        images = result['images'][:MAX_IMAGES]
        referer = REFERERS.get(platform, '')
        fetched, total = [], 0
        for item in images:
            data, content_type = _fetch_bytes(item['url'], referer)
            total += len(data)
            if total > MAX_IMAGE_TOTAL:
                raise MediaError('This carousel is larger than the 50 MB limit.', 413)
            suffix, mime = _image_suffix(content_type, data)
            fetched.append((data, suffix, mime))
        if not fetched:
            raise MediaError('The platform did not return any images.', 422)
        if len(fetched) == 1:
            data, suffix, mime = fetched[0]
            target = self.directory / (hashlib.sha256(
                (url + '\0image').encode()).hexdigest() + '.' + suffix)
            target.write_bytes(data)
            return target, mime, f'clipora-{platform}.{suffix}'
        target = self.directory / (hashlib.sha256(
            (url + '\0images').encode()).hexdigest() + '.zip')
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_STORED) as archive:
            for index, (data, suffix, _mime) in enumerate(fetched, 1):
                archive.writestr(f'clipora-{index:02d}.{suffix}', data)
        return target, 'application/zip', f'clipora-{platform}-images.zip'

    def file(self, name):
        if not isinstance(name, str) or not re.fullmatch(r'[a-f0-9]{64}\.(?:mp4|mp3|jpg|png|webp|zip)', name):
            raise HTTPException(404, 'This media link is not valid.')
        path = self.directory / name
        if not path.is_file():
            raise HTTPException(404, 'This file is no longer available. Check the link again.')
        return path


async def _read_json(request, fields):
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise HTTPException(415, 'Send application/json.')
    try:
        data = await request.json()
        if not isinstance(data, dict) or set(data) != set(fields):
            raise ValueError('Send ' + ', '.join(sorted(fields)) + '.')
    except (ValueError, TypeError, UnicodeError) as exc:
        raise HTTPException(422, str(exc)) from None
    return data


def register(app, directory):
    """Attach real routes. Callers must have checked loopback and the flag."""
    store = MediaStore(directory)

    @app.post('/api/v8/real/preview')
    async def preview(request: Request):
        data = await _read_json(request, ('url', 'media_kind'))
        try:
            media_kind = data['media_kind']
            if media_kind not in KINDS:
                raise MediaError('Choose a supported media kind.')
            kind = 'video' if media_kind == 'audio' else media_kind
            result = recognize_media(data['url'], kind)
            info = await asyncio.to_thread(store.inspect, result.url, media_kind, result.platform)
        except MediaError as exc:
            raise HTTPException(exc.status, str(exc)) from None
        except (ValueError, TypeError, UnicodeError) as exc:
            raise HTTPException(422, str(exc)) from None
        except Exception:
            raise HTTPException(502, 'The platform could not be read right now.') from None
        store.sweep()
        expires = int(store.clock()) + TTL
        if media_kind == 'images':
            preview_url = '/api/v8/real/media/' + store.sign({
                't': 'image', 'u': info['preview_source'], 'r': REFERERS.get(result.platform, ''),
                'e': expires})
        else:
            preview_url = '/api/v8/real/media/' + store.sign({
                't': 'file', 'u': result.url, 'k': media_kind, 'p': result.platform,
                'e': expires})
        poster_url = None
        if media_kind != 'images' and info.get('thumbnail'):
            poster_url = '/api/v8/real/media/' + store.sign({
                't': 'image', 'u': info['thumbnail'], 'r': REFERERS.get(result.platform, ''),
                'e': expires})
        return {'real': True, 'platform': result.platform, 'media_kind': media_kind,
                'title': info.get('title') or '', 'caption': info.get('caption') or '',
                'duration_seconds': info.get('duration_seconds'),
                'width': info.get('width'), 'height': info.get('height'),
                'image_count': info.get('image_count', 0),
                'formats': info.get('formats', []),
                'preview_url': preview_url, 'poster_url': poster_url,
                'expires_in': TTL, 'network_access_performed': True}

    @app.post('/api/v8/real/download')
    async def download(request: Request):
        data = await _read_json(request, ('url', 'media_kind', 'format'))
        try:
            media_kind, fmt = data['media_kind'], data['format']
            if media_kind not in KINDS or fmt not in KINDS[media_kind]:
                raise MediaError('Choose a supported download type.')
            kind = 'video' if media_kind == 'audio' else media_kind
            result = recognize_media(data['url'], kind)
            path, mime, filename = await asyncio.to_thread(
                store.download, result.url, media_kind, fmt, result.platform)
        except MediaError as exc:
            raise HTTPException(exc.status, str(exc)) from None
        except (ValueError, TypeError, UnicodeError) as exc:
            raise HTTPException(422, str(exc)) from None
        except Exception:
            raise HTTPException(502, 'The media could not be prepared right now.') from None
        token = store.sign({'t': 'download', 'n': path.name, 'm': mime, 'f': filename,
                            'e': int(store.clock()) + TTL})
        return {'real': True, 'format': fmt, 'platform': result.platform,
                'filename': filename, 'url': '/api/v8/real/file/' + token,
                'expires_in': TTL, 'network_access_performed': True}

    @app.get('/api/v8/real/media/{token}')
    async def media(token: str, request: Request):
        payload = store.read(token)
        if payload.get('t') == 'file':
            try:
                path, mime = await asyncio.to_thread(
                    store.preview_file, payload['u'], payload['k'], payload['p'])
            except MediaError as exc:
                raise HTTPException(exc.status, str(exc)) from None
            except Exception:
                raise HTTPException(502, 'The preview could not be prepared right now.') from None
            return FileResponse(path, media_type=mime, content_disposition_type='inline',
                                filename='clipora-preview' + path.suffix)
        if payload.get('t') != 'image' or not isinstance(payload.get('u'), str):
            raise HTTPException(404, 'This media link is not valid.')
        return await _proxy(payload['u'], payload.get('r'), request)

    @app.get('/api/v8/real/file/{token}')
    def file(token: str):
        payload = store.read(token)
        if payload.get('t') != 'download':
            raise HTTPException(404, 'This media link is not valid.')
        path = store.file(payload.get('n'))
        return FileResponse(path, media_type=payload.get('m') or 'application/octet-stream',
                            filename=payload.get('f') or path.name)


async def _proxy(url, referer, request):
    """Stream one platform image with the signed URL and a public-host check."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        _public_url(current)
        headers = {'User-Agent': UA, 'Accept': '*/*'}
        if referer:
            headers['Referer'] = referer
        if request.headers.get('range'):
            headers['Range'] = request.headers['range']
        client = httpx.AsyncClient(timeout=httpx.Timeout(30, read=60), follow_redirects=False)
        try:
            response = await client.send(client.build_request('GET', current, headers=headers),
                                         stream=True)
        except httpx.HTTPError:
            await client.aclose()
            raise HTTPException(502, 'The platform image could not be loaded.') from None
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get('location')
            await response.aclose()
            await client.aclose()
            if not location:
                raise HTTPException(502, 'The platform image link was invalid.')
            current = urljoin(current, location)
            continue
        if response.status_code not in (200, 206):
            await response.aclose()
            await client.aclose()
            raise HTTPException(502, 'The platform image could not be loaded.')
        content_type = response.headers.get('content-type', '').split(';')[0].strip().lower()
        if not content_type.startswith(MEDIA_TYPES):
            await response.aclose()
            await client.aclose()
            raise HTTPException(502, 'The platform returned an unsupported file.')
        length = response.headers.get('content-length')
        if length and length.isdigit() and int(length) > MAX_BYTES:
            await response.aclose()
            await client.aclose()
            raise HTTPException(413, 'This file is larger than the 100 MB limit.')
        passed = {name: response.headers[name] for name in
                  ('content-type', 'content-length', 'content-range', 'accept-ranges')
                  if name in response.headers}

        async def chunks():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return StreamingResponse(chunks(), status_code=response.status_code,
                                 headers={**passed, 'Cache-Control': 'no-store'})
    raise HTTPException(502, 'The platform image redirected too many times.')
