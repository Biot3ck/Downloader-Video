"""Bundled sample downloads stay local, signed, and separate from the public gate."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from clipora_v8_web.main import create_app

ORIGIN = 'http://127.0.0.1:8090'
TIKTOK = 'https://www.tiktok.com/@user/video/123'
PIN = 'https://pin.it/abc'


class DemoDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def client(self, origin=ORIGIN, demo=True):
        return TestClient(create_app(origin, Path(self.temp.name).resolve(),
                                     demo_downloads_enabled=demo), base_url=origin)

    def issue(self, client, fmt='video', kind='video', url=TIKTOK, origin=ORIGIN):
        return client.post('/api/v8/demo/download', headers={'Origin': origin},
                           json={'url': url, 'media_kind': kind, 'format': fmt})

    def test_routes_are_absent_unless_explicitly_enabled(self):
        client = self.client(demo=False)
        self.assertEqual(self.issue(client).status_code, 404)
        self.assertEqual(client.get('/api/v8/demo/file/anything').status_code, 404)

    def test_routes_stay_absent_on_non_loopback_https_even_with_the_flag(self):
        client = self.client(origin='https://clipora.example')
        self.assertEqual(self.issue(client, origin='https://clipora.example').status_code, 404)
        self.assertEqual(client.get('/api/v8/demo/file/anything').status_code, 404)

    def test_issued_link_serves_the_bundled_sample(self):
        client = self.client()
        response = self.issue(client)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['sample'])
        self.assertFalse(data['network_access_performed'])
        self.assertEqual(data['platform'], 'tiktok')
        self.assertEqual(data['filename'], 'clipora-sample-tiktok-video.mp4')
        self.assertTrue(data['url'].startswith('/api/v8/demo/file/'))
        self.assertLessEqual(data['expires_in'], 300)
        served = client.get(data['url'])
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.headers['content-type'], 'video/mp4')
        self.assertIn('attachment', served.headers['content-disposition'])
        self.assertIn('clipora-sample-tiktok-video.mp4', served.headers['content-disposition'])
        self.assertGreater(len(served.content), 1024)

    def test_each_format_maps_to_one_fixed_file(self):
        client = self.client()
        for fmt, kind, url, media in (('video', 'video', TIKTOK, 'video/mp4'),
                                      ('hd', 'video', TIKTOK, 'video/mp4'),
                                      ('mp3', 'video', TIKTOK, 'audio/mpeg'),
                                      ('image', 'images', PIN, 'image/jpeg')):
            data = self.issue(client, fmt, kind, url).json()
            served = client.get(data['url'])
            self.assertEqual(served.status_code, 200, fmt)
            self.assertEqual(served.headers['content-type'], media, fmt)
            self.assertIn(data['filename'], served.headers['content-disposition'], fmt)

    def test_mismatched_or_unknown_formats_are_rejected(self):
        client = self.client()
        for fmt, kind in (('video', 'images'), ('image', 'video'), ('exe', 'video'), ('', 'video')):
            self.assertEqual(self.issue(client, fmt, kind).status_code, 422, (fmt, kind))

    def test_public_download_gate_stays_closed(self):
        client = self.client()
        self.assertEqual(client.post('/api/v8/download', headers={'Origin': ORIGIN},
                                     json={'url': TIKTOK, 'format': 'hd'}).status_code, 503)
        health = client.get('/healthz').json()
        self.assertFalse(health['public_downloads_enabled'])
        self.assertFalse(health['ready_for_public_launch'])

    def test_tampered_expired_and_traversal_tokens_are_refused(self):
        client = self.client()
        token = self.issue(client).json()['url'].rsplit('/', 1)[1]
        body, signature = token.split('.')
        def flip(text):
            index = len(text) // 2
            replacement = 'A' if text[index] != 'A' else 'B'
            return text[:index] + replacement + text[index + 1:]
        for bad in (flip(body) + '.' + signature,
                    body + '.' + flip(signature),
                    '../../../../etc/passwd',
                    'not-a-token'):
            self.assertIn(client.get('/api/v8/demo/file/' + bad).status_code, (404, 410), bad)
        future = 10 ** 12
        with patch('clipora_v8_web.demo_downloads.time.time', return_value=future):
            self.assertEqual(client.get('/api/v8/demo/file/' + token).status_code, 410)

    def test_invalid_links_never_produce_a_sample(self):
        client = self.client()
        for url in ('https://evil.example/a', 'http://www.tiktok.com/@a/video/1',
                    'javascript:alert(1)', 'https://www.tiktok.com/'):
            self.assertEqual(self.issue(client, url=url).status_code, 422, url)


if __name__ == '__main__':
    unittest.main()
