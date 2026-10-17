"""Image-mode request boundaries. No extractor or internet access is enabled."""
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from clipora_v8_web.main import create_app
from clipora_v8_web.platforms import recognize_media

ORIGIN='http://127.0.0.1:8090'


class ImageModeTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client=TestClient(create_app(ORIGIN,self.directory.name),base_url=ORIGIN)

    def validate(self,payload):
        return self.client.post('/api/v8/validate',json=payload,headers={'Origin':ORIGIN})

    def test_photo_posts_and_shortlinks_never_resolve_or_dial(self):
        urls={'https://www.tiktok.com/@author/photo/123':'tiktok',
              'https://vt.tiktok.com/sample/':'tiktok',
              'https://www.instagram.com/p/album/':'instagram',
              'https://www.pinterest.com/pin/123/':'pinterest',
              'https://pin.it/sample':'pinterest'}
        with patch('socket.getaddrinfo',side_effect=AssertionError('No DNS')),patch(
                'socket.create_connection',side_effect=AssertionError('No sockets')):
            for url,platform in urls.items():
                response=self.validate({'url':url,'media_kind':'images'})
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['media_kind'],'images')
                self.assertEqual(response.json()['platform'],platform)
                self.assertFalse(response.json()['network_access_performed'])
                self.assertFalse(response.json()['public_downloads_enabled'])

    def test_legacy_video_request_keeps_working(self):
        self.assertEqual(self.validate({'url':'https://youtu.be/sample'}).json()['media_kind'],'video')
        self.assertEqual(self.validate({'url':'https://youtu.be/sample','media_kind':'images'}).status_code,422)

    def test_invalid_media_kind_and_extra_fields_rejected(self):
        for kind in ('image','all','audio','',None,False,[],{},123):
            response=self.validate({'url':'https://pin.it/a','media_kind':kind})
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.validate({'url':'https://pin.it/a','media_kind':'images','proxy':'http://evil'}).status_code,422)

    def test_image_mode_keeps_ssrf_input_rejections(self):
        for url in ('https://127.0.0.1/a','https://instagram.com.evil.test/p/a',
                    'https://user@instagram.com/p/a','https://pin.it:443/a',
                    'https://www.tiktok.com/%0d%0a','http://pin.it/a'):
            with self.subTest(url=url),self.assertRaises(ValueError):
                recognize_media(url,'images')

    def test_image_submission_cannot_bypass_public_gate(self):
        response=self.client.post('/api/v8/download',json={'url':'https://pin.it/a','media_kind':'images'},headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,503)
        self.assertEqual(self.client.get('/api/v8/images/jobs').status_code,404)
        config=self.client.get('/api/v8/ui/config').json()
        self.assertEqual(config['planned_media']['images'],['tiktok','instagram','pinterest'])
        self.assertFalse(config['public_downloads_enabled'])

    def test_device_preview_removed_and_backend_images_still_available(self):
        page=self.client.get('/')
        self.assertNotIn('ON YOUR DEVICE',page.text)
        self.assertNotIn('type="file"',page.text)
        self.assertIn('image-sample-mode',page.text)
        self.assertEqual(self.client.get('/assets/images.js').status_code,404)
        self.assertIn("img-src 'self';",page.headers['content-security-policy'])
        self.assertNotIn('blob:',page.headers['content-security-policy'])


if __name__=='__main__':unittest.main()
