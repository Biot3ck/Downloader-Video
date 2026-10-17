"""Offline staging HTTPS CONNECT Egress. NEVER deploy publicly.

Starts only on localhost with explicit TEST enable. All external dial attempts
are disallowed unless unit tests inject a transport; this is not a public Egress.
"""
import asyncio
import os
from contextlib import suppress
from connect_policy import validate_connect_target
from http_parser import read_connect_request
from dns_executor import resolve_destination, DNSTimeoutError
from ip_policy import validate_destination_ip

MAX_TUNNEL_BYTES = 64 * 1024 * 1024
IDLE_TIMEOUT = 15
SESSION_TIMEOUT = 90
DIAL_TIMEOUT = 4
CAPACITY = asyncio.Semaphore(16)

async def send_status(writer, code):
    writer.write(b'HTTP/1.1 ' + code + b'\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
    await writer.drain()

async def transfer(reader, writer, budget):
    # Report resource-limit/transport failures to the session owner so the
    # opposite direction cannot remain alive after this pump has stopped.
    while True:
        data = await asyncio.wait_for(reader.read(32768), IDLE_TIMEOUT)
        if not data:
            with suppress(Exception):
                writer.write_eof()
                await asyncio.wait_for(writer.drain(), IDLE_TIMEOUT)
            break
        async with budget['lock']:
            budget['bytes'] += len(data)
            if budget['bytes'] > MAX_TUNNEL_BYTES:
                raise ValueError('Transfer budget exceeded')
        writer.write(data)
        await asyncio.wait_for(writer.drain(), IDLE_TIMEOUT)


async def relay_session(reader, writer, upstream_reader, upstream):
    budget = {'bytes': 0, 'lock': asyncio.Lock()}
    tasks = [
        asyncio.create_task(transfer(reader, upstream, budget)),
        asyncio.create_task(transfer(upstream_reader, writer, budget)),
    ]
    try:
        # Ordinary EOF preserves half-close semantics. A pump error is raised
        # immediately; a session deadline or caller cancellation follows the
        # same cleanup path. gather alone would leave its siblings running.
        await asyncio.wait_for(asyncio.gather(*tasks), SESSION_TIMEOUT)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def handle(reader, writer, resolver=resolve_destination, dial=None):
    upstream = None
    established = False
    status = b'400 Bad Request'
    # dial dependency injection permitted only by test harness, never by CLI.
    if dial is None:
        dial = asyncio.open_connection
    try:
        async with CAPACITY:
            target = await read_connect_request(reader)
            hostname, port = validate_connect_target(target)
            # Deny the default transport before any public DNS lookup.
            if dial is asyncio.open_connection:
                status = b'403 Forbidden'
                return
            destination = await resolver(target)
            if destination['host'] != hostname or destination['port'] != port:
                raise ValueError('Resolver target mismatch')
            addresses = destination['addresses']
            if not isinstance(addresses, list) or not addresses:
                raise ValueError('Missing addresses')
            # Validate each address again, and dial only a validated numeric IP.
            pinned = [validate_destination_ip(a) for a in addresses]
            upstream_reader, upstream = await asyncio.wait_for(dial(pinned[0], port), DIAL_TIMEOUT)
            writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            await writer.drain()
            established = True
            await relay_session(reader, writer, upstream_reader, upstream)
    except (ValueError, KeyError, TypeError, UnicodeError, asyncio.TimeoutError,
            asyncio.IncompleteReadError, asyncio.LimitOverrunError, DNSTimeoutError):
        pass
    except OSError:
        status = b'502 Bad Gateway'
    finally:
        if not established:
            with suppress(OSError, ConnectionError):
                await send_status(writer, status)
        if upstream:
            upstream.close()
            with suppress(OSError, ConnectionError):
                await upstream.wait_closed()
        writer.close()
        with suppress(OSError, ConnectionError):
            await writer.wait_closed()

async def main():
    if os.environ.get('CLIPORA_V8_STAGE_LOOPBACK_ONLY') != '1':
        raise SystemExit('Refusing startup: set CLIPORA_V8_STAGE_LOOPBACK_ONLY=1')
    server = await asyncio.start_server(handle, '127.0.0.1', 18888, limit=8192)
    print('CLIPORA V8 SECURE EGRESS STAGE (LOOPBACK DENY-ALL)', flush=True)
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    asyncio.run(main())
