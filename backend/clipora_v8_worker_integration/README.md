# Clipora v8 worker integration (staging only)

This installer creates `real_download_worker_v8.py` alongside the original `real_download_worker.py` with required proxy settings on both metadata and file-download yt-dlp passes. It **does not change the original worker, worker_entry, FastAPI, or active Docker containers**. No public network is enabled. No v8 entrypoint is activated yet.

Run from `~/Desktop/clipora/backend` after extracting the ZIP:

```
python3 -m unittest discover -s clipora_v8_worker_integration/tests -v && python3 clipora_v8_worker_integration/install_v8_worker.py
```

`CLIPORA_V8_PROXY_URL` must be a valid `http://<host>:8888` endpoint at runtime; missing or invalid proxy stops processing. This is a *code-level requirement*, **not** protection against egress bypass if a container has unrestricted network access. Actual worker Docker network restrictions, SSRF, redirects, yt-dlp plugin behavior, ffmpeg networking, TLS and resource limits must be validated before public use. `real_download_worker_v8.py` has not been integrated into worker_entry or Docker. Do not run real public downloads yet.
