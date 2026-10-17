import json
import math
import subprocess

from fastapi import HTTPException
from config import MAX_VIDEO_DURATION_SECONDS


def inspect_video_duration(path):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )

        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])

    except (
        subprocess.SubprocessError,
        OSError,
        KeyError,
        ValueError,
        TypeError,
    ):
        raise HTTPException(
            422, "Could not verify video duration"
        )

    if not math.isfinite(duration) or duration <= 0:
        raise HTTPException(422, "Invalid video duration")

    if duration > MAX_VIDEO_DURATION_SECONDS:
        raise HTTPException(
            413, "Video exceeds the 10-minute limit"
        )

    return duration
