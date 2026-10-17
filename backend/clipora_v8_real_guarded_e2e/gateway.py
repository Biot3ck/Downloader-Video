import asyncio, os

async def relay(r, w):
    try:
        while True:
            data = await asyncio.wait_for(r.read(32768), 10)
            if not data: break
            w.write(data)
            await asyncio.wait_for(w.drain(), 10)
    except (OSError, asyncio.TimeoutError, ConnectionError):
        pass
    finally:
        w.close()

async def handle(r, w):
    upstream = None
    try:
        req = await asyncio.wait_for(r.readuntil(b'\r\n\r\n'), 4)
        lines = req[:-4].split(b'\r\n')
        if len(req)>4096 or not lines or lines[0] not in (b'CONNECT example.com:443 HTTP/1.1', b'CONNECT example.com:443 HTTP/1.0'):
            raise ValueError('target blocked')
        hosts=[line[5:].strip().lower() for line in lines[1:] if line.lower().startswith(b'host:')]
        if hosts and hosts != [b'example.com:443']: raise ValueError('host rejected')
        a,b=await asyncio.wait_for(asyncio.open_connection(os.environ['EGRESS_IP'],8888),4)
        upstream=b
        b.write(b'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n')
        await b.drain()
        reply=await asyncio.wait_for(a.readuntil(b'\r\n\r\n'),4)
        if reply != b'HTTP/1.1 200 Connection Established\r\n\r\n': raise ValueError('upstream not approved')
        w.write(reply);await w.drain()
        await asyncio.gather(relay(r,b),relay(a,w))
    except (OSError,ValueError,asyncio.TimeoutError,asyncio.IncompleteReadError,asyncio.LimitOverrunError):
        try: w.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n');await w.drain()
        except (OSError,ConnectionError): pass
    finally:
        if upstream:upstream.close()
        w.close()

async def main():
    s=await asyncio.start_server(handle,'0.0.0.0',8888,limit=8192)
    print('CLIPORA E2E GATEWAY READY',flush=True)
    async with s:await s.serve_forever()
if __name__=='__main__':asyncio.run(main())
