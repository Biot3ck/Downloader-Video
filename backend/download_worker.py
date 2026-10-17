# Clipora download worker — preparation only
# Not connected to FastAPI yet.

from pathlib import Path
import subprocess
import shutil

from yt_dlp import YoutubeDL

MAX_BYTES = 100 * 1024 * 1024

def ydl_options(download_dir=None):
    options = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "no_warnings": True,
        "socket_timeout": 20,
        "retries": 2,
        "extractor_retries": 2,
    }

    if download_dir:
        options.update({
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",
            "outtmpl": str(
                download_dir / "source.%(ext)s"
            ),
            "max_filesize": MAX_BYTES,
        })

    return options


def media_codecs(path):
    import json

    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries",
            "stream=codec_type,codec_name,pix_fmt",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )

    streams = json.loads(
        result.stdout
    ).get("streams", [])

    video = None
    audio = None
    pixel_format = None

    for stream in streams:
        codec_type = stream.get("codec_type")

        if codec_type == "video":
            video = stream.get("codec_name")
            pixel_format = stream.get("pix_fmt")

        elif codec_type == "audio":
            audio = stream.get("codec_name")

    return video, audio, pixel_format


def make_compatible(source, output):
    video, audio, pix = media_codecs(source)

    if not video:
        raise ValueError("Downloaded file has no video")

    if (
        source.suffix.lower() == ".mp4"
        and video == "h264"
        and pix == "yuv420p"
        and audio in (None, "aac")
    ):
        shutil.copy2(source, output)
        return

    command = [
        "ffmpeg", "-y",
        "-i", str(source),
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output),
    ]

    subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )

