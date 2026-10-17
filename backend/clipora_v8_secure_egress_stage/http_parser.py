import asyncio
import re

MAX_HEADER_BYTES = 8192
HEADER_TIMEOUT = 5

HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")


async def read_connect_request(reader):
    try:
        data = await asyncio.wait_for(
            reader.readuntil(b"\r\n\r\n"),
            timeout=HEADER_TIMEOUT,
        )
    except (
        asyncio.LimitOverrunError,
        asyncio.IncompleteReadError,
        asyncio.TimeoutError,
    ) as exc:
        raise ValueError("Invalid or incomplete headers") from exc

    if len(data) > MAX_HEADER_BYTES:
        raise ValueError("Headers too large")


    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Invalid encoding") from exc

    lines = text[:-4].split("\r\n")
    parts = lines[0].split(" ")

    if len(parts) != 3:
        raise ValueError("Invalid request line")

    method, target, version = parts

    if method != "CONNECT" or version != "HTTP/1.1":
        raise ValueError("Unsupported request")

    headers = {}

    for line in lines[1:]:
        if ":" not in line:
            raise ValueError("Malformed header")

        name, value = line.split(":", 1)

        if not HEADER_NAME.fullmatch(name):
            raise ValueError("Invalid header name")

        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Invalid header value")

        key = name.lower()

        if key in headers:
            raise ValueError("Duplicate header")

        headers[key] = value.strip()

    if headers.get("host") != target:
        raise ValueError("Missing or mismatched Host")

    if "content-length" in headers or "transfer-encoding" in headers:
        raise ValueError("Request body not allowed")

    return target
