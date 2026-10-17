import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from install_v8_worker import install, patched, NEW_META, NEW_DOWNLOAD
from worker_proxy import required_proxy_settings

SAMPLE = '''from yt_dlp import YoutubeDL

def f():
    with YoutubeDL(ydl_options()) as ydl:
        ydl.extract_info('url',download=False)
    with YoutubeDL(ydl_options(folder)) as ydl:
        ydl.extract_info('url',download=True)
'''

class Tests(unittest.TestCase):
    def test_two_download_passes_use_proxy(self):
        data = patched(SAMPLE)
        self.assertIn(NEW_META, data)
        self.assertIn(NEW_DOWNLOAD, data)
    def test_missing_proxy_fail_closed(self):
        with self.assertRaises(RuntimeError):
            required_proxy_settings({}, {})
    def test_invalid_proxy_rejected(self):
        with self.assertRaises(RuntimeError):
            required_proxy_settings({}, {'CLIPORA_V8_PROXY_URL':'http://x:3128'})
    def test_no_silent_source_mismatch(self):
        with self.assertRaises(ValueError):
            patched(SAMPLE.replace('ydl_options(folder)', 'ydl_options(download_dir)'))
    def test_install_does_not_change_v7(self):
        with tempfile.TemporaryDirectory() as d:
            base = pathlib.Path(d)
            src = base / 'real_download_worker.py'
            src.write_text(SAMPLE)
            self.assertIn('INSTALLED', install(base))
            self.assertEqual(src.read_text(), SAMPLE)
            self.assertIn('ALREADY', install(base))
    def test_never_overwrite_existing_v8(self):
        with tempfile.TemporaryDirectory() as d:
            base = pathlib.Path(d)
            (base / 'real_download_worker.py').write_text(SAMPLE)
            (base / 'real_download_worker_v8.py').write_text('existing')
            with self.assertRaises(FileExistsError):
                install(base)

if __name__ == '__main__': unittest.main()
