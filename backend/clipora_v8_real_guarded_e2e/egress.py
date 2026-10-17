import asyncio,ssl
from pathlib import Path
ROOT=Path(__file__).resolve().parent

async def relay(r,w):
    try:
        while True:
            data=await asyncio.wait_for(r.read(32768),10)
            if not data:break
            w.write(data);await asyncio.wait_for(w.drain(),10)
    except (OSError,ConnectionError,asyncio.TimeoutError):pass
    finally:w.close()

async def fixture(r,w):
    try:
        request=await asyncio.wait_for(r.readuntil(b'\r\n\r\n'),5)
        path=request.split(b' ',2)[1]
        if path != b'/video.mp4':
            w.write(b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
        else:
            data=(ROOT/'fixtures/video.mp4').read_bytes()
            w.write(b'HTTP/1.1 200 OK\r\nContent-Type: video/mp4\r\nContent-Length: '+str(len(data)).encode()+b'\r\nConnection: close\r\n\r\n'+data)
        await w.drain()
    except (OSError,asyncio.TimeoutError,asyncio.IncompleteReadError,IndexError):pass
    finally:w.close()

async def handle(r,w):
    upstream=None
    try:
        req=await asyncio.wait_for(r.readuntil(b'\r\n\r\n'),4)
        if req != b'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n':raise ValueError('not allowed')
        a,b=await asyncio.wait_for(asyncio.open_connection('127.0.0.1',9443),4)
        upstream=b
        w.write(b'HTTP/1.1 200 Connection Established\r\n\r\n');await w.drain()
        await asyncio.gather(relay(r,b),relay(a,w))
    except (OSError,ValueError,asyncio.TimeoutError,asyncio.IncompleteReadError):
        try:w.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n');await w.drain()
        except OSError:pass
    finally:
        if upstream:upstream.close()
        w.close()

async def main():
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(ROOT/'fixtures/test.crt'),str(ROOT/'fixtures/test.key'))
    tls=await asyncio.start_server(fixture,'127.0.0.1',9443,ssl=ctx)
    tunnel=await asyncio.start_server(handle,'0.0.0.0',8888)
    print('CLIPORA E2E EGRESS READY',flush=True)
    async with tls,tunnel:await asyncio.gather(tls.serve_forever(),tunnel.serve_forever())
if __name__=='__main__':asyncio.run(main())
