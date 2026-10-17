"""Offline Docker E2E adapter. NOT a production Egress; never deploy.

Uses the unmodified secure stage's handle() with explicit test-only resolver
and dial, mapping validated synthetic IP 8.8.8.8 to a local TLS fixture.
"""
import asyncio
import importlib.util
import os
import ssl
import sys
from pathlib import Path

STAGE = Path('/stage')
FIXTURE = Path('/fixture/fixtures')
if os.environ.get('CLIPORA_E2E_OFFLINE_ONLY') != '1':
    raise SystemExit('Offline fixture disabled by default')
if not (STAGE / 'server_stage.py').is_file():
    raise SystemExit('Missing stage server')
sys.path.insert(0, str(STAGE))
spec = importlib.util.spec_from_file_location('server_stage', STAGE / 'server_stage.py')
secure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(secure)

async def local_tls(reader, writer):
    try:
        request = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 5)
        first = request.split(b'\r\n', 1)[0]
        if first.split(b' ')[:2] != [b'GET', b'/video.mp4']:
            writer.write(b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
        else:
            data = (FIXTURE / 'video.mp4').read_bytes()
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: video/mp4\r\nContent-Length: ' + str(len(data)).encode() + b'\r\nConnection: close\r\n\r\n' + data)
        await writer.drain()
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, IndexError):
        pass
    finally:
        writer.close()

async def resolve(target):
    if target != 'example.com:443':
        raise ValueError('Offline fixture only allows example.com:443')
    return {'host': 'example.com', 'port': 443, 'addresses': ['8.8.8.8']}

async def dial(pinned_ip, port):
    if (pinned_ip, port) != ('8.8.8.8', 443):
        raise ValueError('Unexpected pinned target')
    return await asyncio.open_connection('127.0.0.1', 9443)

async def handle(reader, writer):
    await secure.handle(reader, writer, resolver=resolve, dial=dial)

async def main():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(FIXTURE / 'test.crt'), str(FIXTURE / 'test.key'))
    tls = await asyncio.start_server(local_tls, '127.0.0.1', 9443, ssl=ctx)
    proxy = await asyncio.start_server(handle, '0.0.0.0', 8888, limit=8192)
    print('CLIPORA SECURE E2E EGRESS READY (OFFLINE ONLY)', flush=True)
    async with tls, proxy:
        await asyncio.gather(tls.serve_forever(), proxy.serve_forever())

if __name__ == '__main__':
    asyncio.run(main())
