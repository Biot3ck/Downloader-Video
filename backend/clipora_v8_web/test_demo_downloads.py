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

    def preview(self, client, kind='video', url=TIKTOK, origin=ORIGIN):
        return client.post('/api/v8/demo/preview', headers={'Origin': origin},
                           json={'url': url, 'media_kind': kind})

    def test_routes_are_absent_unless_explicitly_enabled(self):
        client = self.client(demo=False)
        self.assertEqual(self.issue(client).status_code, 404)
        self.assertEqual(self.preview(client).status_code, 404)
        self.assertEqual(client.get('/api/v8/demo/file/anything').status_code, 404)
        self.assertEqual(client.get('/api/v8/demo/preview/anything').status_code, 404)

    def test_routes_stay_absent_on_non_loopback_https_even_with_the_flag(self):
        client = self.client(origin='https://clipora.example')
        self.assertEqual(self.issue(client, origin='https://clipora.example').status_code, 404)
        self.assertEqual(self.preview(client, origin='https://clipora.example').status_code, 404)
        self.assertEqual(client.get('/api/v8/demo/file/anything').status_code, 404)
        self.assertEqual(client.get('/api/v8/demo/preview/anything').status_code, 404)

    def test_preview_returns_the_bundled_clip_and_the_full_caption(self):
        client = self.client()
        response = self.preview(client)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['sample'])
        self.assertFalse(data['network_access_performed'])
        self.assertEqual(data['platform'], 'tiktok')
        self.assertEqual(data['media_kind'], 'video')
        self.assertEqual(data['title'], 'Sample clip · TikTok')
        self.assertEqual((data['width'], data['height']), (640, 360))
        self.assertEqual(data['duration_seconds'], 3)
        self.assertGreater(len(data['caption']), 200)
        self.assertIn('\n', data['caption'])
        self.assertTrue(data['preview_url'].startswith('/api/v8/demo/preview/'))
        self.assertTrue(data['poster_url'].startswith('/api/v8/demo/preview/'))
        served = client.get(data['preview_url'])
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.headers['content-type'], 'video/mp4')
        self.assertIn('inline', served.headers['content-disposition'])
        self.assertGreater(len(served.content), 1024)
        poster = client.get(data['poster_url'])
        self.assertEqual(poster.status_code, 200)
        self.assertEqual(poster.headers['content-type'], 'image/jpeg')

    def test_photo_preview_uses_the_bundled_image_and_no_poster(self):
        client = self.client()
        data = self.preview(client, kind='images', url=PIN).json()
        self.assertEqual(data['platform'], 'pinterest')
        self.assertEqual((data['width'], data['height']), (1280, 720))
        self.assertIsNone(data['duration_seconds'])
        self.assertIsNone(data['poster_url'])
        served = client.get(data['preview_url'])
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.headers['content-type'], 'image/jpeg')
        self.assertIn('inline', served.headers['content-disposition'])

    def test_preview_rejects_unknown_kinds_and_unrecognized_links(self):
        client = self.client()
        self.assertEqual(self.preview(client, kind='audio').status_code, 422)  # no audio surface
        for url in ('https://evil.example/a', 'javascript:alert(1)'):
            self.assertEqual(self.preview(client, url=url).status_code, 422, url)

    def test_preview_tokens_are_signed_and_expire(self):
        client = self.client()
        token = self.preview(client).json()['preview_url'].rsplit('/', 1)[1]
        body, signature = token.split('.')
        self.assertEqual(client.get('/api/v8/demo/preview/' + body + '.' + signature[:-2]).status_code, 404)
        with patch('clipora_v8_web.demo_downloads.time.time', return_value=10 ** 12):
            self.assertEqual(client.get('/api/v8/demo/preview/' + token).status_code, 410)

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

    def test_mp3_download_is_offered_only_for_video_posts(self):
        client = self.client()
        # Photo posts cannot produce audio; the format list is per media kind.
        self.assertEqual(self.issue(client, 'mp3', 'images', PIN).status_code, 422)

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
