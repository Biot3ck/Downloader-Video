from urllib.parse import urlsplit
from fastapi import HTTPException
import ipaddress

ALLOWED_HOSTS = {
    "tiktok.com": "TikTok",
    "www.tiktok.com": "TikTok",
    "m.tiktok.com": "TikTok",
    "vm.tiktok.com": "TikTok",
    "vt.tiktok.com": "TikTok",
    "instagram.com": "Instagram",
    "www.instagram.com": "Instagram",
    "pinterest.com": "Pinterest",
    "www.pinterest.com": "Pinterest",
    "pin.it": "Pinterest",
    "www.pin.it": "Pinterest",
}

def validate_video_url(url):
    if not isinstance(url, str):
        raise HTTPException(400, "Invalid URL")

    url = url.strip()

    if not url or len(url) > 2048:
        raise HTTPException(400, "Invalid URL length")

    if any(ord(c) < 32 or ord(c) == 127 for c in url):
        raise HTTPException(400, "Invalid URL characters")

    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise HTTPException(400, "Malformed URL")

    if parsed.scheme != "https":
        raise HTTPException(400, "HTTPS required")

    if not hostname:
        raise HTTPException(400, "Hostname required")

    if parsed.username is not None or parsed.password is not None:
        raise HTTPException(400, "Credentials not allowed")

    if port is not None:
        raise HTTPException(400, "Custom ports not allowed")

    if "\\" in url:
        raise HTTPException(400, "Backslashes not allowed")

    hostname = hostname.lower().rstrip(".")

    try:
        ipaddress.ip_address(hostname)
        raise HTTPException(400, "IP addresses not allowed")
    except ValueError:
        pass

    platform = ALLOWED_HOSTS.get(hostname)

    if not platform:
        raise HTTPException(
            400,
            "Only TikTok, Instagram and Pinterest are supported"
        )

    return platform
