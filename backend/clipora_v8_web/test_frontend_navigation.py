"""Product/developer separation and supported-feature boundaries."""
from html.parser import HTMLParser
import tempfile
import unittest
from fastapi.testclient import TestClient
from clipora_v8_web.main import create_app

ORIGIN='http://127.0.0.1:8090'


class Markup(HTMLParser):
    def __init__(self,text):
        super().__init__();self.links=[];self.disabled=set();self.scripts=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='a' and 'data-view' in attrs:self.links.append((attrs['data-view'],attrs['href']))
        if 'disabled' in attrs:self.disabled.add(attrs.get('id',tag))
        if tag=='script':self.scripts.append(attrs.get('src'))


class FrontendNavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
    def client(self,origin=ORIGIN,enabled=False):
        return TestClient(create_app(origin,self.temp.name,offline_sample_enabled=enabled),base_url=origin)
    def test_four_feature_navigation_without_fixture_or_device_controls(self):
        for enabled in (False,True):
            text=self.client(enabled=enabled).get('/').text;page=Markup(text)
            self.assertEqual(page.links,[('video','#video'),('photo','#photo'),('audio','#audio'),('history','#history')])
            self.assertEqual(page.scripts,['/assets/app.js'])
            for value in ('Try a sample','sample-start','image-sample-gallery','type="file"','ON YOUR DEVICE','Your image gallery'):
                self.assertNotIn(value,text)
    def test_unsupported_audio_is_disabled_and_history_honest(self):
        text=self.client().get('/').text;page=Markup(text)
        self.assertIn('audio-url',page.disabled)
        self.assertIn('button',page.disabled)
        self.assertIn("History isn't available yet",text)
        self.assertIn('MP3',text)  # Preference in Video; extraction remains disabled.
        self.assertNotIn('320 kbps',text)
    def test_default_product_does_not_serve_developer_or_archived_code(self):
        client=self.client()
        for path in ('/dev','/assets/dev.js','/assets/dev.css','/tools_archive/device-preview/images.js'):
            self.assertEqual(client.get(path).status_code,404,path)
    def test_explicit_loopback_preview_preserves_developer_utilities(self):
        client=self.client(enabled=True)
        self.assertEqual(client.get('/dev').status_code,200)
        self.assertIn('sample-start',client.get('/dev').text)
        self.assertIn('image-sample-start',client.get('/dev').text)
        self.assertEqual(client.get('/assets/dev.js').status_code,200)
        self.assertEqual(client.get('/assets/dev.css').status_code,200)
        self.assertEqual(client.get('/tools_archive/device-preview/images.js').status_code,404)
    def test_https_does_not_expose_developer_utilities_even_with_fixture_flag(self):
        client=self.client(origin='https://clipora.example',enabled=True)
        for path in ('/dev','/assets/dev.js','/assets/dev.css'):
            self.assertEqual(client.get(path).status_code,404,path)
    def test_no_audio_or_history_api_invented_and_public_download_gate_intact(self):
        client=self.client(enabled=True)
        for path in ('/api/v8/audio','/api/v8/history'):
            self.assertEqual(client.get(path).status_code,404)
        for kind in ('video','images','audio'):
            self.assertEqual(client.post('/api/v8/download',headers={'Origin':ORIGIN},json={'media_kind':kind,'url':'https://pin.it/a'}).status_code,503)
        # Client assertions about ads/quality must never unlock the public gate.
        for output in ('video','hd','mp3'):
            self.assertEqual(client.post('/api/v8/download',headers={'Origin':ORIGIN},
                json={'url':'https://youtu.be/abc','format':output,'reward_completed':True}).status_code,503)


if __name__=='__main__':unittest.main()
