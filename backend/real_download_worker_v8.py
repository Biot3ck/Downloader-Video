from clipora_v8_worker_integration.worker_proxy import required_proxy_settings
from pathlib import Path
from uuid import uuid4
import os

from yt_dlp import YoutubeDL

from download_worker import (
    ydl_options,
    media_codecs,
    make_compatible,
)
from download_limits import validate_duration
from video_inspector import inspect_video_duration
from url_security import validate_video_url

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = Path(
    os.environ.get(
        "CLIPORA_TEST_DOWNLOAD_DIR",
        str(BASE_DIR / "downloads"),
    )
).resolve()
from config import MAX_FILE_SIZE_MB

MAX_BYTES = 5 * 1024 * 1024 * 1024

def v8_download_options(folder):
    options = ydl_options(folder)
    options["max_filesize"] = MAX_BYTES

    def check_size(progress):
        downloaded = progress.get("downloaded_bytes") or 0
        total = progress.get("total_bytes") or 0
        estimated = progress.get("total_bytes_estimate") or 0

        if max(downloaded, total, estimated) > MAX_BYTES:
            raise ValueError("Video exceeds 5 GB limit")

    options.setdefault("progress_hooks", []).append(check_size)
    return required_proxy_settings(options)


def process_video(url, job_id):
    import re

    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise ValueError("Invalid Job ID")

    platform = validate_video_url(url)

    with YoutubeDL(required_proxy_settings(ydl_options())) as ydl:
        metadata = ydl.extract_info(
            url.strip(),
            download=False,
        )

    validate_duration(
        metadata.get("duration") if metadata else None
    )

    folder = DOWNLOAD_DIR / job_id
    folder.mkdir(parents=True, exist_ok=False)

    try:
        with YoutubeDL(v8_download_options(folder)) as ydl:
            info = ydl.extract_info(
                url.strip(),
                download=True,
            )

        candidates = [
            p for p in folder.iterdir()
            if p.is_file()
            and p.suffix.lower() in (".mp4", ".webm", ".mkv")
            and p.name != "video.mp4"
        ]

        video_files = []

        for candidate in candidates:
            try:
                video_codec, audio_codec, pix = media_codecs(candidate)
                if video_codec:
                    video_files.append(candidate)
            except Exception:
                continue

        if not video_files:
            raise ValueError("No valid video found")

        source = max(video_files, key=lambda p: p.stat().st_size)

        if source.stat().st_size > MAX_BYTES:
            raise ValueError("Video exceeds size limit")

        output = folder / "video.mp4"
        make_compatible(source, output)

        if output.stat().st_size > MAX_BYTES:
            raise ValueError("Output exceeds size limit")

        inspect_video_duration(output)

        source.unlink(missing_ok=True)
        (folder / ".completed").touch()

        return {
            "success": True,
            "platform": platform,
            "title": info.get("title") or "Video",
            "file": "video.mp4",
            "download_url": f"/api/files/{job_id}/video.mp4",
        }

    except Exception:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        raise
