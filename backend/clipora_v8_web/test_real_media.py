import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from clipora_v8_web import real_media
from clipora_v8_web.main import create_app

ORIGIN = 'http://127.0.0.1:8090'
TIKTOK_VIDEO = 'https://www.tiktok.com/@tiktok/video/7694797676306615583'
TIKTOK_PHOTO = 'https://www.tiktok.com/@catphotovideo0/photo/7690397576977206536'
POST = {'Origin': ORIGIN, 'Content-Type': 'application/json'}
VIDEO_INFO = {'title': 'Post title', 'caption': 'Full caption', 'duration_seconds': 12,
              'width': 1080, 'height': 1920, 'thumbnail': None,
              'formats': ['video', 'hd', 'mp3']}
IMAGE_INFO = {'title': 'Photo post', 'caption': 'Caption',
              'images': [{'url': 'https://p16-common-sign.tiktokcdn.com/a.jpeg',
                          'width': 816, 'height': 1452}],
              'image_count': 1, 'preview_source': 'https://p16-common-sign.tiktokcdn.com/a.jpeg',
              'formats': ['image'], 'duration_seconds': None}


class FakeYDL:
    def __init__(self, info):
        self.info = info

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        return self.info


class RealRouteTests(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.TemporaryDirectory(prefix='clipora-real-test-')
        self.addCleanup(self.state.cleanup)
        self.root = Path(self.state.name).resolve()
        self.client = TestClient(create_app(ORIGIN, self.root, real_downloads_enabled=True),
                                 base_url=ORIGIN)

    def test_routes_are_absent_without_real_mode(self):
        client = TestClient(create_app(ORIGIN, self.root), base_url=ORIGIN)
        response = client.post('/api/v8/real/preview', headers=POST,
                               json={'url': TIKTOK_VIDEO, 'media_kind': 'video'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(client.get('/healthz').json()['real_downloads_enabled'])

    def test_routes_are_absent_for_non_loopback_origin(self):
        origin = 'https://clipora.example'
        client = TestClient(create_app(origin, self.root, real_downloads_enabled=True),
                            base_url=origin)
        response = client.post('/api/v8/real/preview',
                               headers={'Origin': origin, 'Content-Type': 'application/json'},
                               json={'url': TIKTOK_VIDEO, 'media_kind': 'video'})
        self.assertEqual(response.status_code, 404)

    def test_public_download_stays_closed(self):
        response = self.client.post('/api/v8/download', headers=POST,
                                    json={'url': TIKTOK_VIDEO, 'media_kind': 'video'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get('/healthz').json()['public_downloads_enabled'], False)

    def test_preview_returns_live_contract(self):
        with patch('clipora_v8_web.real_media.probe_video', return_value=dict(VIDEO_INFO)):
            response = self.client.post('/api/v8/real/preview', headers=POST,
                                        json={'url': TIKTOK_VIDEO, 'media_kind': 'video'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['real'])
        self.assertTrue(data['network_access_performed'])
        self.assertEqual(data['platform'], 'tiktok')
        self.assertEqual(data['caption'], 'Full caption')
        self.assertEqual(data['formats'], ['video', 'hd', 'mp3'])
        self.assertTrue(data['preview_url'].startswith('/api/v8/real/media/'))
        self.assertIsNone(data['poster_url'])

    def test_preview_maps_media_errors(self):
        with patch('clipora_v8_web.real_media.probe_video',
                   side_effect=real_media.MediaError('This post contains photos only.', 422)):
            response = self.client.post('/api/v8/real/preview', headers=POST,
                                        json={'url': TIKTOK_VIDEO, 'media_kind': 'video'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['detail'], 'This post contains photos only.')

    def test_preview_hides_unexpected_extractor_failures(self):
        with patch('clipora_v8_web.real_media.probe_video', side_effect=RuntimeError('boom')):
            response = self.client.post('/api/v8/real/preview', headers=POST,
                                        json={'url': TIKTOK_VIDEO, 'media_kind': 'video'})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('boom', response.json()['detail'])

    def test_preview_rejects_unsupported_media_kind_and_platform(self):
        response = self.client.post('/api/v8/real/preview', headers=POST,
                                    json={'url': TIKTOK_VIDEO, 'media_kind': 'audio2'})
        self.assertEqual(response.status_code, 422)
        response = self.client.post('/api/v8/real/preview', headers=POST,
                                    json={'url': 'https://www.youtube.com/watch?v=71ya_JC_IbM',
                                          'media_kind': 'images'})
        self.assertEqual(response.status_code, 422)

    def test_audio_preview_uses_video_contract_and_mp3_only(self):
        with patch('clipora_v8_web.real_media.probe_video', return_value=dict(VIDEO_INFO)):
            response = self.client.post('/api/v8/real/preview', headers=POST,
                                        json={'url': TIKTOK_VIDEO, 'media_kind': 'audio'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['media_kind'], 'audio')
        self.assertEqual(response.json()['formats'], ['mp3'])

    def test_image_preview_reports_count_and_signed_url(self):
        with patch('clipora_v8_web.real_media.extract_images', return_value=dict(IMAGE_INFO)):
            response = self.client.post('/api/v8/real/preview', headers=POST,
                                        json={'url': TIKTOK_PHOTO, 'media_kind': 'images'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['image_count'], 1)
        self.assertEqual(data['formats'], ['image'])
        self.assertTrue(data['preview_url'].startswith('/api/v8/real/media/'))

    def test_preview_media_is_inline_and_supports_ranges(self):
        media = self.root / 'preview.mp4'
        media.write_bytes(b'0123456789' * 100)
        with patch('clipora_v8_web.real_media.probe_video', return_value=dict(VIDEO_INFO)):
            preview = self.client.post('/api/v8/real/preview', headers=POST,
                                       json={'url': TIKTOK_VIDEO, 'media_kind': 'video'}).json()
        with patch.object(real_media.MediaStore, 'preview_file',
                          return_value=(media, 'video/mp4')):
            response = self.client.get(preview['preview_url'])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['content-type'], 'video/mp4')
            self.assertIn('inline', response.headers['content-disposition'])
            self.assertEqual(len(response.content), 1000)
            partial = self.client.get(preview['preview_url'], headers={'Range': 'bytes=0-9'})
            self.assertEqual(partial.status_code, 206)
            self.assertEqual(partial.content, b'0123456789')

    def test_download_contract_and_attachment(self):
        cache = self.root / 'media'
        cache.mkdir(exist_ok=True)
        output = cache / ('a' * 64 + '.mp4')
        output.write_bytes(b'video-bytes')
        with patch.object(real_media.MediaStore, 'download',
                          return_value=(output, 'video/mp4', 'clipora-tiktok-video.mp4')):
            response = self.client.post('/api/v8/real/download', headers=POST,
                                        json={'url': TIKTOK_VIDEO, 'media_kind': 'video',
                                              'format': 'video'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['real'])
        self.assertEqual(data['filename'], 'clipora-tiktok-video.mp4')
        self.assertTrue(data['url'].startswith('/api/v8/real/file/'))
        file_response = self.client.get(data['url'])
        self.assertEqual(file_response.status_code, 200)
        self.assertEqual(file_response.content, b'video-bytes')
        self.assertIn('attachment', file_response.headers['content-disposition'])

    def test_download_rejects_format_outside_media_kind(self):
        for media_kind, fmt in (('audio', 'video'), ('images', 'mp3'), ('video', 'image')):
            response = self.client.post('/api/v8/real/download', headers=POST,
                                        json={'url': TIKTOK_VIDEO, 'media_kind': media_kind,
                                              'format': fmt})
            self.assertEqual(response.status_code, 422, (media_kind, fmt))

    def test_tampered_and_expired_tokens_are_rejected(self):
        now = [1_000]
        store = real_media.MediaStore(self.root, clock=lambda: now[0])
        token = store.sign({'t': 'download', 'n': 'a' * 64 + '.mp4', 'm': 'video/mp4',
                            'f': 'x.mp4', 'e': 1_060})
        self.assertEqual(store.read(token)['f'], 'x.mp4')
        with self.assertRaises(HTTPException) as caught:
            store.read(token[:-2] + ('AA' if not token.endswith('AA') else 'BB'))
        self.assertEqual(caught.exception.status_code, 404)
        now[0] = 2_000
        with self.assertRaises(HTTPException) as caught:
            store.read(token)
        self.assertEqual(caught.exception.status_code, 410)

    def test_file_lookup_rejects_paths_outside_the_cache(self):
        store = real_media.MediaStore(self.root)
        for name in ('../secret.mp4', '/etc/passwd', 'a' * 64 + '.txt', None):
            with self.assertRaises(HTTPException) as caught:
                store.file(name)
            self.assertEqual(caught.exception.status_code, 404)

    def test_config_advertises_real_mode(self):
        self.assertTrue(self.client.get('/healthz').json()['real_downloads_enabled'])
        self.assertTrue(self.client.get('/api/v8/ui/config').json()['real_downloads_enabled'])
        response = self.client.post('/api/v8/validate', headers=POST,
                                    json={'url': TIKTOK_VIDEO, 'media_kind': 'video'})
        self.assertTrue(response.json()['real_downloads_enabled'])
        self.assertFalse(response.json()['public_downloads_enabled'])


class ExtractorTests(unittest.TestCase):
    def test_ytdl_opts_request_a_browser_fingerprint_when_available(self):
        with patch.object(real_media, '_impersonation_target', return_value='chrome'):
            options = real_media._ytdl_opts()
        self.assertEqual(options['impersonate'], 'chrome')

    def test_ytdl_opts_stay_plain_without_curl_cffi(self):
        with patch.object(real_media, '_impersonation_target', return_value=None):
            options = real_media._ytdl_opts()
        self.assertNotIn('impersonate', options)

    def test_impersonation_target_is_none_without_curl_cffi(self):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in ('curl_cffi', 'yt_dlp.networking.impersonate'):
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, '__import__', fake_import):
            self.assertIsNone(real_media._impersonation_target())

    def test_probe_rejects_audio_only_slideshows(self):
        info = {'formats': [{'vcodec': 'none', 'acodec': 'mp3'}], 'duration': 24}
        with patch('yt_dlp.YoutubeDL', lambda options: FakeYDL(info)):
            with self.assertRaises(real_media.MediaError) as caught:
                real_media.probe_video(TIKTOK_PHOTO, 'tiktok')
        self.assertEqual(caught.exception.status, 422)
        self.assertIn('Photo Downloader', str(caught.exception))

    def test_probe_enforces_duration_limit(self):
        info = {'formats': [{'vcodec': 'h264', 'acodec': 'aac'}], 'duration': 601}
        with patch('yt_dlp.YoutubeDL', lambda options: FakeYDL(info)):
            with self.assertRaises(real_media.MediaError) as caught:
                real_media.probe_video(TIKTOK_VIDEO, 'tiktok')
        self.assertEqual(caught.exception.status, 413)

    def test_probe_uses_first_playlist_entry_with_formats(self):
        info = {'_type': 'playlist', 'entries': [
            {'formats': [], 'title': 'image'},
            {'formats': [{'vcodec': 'h264', 'acodec': 'aac'}], 'duration': 9,
             'title': 'clip', 'description': 'caption'}]}
        with patch('yt_dlp.YoutubeDL', lambda options: FakeYDL(info)):
            result = real_media.probe_video('https://www.instagram.com/p/abc/', 'instagram')
        self.assertEqual(result['title'], 'clip')
        self.assertEqual(result['caption'], 'caption')
        self.assertEqual(result['duration_seconds'], 9)

    def test_probe_reports_the_standard_stream_size(self):
        info = {'formats': [{'vcodec': 'h264', 'height': 1080, 'width': 1920},
                            {'vcodec': 'h264', 'height': 720, 'width': 1280}],
                'duration': 9, 'title': 'clip'}
        with patch('yt_dlp.YoutubeDL', lambda options: FakeYDL(info)):
            result = real_media.probe_video(TIKTOK_VIDEO, 'tiktok')
        self.assertEqual((result['width'], result['height']), (1280, 720))

    def test_probe_maps_photo_only_posts_to_guidance(self):
        from yt_dlp.utils import DownloadError

        class FailingYDL:
            def __init__(self, options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                raise DownloadError('[Instagram] abc: No video formats found!')

        with patch('yt_dlp.YoutubeDL', FailingYDL):
            with self.assertRaises(real_media.MediaError) as caught:
                real_media.probe_video('https://www.instagram.com/p/abc/', 'instagram')
        self.assertEqual(caught.exception.status, 422)
        self.assertIn('Photo Downloader', str(caught.exception))

    def test_youtube_bot_check_becomes_platform_guidance(self):
        error = real_media._ydl_error(
            Exception("ERROR: [youtube] abc: Sign in to confirm you’re not a bot."))
        self.assertEqual(error.status, 422)
        self.assertIn('TikTok, Instagram, or Pinterest', str(error))

    def test_public_url_rejects_private_and_credentialed_hosts(self):
        private = [(2, 1, 6, '', ('127.0.0.1', 443))]
        with patch('socket.getaddrinfo', return_value=private):
            with self.assertRaises(real_media.MediaError) as caught:
                real_media._public_url('https://cdn.example/a.jpg')
        self.assertEqual(caught.exception.status, 502)
        for url in ('http://cdn.example/a.jpg', 'https://user:pw@cdn.example/a.jpg',
                    'https://cdn.example:8443/a.jpg'):
            with self.assertRaises(real_media.MediaError):
                real_media._public_url(url)
        public = [(2, 1, 6, '', ('93.184.216.34', 443))]
        with patch('socket.getaddrinfo', return_value=public):
            self.assertEqual(real_media._public_url('https://cdn.example/a.jpg'),
                             'https://cdn.example/a.jpg')

    def test_image_suffix_uses_magic_bytes(self):
        self.assertEqual(real_media._image_suffix('application/octet-stream',
                                                  b'\xff\xd8rest'), ('jpg', 'image/jpeg'))
        self.assertEqual(real_media._image_suffix('image/png', b'\x89PNG\r\n\x1a\n'), ('png', 'image/png'))
        self.assertEqual(real_media._image_suffix('image/webp', b'RIFF0000WEBP'), ('webp', 'image/webp'))
        with self.assertRaises(real_media.MediaError):
            real_media._image_suffix('image/gif', b'GIF89a')

    def test_mp3_downloads_use_the_audio_cache_and_extension(self):
        root = tempfile.TemporaryDirectory(prefix='clipora-real-mp3-')
        self.addCleanup(root.cleanup)
        store = real_media.MediaStore(Path(root.name))
        target = Path(root.name) / ('a' * 64 + '.mp3')
        target.write_bytes(b'ID3')
        with patch.object(real_media.MediaStore, 'preview_file',
                          return_value=(target, 'audio/mpeg')):
            path, mime, name = store.download(TIKTOK_VIDEO, 'video', 'mp3', 'tiktok')
        self.assertEqual((path, mime, name),
                         (target, 'audio/mpeg', 'clipora-tiktok-audio.mp3'))

    def test_image_download_bundles_carousels_as_zip(self):
        root = tempfile.TemporaryDirectory(prefix='clipora-real-images-')
        self.addCleanup(root.cleanup)
        store = real_media.MediaStore(Path(root.name))
        images = {'title': 't', 'caption': 'c',
                  'images': [{'url': f'https://cdn.example/{i}.jpg'} for i in range(2)]}
        payloads = [(b'\xff\xd8one', 'image/jpeg'), (b'\xff\xd8two', 'image/jpeg')]
        with patch('clipora_v8_web.real_media.extract_images', return_value=images), \
                patch('clipora_v8_web.real_media._fetch_bytes', side_effect=payloads):
            path, mime, name = store.download(TIKTOK_PHOTO, 'images', 'image', 'tiktok')
        self.assertEqual(mime, 'application/zip')
        self.assertEqual(name, 'clipora-tiktok-images.zip')
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.namelist(), ['clipora-01.jpg', 'clipora-02.jpg'])

    def test_single_image_download_keeps_the_image(self):
        root = tempfile.TemporaryDirectory(prefix='clipora-real-image-')
        self.addCleanup(root.cleanup)
        store = real_media.MediaStore(Path(root.name))
        images = {'title': 't', 'caption': 'c', 'images': [{'url': 'https://cdn.example/1.jpg'}]}
        with patch('clipora_v8_web.real_media.extract_images', return_value=images), \
                patch('clipora_v8_web.real_media._fetch_bytes',
                      return_value=(b'\xff\xd8one', 'image/jpeg')):
            path, mime, name = store.download(TIKTOK_PHOTO, 'images', 'image', 'tiktok')
        self.assertEqual((mime, name), ('image/jpeg', 'clipora-tiktok.jpg'))
        self.assertEqual(path.read_bytes(), b'\xff\xd8one')


class ConversionIsolationTests(unittest.TestCase):
    """Conversion must never follow URLs or parsers outside the allowlist."""

    def fake_run(self, calls, format_name='matroska,webm', video='vp9', audio='opus'):
        def run(command, **kwargs):
            calls.append(command)
            if command[0] == 'ffprobe':
                streams = [{'codec_type': 'video', 'codec_name': video, 'pix_fmt': 'yuv420p'},
                           {'codec_type': 'audio', 'codec_name': audio}]
                stdout = json.dumps({'format': {'format_name': format_name},
                                     'streams': streams})
            else:
                stdout = ''
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr='')
        return run

    def test_ffmpeg_and_ffprobe_only_read_local_files(self):
        calls = []
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'input.webm'
            source.write_bytes(b'x')
            output = Path(root) / 'output.mp4'
            with patch('clipora_v8_web.real_media.subprocess.run',
                       side_effect=self.fake_run(calls)):
                real_media._to_mp4(source, output)
                real_media._to_mp3(source, output)

        ffprobe = [c for c in calls if c[0] == 'ffprobe']
        ffmpeg = [c for c in calls if c[0] == 'ffmpeg']
        self.assertTrue(ffprobe)
        self.assertTrue(ffmpeg)
        for command in ffprobe + ffmpeg:
            index = command.index('-protocol_whitelist')
            self.assertEqual(command[index + 1], 'file')
        for command in ffmpeg:
            self.assertIn('-nostdin', command)
            self.assertEqual(command[command.index('-f') + 1], 'matroska')

    def test_unexpected_container_is_rejected_before_conversion(self):
        calls = []
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'input.bin'
            source.write_bytes(b'x')
            with patch('clipora_v8_web.real_media.subprocess.run',
                       side_effect=self.fake_run(calls, 'image2')):
                with self.assertRaises(real_media.MediaError) as caught:
                    real_media._to_mp4(source, Path(root) / 'output.mp4')
        self.assertEqual(caught.exception.status, 422)
        self.assertFalse([c for c in calls if c[0] == 'ffmpeg'])

    def test_mp4_family_pins_the_mov_demuxer(self):
        calls = []
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'input.m4a'
            source.write_bytes(b'x')
            with patch('clipora_v8_web.real_media.subprocess.run',
                       side_effect=self.fake_run(calls, 'mov,mp4,m4a,3gp,3g2,mj2')):
                real_media._to_mp3(source, Path(root) / 'output.mp3')
        ffmpeg = [c for c in calls if c[0] == 'ffmpeg'][0]
        self.assertEqual(ffmpeg[ffmpeg.index('-f') + 1], 'mov')

    def test_decoder_outside_the_allowlist_is_rejected(self):
        calls = []
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'input.mp4'
            source.write_bytes(b'x')
            with patch('clipora_v8_web.real_media.subprocess.run',
                       side_effect=self.fake_run(calls, 'mov,mp4', video='jpeg2000')):
                with self.assertRaises(real_media.MediaError) as caught:
                    real_media._to_mp4(source, Path(root) / 'output.mp4')
        self.assertEqual(caught.exception.status, 422)
        self.assertFalse([c for c in calls if c[0] == 'ffmpeg'])

    def test_hevc_and_aac_are_allowed(self):
        calls = []
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'input.mov'
            source.write_bytes(b'x')
            with patch('clipora_v8_web.real_media.subprocess.run',
                       side_effect=self.fake_run(calls, 'mov,mp4', video='hevc', audio='aac')):
                real_media._to_mp4(source, Path(root) / 'output.mp4')
        self.assertTrue([c for c in calls if c[0] == 'ffmpeg'])


if __name__ == '__main__':
    unittest.main()
