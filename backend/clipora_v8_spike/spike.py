"""Spike kelayakan platform (Fase 0.5).

Alat operasional offline: menguji sekumpulan URL publik dengan yt-dlp dan mencatat
hasilnya apa adanya. Tidak pernah diimpor oleh aplikasi web, dan tidak dijalankan
saat tes otomatis (semua tes di sini hanya menguji fungsi murni).

Contoh pemakaian:

    python -B -m clipora_v8_spike.spike --urls clipora_v8_spike/urls.txt --out hasil.csv

    # uji ulang 24 jam kemudian, hanya URL yang sebelumnya berhasil
    python -B -m clipora_v8_spike.spike --urls clipora_v8_spike/urls.txt \
        --out hasil-24jam.csv --recheck hasil.csv

Keluar dengan kode 0 bila tidak ada kegagalan fatal, 1 bila berkas masukan salah.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

PLATFORMS = ("tiktok", "instagram", "pinterest", "youtube")

_PATTERNS = (
    ("tiktok", re.compile(r"(?:^|\.)(?:tiktok\.com|douyin\.com)$", re.I)),
    ("instagram", re.compile(r"(?:^|\.)(?:instagram\.com|instagr\.am)$", re.I)),
    ("pinterest", re.compile(r"(?:^|\.)(?:pinterest\.[a-z.]+|pin\.it)$", re.I)),
    ("youtube", re.compile(r"(?:^|\.)(?:youtube\.com|youtu\.be|youtube-nocookie\.com)$", re.I)),
)

# Format TikTok yang biasanya membawa watermark. Hanya petunjuk, bukan kepastian:
# nama format bisa berubah antar versi API platform.
_WATERMARK_HINTS = ("download", "watermark")

# Pesan yt-dlp yang berarti URL-nya sendiri tidak bisa diuji (post dihapus, privat,
# atau salah ketik). Baris seperti ini TIDAK boleh dihitung sebagai kegagalan
# ekstraksi: kalau dihitung, success rate turun palsu dan bisa memicu vonis STOP.
_INVALID_HINTS = (
    "video unavailable",
    "this video is unavailable",
    "has been removed",
    "no longer available",
    "does not exist",
    "not available",
    "404",
    "410",
    "gone",
    "private",
    "requested content is not available",
    "unable to find",
)
# Sengaja TIDAK masuk daftar di atas:
#   - "Unsupported URL"      → yt-dlp tidak punya extractor untuk bentuk URL itu
#                              (mis. TikTok /photo/). Itu keterbatasan produk, bukan URL mati.
#   - "No video formats found" → post hidup tetapi hanya berisi gambar; pipeline kita
#                              belum bisa mengambilnya. Juga kegagalan, bukan URL mati.

# Jumlah minimum URL valid sebelum success rate dianggap cukup untuk keputusan.
MIN_SAMPLE = 10

# Target URL per platform yang diminta berkas urls.txt.
TARGET_PER_PLATFORM = 20


def public_ip(timeout_s: int = 6) -> str:
    """IP publik keluar. Dicatat supaya hasil spike bisa diatribusikan ke IP tertentu."""
    import urllib.request

    for endpoint in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(endpoint, timeout=timeout_s) as response:
                value = response.read(64).decode("ascii", "replace").strip()
            if value:
                return value
        except Exception:
            continue
    return "unknown"


def egress_warning(ip: str) -> str:
    """Ingatkan bila hasil diukur dari IP yang salah jenisnya."""
    if ip == "unknown":
        return "IP keluar tidak terdeteksi — hasil tidak bisa diatribusikan. Periksa jaringan."
    if ip.startswith(("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2",
                      "172.30.", "172.31.", "127.", "169.254.")):
        return "IP keluar privat — tidak ada akses internet. Hasil tidak sah."
    return ""


def classify(url: str) -> str:
    """Kembalikan nama platform dari sebuah URL, atau 'unknown'."""
    match = re.match(r"^https?://([^/:?#]+)", url.strip(), re.I)
    if not match:
        return "unknown"
    host = match.group(1).lower().split("@")[-1]
    for platform, pattern in _PATTERNS:
        if pattern.search(host):
            return platform
    return "unknown"


def read_urls(path: Path) -> list[str]:
    """Baca daftar URL: satu per baris, `#` sebagai komentar, duplikat dibuang."""
    seen: set[str] = set()
    urls: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line in seen:
            continue
        seen.add(line)
        urls.append(line)
    return urls


def audit(urls: list[str]) -> dict:
    """Periksa komposisi daftar URL sebelum jaringan dipakai.

    Spike yang dijalankan dengan tiga URL TikTok akan menghasilkan angka yang
    terlihat pasti padahal tidak berarti. Fungsi ini melaporkan kekurangan itu
    di awal, bukan setelah 20 menit menunggu.
    """
    counts = {platform: 0 for platform in PLATFORMS}
    unknown: list[str] = []
    for url in urls:
        platform = classify(url)
        if platform in counts:
            counts[platform] += 1
        else:
            unknown.append(url)
    warnings = [
        f"{platform}: {counts[platform]} URL (target {TARGET_PER_PLATFORM})"
        for platform in PLATFORMS
        if counts[platform] < TARGET_PER_PLATFORM
    ]
    if unknown:
        warnings.append(f"{len(unknown)} URL tidak dikenali platformnya")
    return {"counts": counts, "unknown": unknown, "warnings": warnings}


def _size(value) -> int | None:
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return None


def _looks_watermarked(format_id: str, url: str) -> bool:
    haystack = f"{format_id} {url}".lower()
    return any(hint in haystack for hint in _WATERMARK_HINTS)


def image_only(error: str) -> bool:
    """Apakah kegagalan ini karena post-nya hanya berisi gambar?

    Pesannya spesifik per platform, bukan tebakan: Instagram "There is no video in
    this post", Pinterest "No video formats found!", dan TikTok menolak URL /photo/
    karena extractornya hanya menerima /video/. Post seperti ini tidak mengukur
    kemampuan ekstraksi video, jadi dipisahkan — bukan dihitung gagal, bukan juga
    dihitung berhasil.
    """
    haystack = (error or "").lower()
    if "there is no video in this post" in haystack or "no video formats found" in haystack:
        return True
    return "unsupported url" in haystack and "/photo/" in haystack


def error_kind(error: str) -> str:
    """Pisahkan URL yang tidak bisa diuji dari kegagalan ekstraksi sungguhan."""
    if image_only(error):
        return "image"
    haystack = (error or "").lower()
    return "invalid" if any(hint in haystack for hint in _INVALID_HINTS) else "extraction"


def no_media_reason(video_formats: int, image_count: int) -> str:
    """Alasan baris tetap dianggap gagal meski metadata berhasil dibaca.

    Ekstraksi yang hanya menghasilkan audio (mis. post foto TikTok lewat extractor
    video) bukan keberhasilan bagi produk yang mengunduh video atau gambar.
    """
    if video_formats > 0 or image_count > 0:
        return ""
    return "tidak ada format video/gambar yang bisa diunduh (mungkin hanya audio)"


@dataclass
class Result:
    platform: str
    url: str
    ok: bool
    error: str = ""
    error_kind: str = ""
    title: str = ""
    extractor: str = ""
    duration_s: float | None = None
    max_height: int | None = None
    size_bytes: int | None = None
    format_count: int = 0
    video_formats: int = 0
    clean_formats: int = 0
    watermark_formats: int = 0
    image_count: int = 0
    is_slideshow: bool = False
    raw_format_ids: str = ""
    elapsed_s: float = 0.0
    fields: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        row = asdict(self)
        row.pop("fields", None)
        return row


def analyze(info: dict) -> dict:
    """Ringkas metadata yt-dlp menjadi angka yang dibutuhkan keputusan Fase 0.5."""
    formats = info.get("formats") or []
    entries = info.get("entries") or []
    if not formats and entries:
        # Post carousel/slideshow: tiap entri adalah satu gambar atau video.
        formats = [f for entry in entries if isinstance(entry, dict) for f in (entry.get("formats") or [])]
        info = {**info, "entries": entries}

    heights = [f.get("height") for f in formats if isinstance(f.get("height"), int)]
    sizes = [s for f in formats if (s := _size(f.get("filesize") or f.get("filesize_approx")))]

    clean = 0
    marked = 0
    for fmt in formats:
        fmt_id = str(fmt.get("format_id") or "")
        if _looks_watermarked(fmt_id, str(fmt.get("url") or "")):
            marked += 1
        else:
            clean += 1

    image_count = sum(1 for entry in entries if isinstance(entry, dict) and entry.get("ext") in {"jpg", "jpeg", "png", "webp"})

    # Format audio saja (vcodec "none") tidak berguna bagi produk yang mengunduh
    # video atau gambar. Tanpa hitungan terpisah, post foto TikTok yang hanya
    # menghasilkan audio akan tampak "berhasil".
    video_formats = sum(1 for f in formats if str(f.get("vcodec") or "").lower() != "none")

    return {
        "title": (info.get("title") or "")[:120],
        "extractor": info.get("extractor_key") or info.get("extractor") or "",
        "duration_s": info.get("duration"),
        "max_height": max(heights) if heights else None,
        "size_bytes": max(sizes) if sizes else None,
        "format_count": len(formats),
        "video_formats": video_formats,
        "clean_formats": clean,
        "watermark_formats": marked,
        "image_count": image_count,
        "is_slideshow": bool(entries) and info.get("extractor_key", "").lower().startswith("tiktok"),
        "raw_format_ids": ",".join(str(f.get("format_id") or "") for f in formats)[:400],
    }


def probe_command(url: str, impersonate: str | None = None,
                  cookies: Path | None = None,
                  extractor_args: str | None = None) -> list[str]:
    """Susun perintah yt-dlp untuk satu URL.

    `--impersonate` meniru fingerprint TLS browser. Ini penting untuk TikTok:
    tanpa itu, permintaan dari IP datacenter dijawab halaman anti-bot dan
    yt-dlp melaporkan "Unexpected response from webpage request".
    """
    cmd = [
        sys.executable,
        "-B",
        "-m",
        "yt_dlp",
        "--dump-single-json",
        "--no-warnings",
        "--no-playlist",
        "--retries",
        "1",
        "--socket-timeout",
        "20",
    ]
    if impersonate:
        cmd += ["--impersonate", impersonate]
    if cookies:
        cmd += ["--cookies", str(cookies)]
    if extractor_args:
        cmd += ["--extractor-args", extractor_args]
    cmd.append(url)
    return cmd


def probe(url: str, timeout_s: int = 45, impersonate: str | None = None,
          cookies: Path | None = None,
          extractor_args: str | None = None) -> tuple[dict | None, str]:
    """Jalankan yt-dlp dan kembalikan (metadata, pesan galat). Tidak mengunduh media."""
    cmd = probe_command(url, impersonate=impersonate, cookies=cookies,
                        extractor_args=extractor_args)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return None, f"timeout>{timeout_s}s"
    if proc.returncode != 0:
        return None, _short_error(proc.stderr or proc.stdout)
    try:
        return json.loads(proc.stdout), ""
    except json.JSONDecodeError:
        return None, "json tidak valid"


def _short_error(text: str) -> str:
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("ERROR:"):
            return line[:180]
    tail = text.strip().splitlines()
    return (tail[-1][:180] if tail else "gagal tanpa pesan")


def success_rate(rows: list[dict]) -> dict[str, dict]:
    """Hitung success rate ekstraksi VIDEO per platform.

    Dua jenis baris dikeluarkan dari penyebut:
      - `invalid`: URL mati/privat — tidak mengukur kemampuan ekstraksi.
      - `image`:  post hanya berisi gambar — kemampuan lain, diukur terpisah.
    Keduanya dilaporkan supaya tidak hilang diam-diam.
    """
    summary: dict[str, dict] = {}
    for row in rows:
        platform = row.get("platform") or "unknown"
        bucket = summary.setdefault(
            platform, {"total": 0, "ok": 0, "errors": {}, "skipped": 0, "image_only": 0})
        kind = row.get("error_kind")
        if kind == "invalid":
            bucket["skipped"] += 1
            continue
        if kind == "image":
            bucket["image_only"] += 1
            continue
        bucket["total"] += 1
        if row.get("ok"):
            bucket["ok"] += 1
        else:
            reason = (row.get("error") or "tanpa alasan")[:60]
            bucket["errors"][reason] = bucket["errors"].get(reason, 0) + 1
    for bucket in summary.values():
        bucket["rate"] = round(bucket["ok"] / bucket["total"] * 100, 1) if bucket["total"] else 0.0
    return summary


def verdict(summary: dict[str, dict]) -> str:
    """Terapkan kriteria berhenti dari ROADMAP bagian 4.3."""
    if "tiktok" not in summary or not summary["tiktok"]["total"]:
        return "TIDAK ADA DATA TIKTOK: isi URL TikTok dulu — keputusan Fase 0.5 bergantung padanya."
    if summary["tiktok"]["total"] < MIN_SAMPLE:
        return (f"DATA KURANG: hanya {summary['tiktok']['total']} URL TikTok yang valid "
                f"(minimum {MIN_SAMPLE}). Tambah URL, jangan ambil keputusan dari sampel sekecil ini.")
    tiktok = summary["tiktok"]["rate"]
    others = [b["rate"] for name, b in summary.items() if name != "tiktok" and b["total"]]
    if tiktok < 70:
        return "STOP: TikTok di bawah 70% — tinjau ulang model produk (ROADMAP 4.3)."
    if others and max(others) < 50:
        return "SEMPITKAN: TikTok layak, platform lain lemah — fokus TikTok + satu platform."
    if tiktok >= 85 and (not others or max(others) >= 70):
        return "LANJUT: TikTok >=85% dan minimal satu platform lain >=70%."
    return "LANJUT BERSYARAT: angka belum memenuhi ambang penuh, lihat tabel."


def render_markdown(rows: list[dict], summary: dict[str, dict], source: str,
                    egress: str = "unknown", mode: str = "",
                    decision: str | None = None) -> str:
    lines = [f"# Hasil spike kelayakan — {source}", ""]
    lines.append(f"**IP keluar:** `{egress}`")
    if mode:
        lines.append(f"**Mode yt-dlp:** {mode}")
    warning = egress_warning(egress)
    if warning:
        lines += ["", f"> **PERINGATAN:** {warning}"]
    lines.append("")
    lines.append("| Platform | Diuji | Berhasil | Success rate |")
    lines.append("| --- | ---: | ---: | ---: |")
    for platform, bucket in sorted(summary.items()):
        lines.append(f"| {platform} | {bucket['total']} | {bucket['ok']} | {bucket['rate']}% |")
    skipped = {name: bucket.get("skipped", 0) for name, bucket in summary.items() if bucket.get("skipped")}
    if skipped:
        detail = ", ".join(f"{name} {count}" for name, count in sorted(skipped.items()))
        lines += ["", f"**URL mati/privat, tidak dihitung:** {detail}"]
    image_only_counts = {name: bucket.get("image_only", 0) for name, bucket in summary.items()
                         if bucket.get("image_only")}
    if image_only_counts:
        detail = ", ".join(f"{name} {count}" for name, count in sorted(image_only_counts.items()))
        lines += ["", f"**Post hanya gambar (diukur terpisah, bukan kegagalan video):** {detail}"]
    lines += ["", f"**Keputusan otomatis:** {decision or verdict(summary)}", "", "## Kegagalan", ""]
    invalid = [row for row in rows if row.get("error_kind") == "invalid"]
    images = [row for row in rows if row.get("error_kind") == "image"]
    failures = [row for row in rows
                if not row.get("ok") and row.get("error_kind") not in {"invalid", "image"}]
    if not failures:
        lines.append("Tidak ada kegagalan ekstraksi video.")
    else:
        lines.append("| Platform | Alasan |")
        lines.append("| --- | --- |")
        for row in failures[:40]:
            lines.append(f"| {row.get('platform')} | `{(row.get('error') or '')[:90]}` |")
    if images:
        lines += ["", "## Post hanya gambar", "",
                  "Post ini hidup dan publik, tetapi tidak berisi video. Pipeline saat ini",
                  "belum bisa mengambil gambarnya — itu pekerjaan terpisah, bukan angka di atas.",
                  "", "| Platform | Alasan |", "| --- | --- |"]
        for row in images[:40]:
            lines.append(f"| {row.get('platform')} | `{(row.get('error') or '')[:90]}` |")
    if invalid:
        lines += ["", "## URL tidak bisa diuji (mati, dihapus, atau privat)", "",
                  "URL ini tidak dihitung dalam success rate. Ganti dengan URL publik lain.", "",
                  "| Platform | Alasan |", "| --- | --- |"]
        for row in invalid[:40]:
            lines.append(f"| {row.get('platform')} | `{(row.get('error') or '')[:90]}` |")
    lines += ["", "## Rincian", ""]
    lines.append("| Platform | Tinggi maks | Ukuran | Format bersih | Format watermark | Slideshow |")
    lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
    for row in rows:
        if not row.get("ok"):
            continue
        height = row.get("max_height") or "-"
        size = row.get("size_bytes")
        size_text = f"{size / 1_048_576:.1f} MB" if size else "-"
        lines.append(
            f"| {row.get('platform')} | {height} | {size_text} | "
            f"{row.get('clean_formats', 0)} | {row.get('watermark_formats', 0)} | "
            f"{'ya' if row.get('is_slideshow') else '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


def run(urls: list[str], recheck_ok: set[str] | None = None,
        impersonate: str | None = None, cookies: Path | None = None,
        extractor_args: str | None = None) -> list[dict]:
    import time

    rows: list[dict] = []
    for index, url in enumerate(urls, 1):
        platform = classify(url)
        if recheck_ok is not None and url not in recheck_ok:
            continue
        if platform == "unknown":
            # Jangan buang waktu jaringan untuk situs yang tidak dinilai.
            rows.append(Result(platform=platform, url=url, ok=False,
                               error="platform tidak dikenali", error_kind="invalid").as_row())
            print(f"[{index}/{len(urls)}] {platform:10} LEWAT {url[:70]}", flush=True)
            continue
        started = time.monotonic()
        info, error = probe(url, impersonate=impersonate, cookies=cookies,
                            extractor_args=extractor_args)
        elapsed = round(time.monotonic() - started, 2)
        if info is None:
            result = Result(platform=platform, url=url, ok=False, error=error,
                            error_kind=error_kind(error), elapsed_s=elapsed)
        else:
            result = Result(platform=platform, url=url, ok=True, elapsed_s=elapsed, **analyze(info))
            reason = no_media_reason(result.video_formats, result.image_count)
            if reason:
                result.ok = False
                result.error = reason
                result.error_kind = "extraction"
        rows.append(result.as_row())
        status = "ok" if result.ok else "GAGAL"
        print(f"[{index}/{len(urls)}] {platform:10} {status:5} {elapsed:6.2f}s  {url[:70]}", flush=True)
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(Result(platform="", url="", ok=False).as_row().keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def read_ok_urls(path: Path) -> set[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["url"] for row in csv.DictReader(handle) if row.get("ok") == "True"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Spike kelayakan platform (Fase 0.5)")
    parser.add_argument("--urls", type=Path, help="berkas daftar URL")
    parser.add_argument("--out", type=Path, help="berkas CSV hasil")
    parser.add_argument("--recheck", type=Path, help="CSV sebelumnya; hanya URL yang berhasil diuji ulang")
    parser.add_argument("--impersonate", metavar="TARGET",
                        help="tiru fingerprint TLS browser, mis. 'chrome' (butuh curl_cffi). "
                             "Wajib dicoba bila platform menolak IP datacenter.")
    parser.add_argument("--cookies", type=Path, help="berkas cookies Netscape untuk yt-dlp")
    parser.add_argument("--extractor-args", metavar="KEY:VALUE",
                        help="teruskan ke yt-dlp, mis. 'youtube:player_client=android_vr'")
    parser.add_argument("--platform", choices=PLATFORMS,
                        help="hanya uji satu platform (mempercepat eksperimen)")
    parser.add_argument("--egress-only", action="store_true", help="hanya laporkan IP keluar lalu keluar")
    parser.add_argument("--audit-only", action="store_true",
                        help="periksa komposisi --urls tanpa akses jaringan")
    args = parser.parse_args(argv)

    if args.egress_only:
        ip = public_ip()
        print(ip)
        warning = egress_warning(ip)
        if warning:
            print(warning, file=sys.stderr)
            return 2
        return 0

    if not args.urls or (not args.out and not args.audit_only):
        parser.error("--urls dan --out wajib kecuali dengan --egress-only atau --audit-only")

    if not args.urls.is_file():
        print(f"berkas tidak ditemukan: {args.urls}", file=sys.stderr)
        return 1
    urls = read_urls(args.urls)
    if not urls:
        print("tidak ada URL di berkas masukan", file=sys.stderr)
        return 1

    composition = audit(urls)
    print("URL terbaca: " + ", ".join(f"{name} {count}" for name, count in composition["counts"].items()))
    for warning in composition["warnings"]:
        print(f"PERINGATAN: {warning}", file=sys.stderr)
    for url in composition["unknown"][:5]:
        print(f"PERINGATAN: platform tidak dikenali: {url}", file=sys.stderr)

    if args.audit_only:
        return 0 if not composition["warnings"] else 2

    if args.platform:
        urls = [url for url in urls if classify(url) == args.platform]
        if not urls:
            print(f"tidak ada URL untuk platform {args.platform}", file=sys.stderr)
            return 1

    egress = public_ip()
    warning = egress_warning(egress)
    print(f"IP keluar: {egress}")
    if warning:
        print(f"PERINGATAN: {warning}", file=sys.stderr)

    recheck_ok = read_ok_urls(args.recheck) if args.recheck else None
    if args.cookies and not args.cookies.is_file():
        print(f"berkas cookies tidak ditemukan: {args.cookies}", file=sys.stderr)
        return 1
    mode = "default"
    if args.impersonate:
        mode = f"`--impersonate {args.impersonate}`"
    if args.cookies:
        mode += " + cookies"
    if args.extractor_args:
        mode += f" + `--extractor-args {args.extractor_args}`"
    if args.platform:
        mode += f" + hanya {args.platform}"
    print(f"Mode yt-dlp: {mode}")
    rows = run(urls, recheck_ok, impersonate=args.impersonate, cookies=args.cookies,
               extractor_args=args.extractor_args)
    write_csv(rows, args.out)

    summary = success_rate(rows)
    decision = None
    if args.platform and args.platform != "tiktok":
        decision = (f"Eksperimen satu platform ({args.platform}) — bukan keputusan Fase 0.5; "
                    "keputusan tetap diukur dari TikTok.")
    markdown = render_markdown(rows, summary, args.out.name, egress, mode, decision)
    report = args.out.with_suffix(".md")
    report.write_text(markdown, encoding="utf-8")

    print()
    print(markdown)
    print(f"CSV: {args.out}\nLaporan: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
