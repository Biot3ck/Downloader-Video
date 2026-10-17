import asyncio
import unittest
import tempfile
from unittest.mock import patch
from fastapi.testclient import TestClient
from clipora_v8_web.main import Boundary, create_app, validate_origin
from clipora_v8_web.platforms import recognize

ORIGIN='http://127.0.0.1:8090'


class WebTests(unittest.TestCase):
    def setUp(self):
        self.state=tempfile.TemporaryDirectory(prefix='clipora-web-test-')
        self.addCleanup(self.state.cleanup)
        self.client=TestClient(create_app(ORIGIN,self.state.name),base_url=ORIGIN)
    def test_only_product_surface(self):
        for path in ('/', '/app', '/assets/app.js', '/assets/style.css'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn("frame-ancestors 'none'",response.headers['content-security-policy'])
            self.assertNotIn('unsafe-inline',response.headers['content-security-policy'])
        for path in ('/dev','/docs','/openapi.json','/api/v8/real-offline/jobs','/api/v8/demo/jobs','/api/v8/local-mp4/jobs'):
            self.assertEqual(self.client.get(path).status_code,404,path)
            self.assertEqual(self.client.post(path,headers={'Origin':ORIGIN}).status_code,404,path)
        self.assertNotIn('/dev',self.client.get('/').text)
    def test_download_cannot_be_enabled_by_legacy_flags(self):
        with patch.dict('os.environ',{'CLIPORA_V8_OFFLINE_BROWSER_TEST':'1','CLIPORA_PUBLIC_DOWNLOADS_ENABLED':'1'}):
            self.assertEqual(self.client.post('/api/v8/download',headers={'Origin':ORIGIN}).status_code,503)
            self.assertFalse(self.client.get('/healthz').json()['ready_for_public_launch'])
    def test_exact_host_and_origin(self):
        self.assertEqual(self.client.get('/',headers={'Host':'evil.example'}).status_code,400)
        for origin in ('https://evil.example','null',ORIGIN+'.evil'):
            response=self.client.post('/api/v8/validate',headers={'Origin':origin},json={'url':'https://youtu.be/test'})
            self.assertEqual(response.status_code,403)
            self.assertIn('content-security-policy',response.headers)
        self.assertEqual(self.client.post('/api/v8/validate',json={}).status_code,403)
        self.assertEqual(self.client.options('/').status_code,405)
    def test_size_encoding_and_json(self):
        for body,extra,code in [(b'x'*4097,{},413),(b'{}',{'Content-Encoding':'gzip'},415),
                                 (b'no-json',{'Content-Type':'application/json'},422),(b'{}',{},415)]:
            self.assertEqual(self.client.post('/api/v8/validate',content=body,headers={'Origin':ORIGIN,**extra}).status_code,code)
    def test_four_platforms_without_outbound_network(self):
        cases={'https://youtu.be/abc':'youtube','https://www.tiktok.com/@name/video/123':'tiktok',
               'https://www.instagram.com/reel/abc/':'instagram','https://pin.it/abc':'pinterest'}
        with patch('socket.getaddrinfo',side_effect=AssertionError('DNS forbidden')),patch('socket.create_connection',side_effect=AssertionError('Network forbidden')):
            for url,platform in cases.items():
                response=self.client.post('/api/v8/validate',json={'url':url},headers={'Origin':ORIGIN})
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['platform'],platform)
                self.assertFalse(response.json()['network_access_performed'])
    def test_deceptive_urls_rejected(self):
        urls=['http://youtu.be/abc','https://youtube.com.evil.test/watch?v=a',
              'https://youtube.com@evil.test/watch','https://evil@youtube.com/watch',
              'https://127.0.0.1/a','https://[::1]/a','https://youtube.com:443/a',
              'https://youtube.com./a','https://youtube.com\\@evil.test/a',
              'https://youtube.com/%0d%0a','https://youtube.com/\na', 'https://youtube.com/']
        for url in urls:
            with self.subTest(url=url),self.assertRaises(ValueError):recognize(url)
    def test_origin_configuration(self):
        for origin in ('http://example.com','https://example.com/','https://*.example.com',
                       'https://user@example.com','https://example.com?x=1'):
            with self.assertRaises(ValueError):validate_origin(origin)


class StreamBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_chunked_body_limit_and_duplicate_host(self):
        called=False
        async def downstream(scope,receive,send):
            nonlocal called
            called=True
        boundary=Boundary(downstream,ORIGIN)
        scope={'type':'http','method':'POST','headers':[(b'host',b'127.0.0.1:8090'),(b'origin',ORIGIN.encode())]}
        messages=iter([{'type':'http.request','body':b'x'*3000,'more_body':True},
                       {'type':'http.request','body':b'x'*2000,'more_body':False}])
        sent=[]
        async def receive():return next(messages)
        async def send(message):sent.append(message)
        await boundary(scope,receive,send)
        self.assertFalse(called)
        self.assertEqual(sent[0]['status'],413)
        sent.clear();scope['headers'].append((b'host',b'127.0.0.1:8090'))
        await boundary(scope,receive,send)
        self.assertEqual(sent[0]['status'],400)


if __name__=='__main__':unittest.main()
