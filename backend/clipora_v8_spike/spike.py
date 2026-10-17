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


def _size(value) -> int | None:
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return None


def _looks_watermarked(format_id: str, url: str) -> bool:
    haystack = f"{format_id} {url}".lower()
    return any(hint in haystack for hint in _WATERMARK_HINTS)


@dataclass
class Result:
    platform: str
    url: str
    ok: bool
    error: str = ""
    title: str = ""
    extractor: str = ""
    duration_s: float | None = None
    max_height: int | None = None
    size_bytes: int | None = None
    format_count: int = 0
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

    return {
        "title": (info.get("title") or "")[:120],
        "extractor": info.get("extractor_key") or info.get("extractor") or "",
        "duration_s": info.get("duration"),
        "max_height": max(heights) if heights else None,
        "size_bytes": max(sizes) if sizes else None,
        "format_count": len(formats),
        "clean_formats": clean,
        "watermark_formats": marked,
        "image_count": image_count,
        "is_slideshow": bool(entries) and info.get("extractor_key", "").lower().startswith("tiktok"),
        "raw_format_ids": ",".join(str(f.get("format_id") or "") for f in formats)[:400],
    }


def probe(url: str, timeout_s: int = 45) -> tuple[dict | None, str]:
    """Jalankan yt-dlp dan kembalikan (metadata, pesan galat). Tidak mengunduh media."""
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
        url,
    ]
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
    """Hitung success rate per platform. Platform tanpa data tidak dilaporkan."""
    summary: dict[str, dict] = {}
    for row in rows:
        platform = row.get("platform") or "unknown"
        bucket = summary.setdefault(platform, {"total": 0, "ok": 0, "errors": {}})
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
    tiktok = summary.get("tiktok", {}).get("rate", 0.0)
    others = [b["rate"] for name, b in summary.items() if name != "tiktok" and b["total"]]
    if tiktok < 70:
        return "STOP: TikTok di bawah 70% — tinjau ulang model produk (ROADMAP 4.3)."
    if others and max(others) < 50:
        return "SEMPITKAN: TikTok layak, platform lain lemah — fokus TikTok + satu platform."
    if tiktok >= 85 and (not others or max(others) >= 70):
        return "LANJUT: TikTok >=85% dan minimal satu platform lain >=70%."
    return "LANJUT BERSYARAT: angka belum memenuhi ambang penuh, lihat tabel."


def render_markdown(rows: list[dict], summary: dict[str, dict], source: str) -> str:
    lines = [f"# Hasil spike kelayakan — {source}", ""]
    lines.append("| Platform | Diuji | Berhasil | Success rate |")
    lines.append("| --- | ---: | ---: | ---: |")
    for platform, bucket in sorted(summary.items()):
        lines.append(f"| {platform} | {bucket['total']} | {bucket['ok']} | {bucket['rate']}% |")
    lines += ["", f"**Keputusan otomatis:** {verdict(summary)}", "", "## Kegagalan", ""]
    failures = [row for row in rows if not row.get("ok")]
    if not failures:
        lines.append("Tidak ada kegagalan.")
    else:
        lines.append("| Platform | Alasan |")
        lines.append("| --- | --- |")
        for row in failures[:40]:
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


def run(urls: list[str], recheck_ok: set[str] | None = None) -> list[dict]:
    import time

    rows: list[dict] = []
    for index, url in enumerate(urls, 1):
        platform = classify(url)
        if recheck_ok is not None and url not in recheck_ok:
            continue
        started = time.monotonic()
        info, error = probe(url)
        elapsed = round(time.monotonic() - started, 2)
        if info is None:
            result = Result(platform=platform, url=url, ok=False, error=error, elapsed_s=elapsed)
        else:
            result = Result(platform=platform, url=url, ok=True, elapsed_s=elapsed, **analyze(info))
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
    parser.add_argument("--urls", type=Path, required=True, help="berkas daftar URL")
    parser.add_argument("--out", type=Path, required=True, help="berkas CSV hasil")
    parser.add_argument("--recheck", type=Path, help="CSV sebelumnya; hanya URL yang berhasil diuji ulang")
    args = parser.parse_args(argv)

    if not args.urls.is_file():
        print(f"berkas tidak ditemukan: {args.urls}", file=sys.stderr)
        return 1
    urls = read_urls(args.urls)
    if not urls:
        print("tidak ada URL di berkas masukan", file=sys.stderr)
        return 1

    recheck_ok = read_ok_urls(args.recheck) if args.recheck else None
    rows = run(urls, recheck_ok)
    write_csv(rows, args.out)

    summary = success_rate(rows)
    markdown = render_markdown(rows, summary, args.out.name)
    report = args.out.with_suffix(".md")
    report.write_text(markdown, encoding="utf-8")

    print()
    print(markdown)
    print(f"CSV: {args.out}\nLaporan: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
