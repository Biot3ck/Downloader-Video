"""Small durable offline queue. SQLite transactions enforce a shared admission limit."""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4


class QueueFull(Exception):
    pass


class JobStore:
    def __init__(self, directory, max_pending=4, max_records=256):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.directory.is_symlink():
            raise ValueError('Job directory symlink rejected')
        self.path = self.directory / 'jobs.sqlite3'
        self.max_pending = max_pending
        self.max_records = max_records
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    tag TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK(status IN ('queued','processing','completed','failed')),
                    owner TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    message TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status,created_at);
            ''')

    def _configure_connection(self, db):
        """Hook for subclasses that need extra per-connection pragmas."""

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=5000')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA wal_autocheckpoint=100')
        self._configure_connection(db)
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise

    def _admit(self, db, now, message, limit_message):
        """Single admission path so capacity rules cannot drift between stores."""
        pending = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','processing')").fetchone()[0]
        total = db.execute('SELECT count(*) FROM jobs').fetchone()[0]
        if pending >= self.max_pending or total >= self.max_records:
            raise QueueFull(limit_message)
        job_id, tag = uuid4().hex, uuid4().hex[:10]
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',
                   (job_id, tag, 'queued', None, now, now, message))
        return job_id

    def create(self):
        with self.transaction() as db:
            job_id = self._admit(db, time.time(), 'Waiting for isolated Worker',
                                 'Offline queue or retained job limit reached')
        return self.get(job_id)

    def get(self, job_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone()
        return dict(row) if row else None

    def list(self, status=None):
        with self.connection() as db:
            rows = db.execute('SELECT * FROM jobs' + (' WHERE status=?' if status else '') + ' ORDER BY created_at,job_id',
                              (status,) if status else ()).fetchall()
        return [dict(row) for row in rows]

    def claim(self, owner):
        # Caller must also hold the global runner flock for the entire job.
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM jobs WHERE status='processing'").fetchone():
                return None
            row = db.execute("SELECT job_id FROM jobs WHERE status='queued' ORDER BY created_at,job_id LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET status='processing',owner=?,updated_at=?,message=? WHERE job_id=? AND status='queued'",
                       (owner, time.time(), 'Docker Worker is processing offline MP4', row['job_id']))
        return self.get(row['job_id'])

    def finish(self, job_id, owner, success, message):
        with self.transaction() as db:
            result = db.execute("UPDATE jobs SET status=?,owner=NULL,updated_at=?,message=? WHERE job_id=? AND status='processing' AND owner=?",
                                ('completed' if success else 'failed', time.time(), message, job_id, owner))
        return result.rowcount == 1

    def interrupted(self, job_id):
        with self.transaction() as db:
            db.execute("UPDATE jobs SET status='failed',owner=NULL,updated_at=?,message=? WHERE job_id=? AND status='processing'",
                       (time.time(), 'Job interrupted by restart; isolated resources cleaned. Generate a new sample.', job_id))

    def delete_expired(self, job_id, cutoff):
        with self.transaction() as db:
            db.execute("DELETE FROM jobs WHERE job_id=? AND status IN ('completed','failed') AND updated_at<?", (job_id, cutoff))
