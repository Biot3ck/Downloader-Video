"""Tes fungsi murni untuk alat spike. Tidak ada akses jaringan di sini."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clipora_v8_spike.spike import (
    analyze,
    classify,
    read_ok_urls,
    read_urls,
    render_markdown,
    success_rate,
    verdict,
)


class ClassifyTests(unittest.TestCase):
    def test_platforms(self) -> None:
        cases = {
            "https://www.tiktok.com/@user/video/123": "tiktok",
            "https://vm.tiktok.com/ZMabc/": "tiktok",
            "https://www.instagram.com/reel/abc/": "instagram",
            "https://instagr.am/p/abc/": "instagram",
            "https://www.pinterest.com/pin/123/": "pinterest",
            "https://pin.it/abc": "pinterest",
            "https://www.youtube.com/watch?v=abc": "youtube",
            "https://youtu.be/abc": "youtube",
            "https://example.com/x": "unknown",
            "bukan url": "unknown",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(classify(url), expected)

    def test_does_not_match_lookalike_host(self) -> None:
        self.assertEqual(classify("https://nottiktok.com/x"), "unknown")
        self.assertEqual(classify("https://tiktok.com.evil.io/x"), "unknown")


class ReadUrlsTests(unittest.TestCase):
    def test_comments_blank_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "urls.txt"
            path.write_text(
                "# komentar\n\nhttps://a.com/1\nhttps://a.com/1  # duplikat\nhttps://b.com/2\n",
                encoding="utf-8",
            )
            self.assertEqual(read_urls(path), ["https://a.com/1", "https://b.com/2"])


class AnalyzeTests(unittest.TestCase):
    def test_separates_watermark_candidates(self) -> None:
        info = {
            "title": "contoh",
            "extractor_key": "TikTok",
            "duration": 12.5,
            "formats": [
                {"format_id": "download", "url": "https://cdn/x", "height": 720, "filesize": 1000},
                {"format_id": "play", "url": "https://cdn/y", "height": 1080, "filesize": 2000},
                {"format_id": "audio", "url": "https://cdn/z", "vcodec": "none"},
            ],
        }
        result = analyze(info)
        self.assertEqual(result["max_height"], 1080)
        self.assertEqual(result["size_bytes"], 2000)
        self.assertEqual(result["watermark_formats"], 1)
        self.assertEqual(result["clean_formats"], 2)

    def test_handles_missing_formats(self) -> None:
        result = analyze({"title": "x"})
        self.assertIsNone(result["max_height"])
        self.assertIsNone(result["size_bytes"])
        self.assertEqual(result["format_count"], 0)

    def test_slideshow_entries_are_flattened(self) -> None:
        info = {
            "extractor_key": "TikTok",
            "entries": [
                {"ext": "jpg", "formats": []},
                {"ext": "jpg", "formats": []},
                {"ext": "mp4", "formats": [{"format_id": "play", "height": 720, "filesize": 500}]},
            ],
        }
        result = analyze(info)
        self.assertEqual(result["image_count"], 2)
        self.assertTrue(result["is_slideshow"])
        self.assertEqual(result["max_height"], 720)


class SummaryTests(unittest.TestCase):
    def test_success_rate_and_errors(self) -> None:
        rows = [
            {"platform": "tiktok", "ok": True},
            {"platform": "tiktok", "ok": False, "error": "ERROR: tidak tersedia"},
            {"platform": "youtube", "ok": False, "error": "ERROR: bot check"},
        ]
        summary = success_rate(rows)
        self.assertEqual(summary["tiktok"]["total"], 2)
        self.assertEqual(summary["tiktok"]["rate"], 50.0)
        self.assertEqual(summary["youtube"]["rate"], 0.0)

    def test_verdict_stop_below_seventy(self) -> None:
        self.assertIn("STOP", verdict({"tiktok": {"total": 10, "ok": 6, "rate": 60.0}}))

    def test_verdict_narrow_when_others_weak(self) -> None:
        summary = {
            "tiktok": {"total": 10, "ok": 9, "rate": 90.0},
            "youtube": {"total": 10, "ok": 3, "rate": 30.0},
        }
        self.assertIn("SEMPITKAN", verdict(summary))

    def test_verdict_continue(self) -> None:
        summary = {
            "tiktok": {"total": 10, "ok": 9, "rate": 90.0},
            "pinterest": {"total": 10, "ok": 10, "rate": 100.0},
        }
        self.assertIn("LANJUT:", verdict(summary))

    def test_markdown_contains_tables(self) -> None:
        rows = [{"platform": "tiktok", "ok": True, "max_height": 1080, "size_bytes": 2_097_152,
                 "clean_formats": 2, "watermark_formats": 1, "is_slideshow": False}]
        text = render_markdown(rows, success_rate(rows), "uji.csv")
        self.assertIn("| tiktok | 1 | 1 | 100.0% |", text)
        self.assertIn("2.0 MB", text)
        self.assertIn("Keputusan otomatis", text)


class CsvRoundTripTests(unittest.TestCase):
    def test_read_ok_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hasil.csv"
            path.write_text(
                "platform,url,ok\ntiktok,https://a/1,True\ntiktok,https://a/2,False\n",
                encoding="utf-8",
            )
            self.assertEqual(read_ok_urls(path), {"https://a/1"})


if __name__ == "__main__":
    unittest.main()
