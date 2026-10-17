"""Shared fixed-window admission limiter with bounded local SQLite state.

Client IPs are HMAC-keyed with a per-database secret, never stored verbatim.
No URL, filename, file content, or forwarded header is stored.
"""
from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import threading
import time


class LimitReached(Exception):
    def __init__(self, retry_after):self.retry_after = retry_after


class Limiter:
    def __init__(self, directory, per_client=20, total=120, period=60):
        if not (1 <= per_client <= total <= 1000 and 1 <= period <= 3600):
            raise ValueError('Invalid rate limits')
        self.directory = Path(directory)
        self.path = self.directory / 'admission.sqlite3'
        self.per_client, self.total, self.period = per_client, total, period
        self.initialized = False
        self.lock = threading.Lock()

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=.2, isolation_level=None)
        try:
            db.execute('PRAGMA busy_timeout=200')
            db.execute('PRAGMA max_page_count=256')
            yield db
        finally:db.close()

    def initialize(self):
        with self.lock:
            if self.initialized:return
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.directory.is_symlink():raise ValueError('State directory symlink rejected')
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            with self.connection() as db:
                db.execute('PRAGMA journal_mode=DELETE')
                if db.execute('PRAGMA page_size').fetchone()[0] != 4096:
                    raise ValueError('Unexpected SQLite page size')
                db.executescript('''
                    CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), secret BLOB NOT NULL);
                    CREATE TABLE IF NOT EXISTS windows (key TEXT PRIMARY KEY, bucket INTEGER NOT NULL, count INTEGER NOT NULL);
                ''')
                db.execute('INSERT OR IGNORE INTO meta VALUES(1,?)', (os.urandom(32),))
            self.initialized = True

    def admit(self, client, now=None):
        if not isinstance(client, str) or not 1 <= len(client) <= 128:
            raise ValueError('Missing client identity')
        self.initialize()
        now = time.time() if now is None else now
        bucket = int(now // self.period)
        retry = max(1, int((bucket + 1) * self.period - now) + 1)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                secret = db.execute('SELECT secret FROM meta WHERE id=1').fetchone()[0]
                key = hmac.new(secret, client.encode(), hashlib.sha256).hexdigest()
                db.execute('DELETE FROM windows WHERE bucket != ?', (bucket,))
                for identity, limit in (('global', self.total), (key, self.per_client)):
                    row = db.execute('SELECT count FROM windows WHERE key=?', (identity,)).fetchone()
                    if row and row[0] >= limit:
                        raise LimitReached(retry)
                if db.execute('SELECT count(*) FROM windows').fetchone()[0] > self.total:
                    raise LimitReached(retry)
                for identity in ('global', key):
                    db.execute('INSERT INTO windows VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET count=count+1', (identity,bucket))
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise
