"""Tes fungsi murni untuk alat spike. Tidak ada akses jaringan di sini."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clipora_v8_spike.spike import (
    analyze,
    audit,
    classify,
    egress_warning,
    error_kind,
    no_media_reason,
    probe_command,
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
        self.assertEqual(result["video_formats"], 2)

    def test_audio_only_extraction_is_not_usable_media(self) -> None:
        info = {"extractor_key": "TikTok", "formats": [{"format_id": "audio", "vcodec": "none"}]}
        result = analyze(info)
        self.assertEqual(result["video_formats"], 0)
        self.assertEqual(result["image_count"], 0)
        self.assertIn("tidak ada format video/gambar", no_media_reason(
            result["video_formats"], result["image_count"]))

    def test_usable_media_needs_video_or_image(self) -> None:
        self.assertEqual(no_media_reason(3, 0), "")
        self.assertEqual(no_media_reason(0, 2), "")
        self.assertNotEqual(no_media_reason(0, 0), "")

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

    def test_verdict_requires_tiktok_data(self) -> None:
        self.assertIn("TIDAK ADA DATA", verdict({}))
        self.assertIn("TIDAK ADA DATA", verdict({"youtube": {"total": 5, "ok": 1, "rate": 20.0}}))

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

    def test_markdown_records_egress_ip(self) -> None:
        rows = [{"platform": "tiktok", "ok": True}]
        text = render_markdown(rows, success_rate(rows), "uji.csv", "203.0.113.9")
        self.assertIn("`203.0.113.9`", text)


class ErrorKindTests(unittest.TestCase):
    def test_dead_or_private_urls_are_not_extraction_failures(self) -> None:
        for error in ("ERROR: [TikTok] 123: HTTP Error 404: Not Found",
                      "ERROR: Video unavailable",
                      "ERROR: This video is private",
                      "ERROR: Requested content is not available"):
            with self.subTest(error=error):
                self.assertEqual(error_kind(error), "invalid")

    def test_platform_failures_stay_extraction_failures(self) -> None:
        for error in ("ERROR: Sign in to confirm you are not a bot",
                      "timeout>45s",
                      "ERROR: Unable to download webpage: HTTP Error 403",
                      ""):
            with self.subTest(error=error):
                self.assertEqual(error_kind(error), "extraction")

    def test_image_only_posts_are_their_own_category(self) -> None:
        for error in ("ERROR: [Instagram] X: There is no video in this post",
                      "ERROR: [Pinterest] 123: No video formats found!; please report this issue",
                      "ERROR: Unsupported URL: https://www.tiktok.com/@u/photo/1"):
            with self.subTest(error=error):
                self.assertEqual(error_kind(error), "image")

    def test_success_rate_ignores_dead_urls(self) -> None:
        rows = [
            {"platform": "tiktok", "ok": True},
            {"platform": "tiktok", "ok": True},
            {"platform": "tiktok", "ok": False, "error": "ERROR: Video unavailable",
             "error_kind": "invalid"},
            {"platform": "tiktok", "ok": False, "error": "ERROR: bot check",
             "error_kind": "extraction"},
        ]
        summary = success_rate(rows)
        self.assertEqual(summary["tiktok"]["total"], 3)
        self.assertEqual(summary["tiktok"]["skipped"], 1)
        self.assertEqual(summary["tiktok"]["rate"], 66.7)

    def test_success_rate_measures_video_only(self) -> None:
        rows = [
            {"platform": "tiktok", "ok": True},
            {"platform": "tiktok", "ok": False, "error": "There is no video in this post",
             "error_kind": "image"},
        ]
        summary = success_rate(rows)
        self.assertEqual(summary["tiktok"]["total"], 1)
        self.assertEqual(summary["tiktok"]["image_only"], 1)
        self.assertEqual(summary["tiktok"]["rate"], 100.0)

    def test_verdict_refuses_a_sample_that_is_too_small(self) -> None:
        summary = {"tiktok": {"total": 3, "ok": 3, "rate": 100.0, "skipped": 0}}
        self.assertIn("DATA KURANG", verdict(summary))
        self.assertNotIn("LANJUT", verdict(summary))

    def test_markdown_separates_dead_urls_from_failures(self) -> None:
        rows = [
            {"platform": "tiktok", "ok": True},
            {"platform": "tiktok", "ok": False, "error": "ERROR: Video unavailable",
             "error_kind": "invalid"},
        ]
        text = render_markdown(rows, success_rate(rows), "uji.csv")
        self.assertIn("URL mati/privat, tidak dihitung", text)
        self.assertIn("tiktok 1", text)
        self.assertIn("URL tidak bisa diuji", text)
        self.assertIn("Tidak ada kegagalan ekstraksi video.", text)

    def test_markdown_reports_image_posts_separately(self) -> None:
        rows = [
            {"platform": "tiktok", "ok": True},
            {"platform": "pinterest", "ok": False, "error": "No video formats found!",
             "error_kind": "image"},
        ]
        text = render_markdown(rows, success_rate(rows), "uji.csv")
        self.assertIn("Post hanya gambar (diukur terpisah, bukan kegagalan video)", text)
        self.assertIn("pinterest 1", text)
        self.assertIn("## Post hanya gambar", text)
        self.assertNotIn("pinterest | `No video formats found!", text.split("## Post hanya gambar")[0])


class AuditTests(unittest.TestCase):
    def test_counts_per_platform_and_flags_short_lists(self) -> None:
        urls = ["https://www.tiktok.com/@u/video/1", "https://youtu.be/a", "https://example.com/x"]
        report = audit(urls)
        self.assertEqual(report["counts"]["tiktok"], 1)
        self.assertEqual(report["counts"]["youtube"], 1)
        self.assertEqual(report["counts"]["instagram"], 0)
        self.assertEqual(report["unknown"], ["https://example.com/x"])
        self.assertIn("tiktok: 1 URL (target 20)", report["warnings"])
        self.assertIn("1 URL tidak dikenali platformnya", report["warnings"])

    def test_full_list_has_no_warnings(self) -> None:
        urls = [f"https://www.tiktok.com/@u/video/{i}" for i in range(20)]
        urls += [f"https://youtu.be/{i}" for i in range(20)]
        urls += [f"https://www.instagram.com/reel/{i}/" for i in range(20)]
        urls += [f"https://www.pinterest.com/pin/{i}/" for i in range(20)]
        self.assertEqual(audit(urls)["warnings"], [])


class EgressWarningTests(unittest.TestCase):
    def test_private_ip_is_flagged(self) -> None:
        for ip in ("10.0.0.5", "192.168.1.10", "172.17.0.2", "127.0.0.1"):
            with self.subTest(ip=ip):
                self.assertIn("privat", egress_warning(ip))

    def test_unknown_is_flagged(self) -> None:
        self.assertIn("tidak terdeteksi", egress_warning("unknown"))

    def test_public_ip_is_silent(self) -> None:
        self.assertEqual(egress_warning("203.0.113.9"), "")


class ProbeCommandTests(unittest.TestCase):
    def test_default_command_puts_the_url_last(self) -> None:
        cmd = probe_command("https://example.test/x")
        self.assertEqual(cmd[-1], "https://example.test/x")
        self.assertNotIn("--impersonate", cmd)
        self.assertNotIn("--cookies", cmd)

    def test_impersonation_is_passed_before_the_url(self) -> None:
        cmd = probe_command("https://example.test/x", impersonate="chrome")
        self.assertEqual(cmd[-1], "https://example.test/x")
        self.assertEqual(cmd[cmd.index("--impersonate") + 1], "chrome")

    def test_cookies_are_passed_before_the_url(self) -> None:
        cmd = probe_command("https://example.test/x", cookies=Path("/tmp/c.txt"))
        self.assertEqual(cmd[-1], "https://example.test/x")
        self.assertEqual(cmd[cmd.index("--cookies") + 1], "/tmp/c.txt")

    def test_extractor_args_are_passed_before_the_url(self) -> None:
        cmd = probe_command("https://example.test/x",
                            extractor_args="youtube:player_client=android_vr")
        self.assertEqual(cmd[-1], "https://example.test/x")
        self.assertEqual(cmd[cmd.index("--extractor-args") + 1],
                         "youtube:player_client=android_vr")


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
