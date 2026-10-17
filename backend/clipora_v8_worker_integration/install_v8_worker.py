"""Install an opt-in v8-only copy of real_download_worker; never patch v7."""
from pathlib import Path
import argparse
import hashlib
import sys

PREFACE = 'from clipora_v8_worker_integration.worker_proxy import required_proxy_settings\n'
OLD_META = 'with YoutubeDL(ydl_options()) as ydl:'
OLD_DOWNLOAD = 'with YoutubeDL(ydl_options(folder)) as ydl:'
NEW_META = 'with YoutubeDL(required_proxy_settings(ydl_options())) as ydl:'
NEW_DOWNLOAD = 'with YoutubeDL(required_proxy_settings(ydl_options(folder))) as ydl:'


def patched(source: str) -> str:
    if source.count(OLD_META) != 1 or source.count(OLD_DOWNLOAD) != 1:
        raise ValueError('Expected exactly two original yt-dlp calls; no changes made')
    if 'nocheckcertificate' in source or 'ignoreerrors' in source:
        raise ValueError('Unexpected worker security options; refusing patch')
    return PREFACE + source.replace(OLD_META, NEW_META, 1).replace(OLD_DOWNLOAD, NEW_DOWNLOAD, 1)


def install(backend: Path) -> str:
    backend = backend.resolve()
    src = backend / 'real_download_worker.py'
    dest = backend / 'real_download_worker_v8.py'
    if not src.is_file():
        raise FileNotFoundError(str(src))
    data = patched(src.read_text())
    if dest.exists():
        if dest.read_text() == data:
            return 'V8 WORKER ALREADY INSTALLED; V7 UNCHANGED'
        raise FileExistsError('v8 output differs; refusing overwrite: ' + str(dest))
    dest.write_text(data)
    if src.read_text() != data.removeprefix(PREFACE).replace(NEW_META, OLD_META, 1).replace(NEW_DOWNLOAD, OLD_DOWNLOAD, 1):
        dest.unlink()
        raise RuntimeError('source integrity check failed')
    return 'V8 WORKER COPY INSTALLED; V7 UNCHANGED'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', type=Path, default=Path.cwd())
    a = parser.parse_args()
    print(install(a.backend))

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('V8 INSTALL ABORTED:', exc, file=sys.stderr)
        sys.exit(1)
