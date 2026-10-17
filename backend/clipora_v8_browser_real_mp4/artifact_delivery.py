"""Pin an opened inode through FileResponse, retaining Starlette's Range support."""
import fcntl
import os
from pathlib import Path
import stat
from starlette.responses import FileResponse


def unlink_idle(path):
    """Never unlink an inode held by a download in this or another process."""
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return False
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = os.lstat(path)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            return False
        os.unlink(path)
        return True
    except FileNotFoundError:
        return True
    except (BlockingIOError, OSError):
        return False
    finally:
        if fd is not None:
            os.close(fd)


class PinnedVideoResponse(FileResponse):
    def __init__(self, path, max_size):
        self.fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or not 128 <= info.st_size <= max_size:
                raise ValueError('Invalid output artifact')
            fcntl.flock(self.fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            if b'ftyp' not in os.pread(self.fd, 16, 0):
                raise ValueError('Invalid MP4 signature')
            # Both Linux and macOS expose fd references. Reopening this path
            # refers to the pinned inode even if the original name disappears.
            prefix = '/proc/self/fd' if Path('/proc/self/fd').is_dir() else '/dev/fd'
            super().__init__(f'{prefix}/{self.fd}', stat_result=info,
                             media_type='video/mp4', filename='clipora-offline-worker-test.mp4',
                             headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    async def __call__(self, scope, receive, send):
        try:
            # Do not hand an fd pseudo-path to an external zero-copy extension.
            scope = {**scope, 'extensions': {k:v for k,v in scope.get('extensions', {}).items()
                                            if k != 'http.response.pathsend'}}
            await super().__call__(scope, receive, send)
        finally:
            self.close()
