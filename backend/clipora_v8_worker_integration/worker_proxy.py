"""V8-only fail-closed yt-dlp configuration. Not a downloader or public-network authorization."""
import os
from urllib.parse import urlsplit


def required_proxy_settings(base_options, environ=None):
    env = os.environ if environ is None else environ
    raw = env.get('CLIPORA_V8_PROXY_URL', '')
    if not raw:
        raise RuntimeError('V8 proxy URL required; direct yt-dlp connections forbidden')
    try:
        parsed = urlsplit(raw)
        if parsed.scheme != 'http' or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            raise ValueError('unsupported proxy URL')
        if not parsed.hostname or parsed.port != 8888:
            raise ValueError('proxy must specify host and port 8888')
    except ValueError as exc:
        raise RuntimeError('Invalid V8 proxy URL') from exc
    opts = dict(base_options)
    opts['proxy'] = raw
    opts['noplaylist'] = True
    return opts


def inspect_then_download(url, download_dir, ydl_options, youtube_dl_class, environ=None):
    """Use a proxy for both yt-dlp passes; caller remains responsible for URL/duration/size protections."""
    options = required_proxy_settings(ydl_options(), environ)
    with youtube_dl_class(options) as ydl:
        metadata = ydl.extract_info(url, download=False)
    options = required_proxy_settings(ydl_options(download_dir), environ)
    with youtube_dl_class(options) as ydl:
        result = ydl.extract_info(url, download=True)
    return metadata, result
