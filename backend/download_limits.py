from fastapi import HTTPException
from config import MAX_VIDEO_DURATION_SECONDS


def validate_duration(duration):
    if duration is None:
        return None

    try:
        seconds = float(duration)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail="Invalid video duration"
        )

    import math

    if not math.isfinite(seconds) or seconds <= 0:
        raise HTTPException(
            status_code=422,
            detail="Invalid video duration"
        )

    if seconds > MAX_VIDEO_DURATION_SECONDS:
        raise HTTPException(
            status_code=413,
            detail="Video exceeds the 10-minute limit"
        )

    return seconds
