# Clipora v8 — Actual Worker, offline guarded E2E

Run from the existing `~/Desktop/clipora/backend` folder: `python3 clipora_v8_real_guarded_e2e/run_test.py`.

Exercises real `real_download_worker_v8.process_video()` with actual yt-dlp, ffprobe/ffmpeg, existing proxy settings, and a tiny local HTTPS MP4 fixture reached through two internal Docker networks and gateway/egress. Requires the project's existing modules and `clipora-worker:v8-dns`, `clipora-gateway:v8-test` images.

Safety boundaries: test-only monkeypatch permits exactly `https://example.com/video.mp4` and disables trust verification **for a synthetic certificate only**, without altering the production worker. Not a public HTTPS, SSRF, or hard disk quota test. Maximum local fixture workspace is 64 MiB (polled); timeout 90s; cleanup on failure; not a 5 GiB capacity test. No existing containers or v7 files are modified. Check the code before executing.
