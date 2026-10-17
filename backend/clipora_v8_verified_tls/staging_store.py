"""Atomic, application-enforced retention budget for verified offline artifacts.

This does not impose a host filesystem quota on unrelated processes.
"""
import fcntl
import os
from pathlib import Path
import re
import stat
import uuid

MAX_STAGING_BYTES = 64 * 1024 * 1024
MAX_STAGED_FILES = 32


def publish_artifact(source, staging, tag, *, limit=MAX_STAGING_BYTES, max_files=MAX_STAGED_FILES):
    if not re.fullmatch(r'[0-9a-f]{10}', tag):
        raise ValueError('Invalid artifact tag')
    staging = Path(staging)
    staging.mkdir(parents=True, exist_ok=True)
    if staging.is_symlink():
        raise ValueError('Staging symlink rejected')
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    lock_fd = None
    temporary = None
    try:
        info = os.fstat(source_fd)
        if not stat.S_ISREG(info.st_mode) or not 128 <= info.st_size <= limit:
            raise ValueError('Invalid artifact source')
        lock_fd = os.open(staging / '.publish.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        used = 0
        count = 0
        for path in staging.iterdir():
            if path.name == '.publish.lock':
                continue
            try:
                item = path.lstat()
            except FileNotFoundError:
                continue  # Concurrent TTL cleanup can only reduce usage.
            if not stat.S_ISREG(item.st_mode):
                raise ValueError('Non-regular staging entry rejected')
            used += item.st_size
            count += 1
        if used + info.st_size > limit or count >= max_files:
            raise ValueError('Offline staging budget exhausted')
        temporary = staging / ('.' + uuid.uuid4().hex + '.part')
        temp_fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        copied = 0
        with os.fdopen(temp_fd, 'wb') as output, os.fdopen(source_fd, 'rb', closefd=False) as input_file:
            while True:
                chunk = input_file.read(min(65536, info.st_size - copied + 1))
                if not chunk:
                    break
                copied += len(chunk)
                if copied > info.st_size:
                    raise ValueError('Artifact changed while publishing')
                output.write(chunk)
            if copied != info.st_size:
                raise ValueError('Artifact changed while publishing')
            output.flush()
            os.fsync(output.fileno())
        # Same-filesystem link is atomic and refuses to overwrite an existing file.
        os.link(temporary, staging / (tag + '.mp4'))
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        os.close(source_fd)
