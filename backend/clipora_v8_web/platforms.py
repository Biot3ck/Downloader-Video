"""Input URL recognition only. Never resolves DNS, follows redirects, or dials."""
from dataclasses import dataclass
import re
from urllib.parse import urlsplit, urlunsplit

HOSTS = {
    'youtube.com': 'youtube', 'www.youtube.com': 'youtube', 'm.youtube.com': 'youtube', 'youtu.be': 'youtube',
    'tiktok.com': 'tiktok', 'www.tiktok.com': 'tiktok', 'vm.tiktok.com': 'tiktok', 'vt.tiktok.com': 'tiktok',
    'instagram.com': 'instagram', 'www.instagram.com': 'instagram',
    'pinterest.com': 'pinterest', 'www.pinterest.com': 'pinterest', 'pin.it': 'pinterest',
}


@dataclass(frozen=True)
class VideoURL:
    platform: str
    url: str


def recognize(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise ValueError('Use a post link up to 2048 characters.')
    if any(ord(c) <= 32 or ord(c) == 127 for c in value) or '\\' in value:
        raise ValueError('The link contains invalid characters.')
    parsed = urlsplit(value)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or parsed.username is not None or parsed.password is not None:
        raise ValueError('Use an HTTPS post link without login details.')
    # Exact authority match prevents encoded hostnames, trailing dots and ports.
    if parsed.netloc.lower() != host or host not in HOSTS:
        raise ValueError('Use a YouTube, TikTok, Instagram, or Pinterest post link.')
    if not parsed.path or parsed.path == '/':
        raise ValueError('Paste a link to a post, not the platform home page.')
    # Input matching is deliberately narrower than extractor/CDN permissions.
    if re.search(r'%(?:0[0-9a-f]|1[0-9a-f]|7f|5c)', value, re.I):
        raise ValueError('The link contains encoded control characters.')
    return VideoURL(HOSTS[host], urlunsplit(('https', host, parsed.path, parsed.query, '')))


MEDIA_PLATFORMS = {
    'video': ('youtube', 'tiktok', 'instagram', 'pinterest'),
    'images': ('tiktok', 'instagram', 'pinterest'),
}


def recognize_media(value, media_kind='video'):
    """Recognize requested media without claiming the remote post contains it."""
    if not isinstance(media_kind, str) or media_kind not in MEDIA_PLATFORMS:
        raise ValueError('Choose video or images.')
    result = recognize(value)
    if result.platform not in MEDIA_PLATFORMS[media_kind]:
        raise ValueError('Image links must be from TikTok, Instagram, or Pinterest.')
    return result
