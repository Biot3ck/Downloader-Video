"""Candidate ownership layer over the existing durable queue.

Not installed on public routes; no worker, network, or Docker access. The queue's
owner field remains an execution fence. Browser ownership is a separate table.
"""
from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import time
from uuid import uuid4

from clipora_v8_browser_real_mp4.job_store import JobStore, QueueFull
from .platforms import recognize


class OwnerRequired(PermissionError):pass
class IdempotencyConflict(ValueError):pass


class OwnedJobs(JobStore):
    def __init__(self,directory,*,clock=time.time,max_sessions=1024):
        if type(max_sessions) is not int or not 1<=max_sessions<=1024:raise ValueError('Invalid session limit')
        self.clock,self.max_sessions=clock,max_sessions
        # Refuse symlinked state ancestors as well as the database itself.
        path=Path(directory).absolute()/'owned-public'
        if any(p.is_symlink() for p in (path,*path.parents)):
            raise ValueError('Symlinked state path rejected')
        super().__init__(path,max_pending=4,max_records=256)
        self.directory.chmod(0o700);self.path.chmod(0o600)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS ownership_meta (
                    id INTEGER PRIMARY KEY CHECK(id=1), secret BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS browser_sessions (
                    identity TEXT PRIMARY KEY, expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_ownership (
                    job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),
                    identity TEXT NOT NULL REFERENCES browser_sessions(identity),
                    idempotency TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    url TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    UNIQUE(identity,idempotency)
                );
                CREATE TABLE IF NOT EXISTS job_cancellation (
                    job_id TEXT PRIMARY KEY REFERENCES jobs(job_id) ON DELETE CASCADE,
                    requested_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS owned_expiry ON job_ownership(expires_at);
            ''')
            db.execute('INSERT OR IGNORE INTO ownership_meta VALUES(1,?)',(secrets.token_bytes(32),))

    @contextmanager
    def connection(self):
        with super().connection() as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA max_page_count=1024')
            yield db

    def _identity(self,db,token):
        if type(token) is not str or re.fullmatch('[0-9a-f]{64}',token) is None:
            raise OwnerRequired('Valid session required')
        secret=db.execute('SELECT secret FROM ownership_meta WHERE id=1').fetchone()[0]
        return hmac.new(secret,token.encode('ascii'),hashlib.sha256).hexdigest()

    def _session(self,db,token,now):
        identity=self._identity(db,token)
        row=db.execute('SELECT expires_at FROM browser_sessions WHERE identity=?',(identity,)).fetchone()
        if row is None or row['expires_at']<=now:raise OwnerRequired('Valid session required')
        return identity

    def issue_session(self):
        token=secrets.token_hex(32);now=self.clock()
        with self.transaction() as db:
            self._prune(db,now)
            if db.execute('SELECT count(*) FROM browser_sessions').fetchone()[0]>=self.max_sessions:
                raise QueueFull('Session capacity reached')
            identity=self._identity(db,token)
            db.execute('INSERT INTO browser_sessions VALUES(?,?)',(identity,now+86400))
        return token

    def _prune(self,db,now):
        # Never delete a processing record: its resource owner must first stop
        # the runner and fence the completion before physical artifact cleanup.
        db.execute("UPDATE jobs SET status='failed',updated_at=?,message='Expired job' WHERE status='queued' AND job_id IN (SELECT job_id FROM job_ownership WHERE expires_at<=?)",(now,now))
        db.execute("DELETE FROM job_ownership WHERE expires_at<=? AND job_id IN (SELECT job_id FROM jobs WHERE status IN ('failed','completed'))",(now,))
        db.execute("DELETE FROM jobs WHERE status IN ('failed','completed') AND job_id NOT IN (SELECT job_id FROM job_ownership)")
        db.execute('DELETE FROM browser_sessions WHERE expires_at<=? AND identity NOT IN (SELECT identity FROM job_ownership)',(now,))

    def create(self):
        raise OwnerRequired('Use create_owned with a valid browser owner')

    def create_owned(self,token,url,idempotency):
        if type(idempotency) is not str or re.fullmatch('[0-9a-f]{32}',idempotency) is None:
            raise ValueError('Canonical idempotency key required')
        return self._submit(token,recognize(url).url,idempotency)

    def create_sample(self,token,idempotency):
        if type(idempotency) is not str or re.fullmatch('[0-9a-f]{32}',idempotency) is None:
            raise ValueError('Canonical idempotency key required')
        return self._submit(token,'clipora:offline-sample',idempotency)

    def session_valid(self,token):
        with self.connection() as db:
            try:self._session(db,token,self.clock())
            except OwnerRequired:return False
        return True

    def _submit(self,token,normalized,idempotency):
        digest=hashlib.sha256(normalized.encode()).hexdigest();now=self.clock()
        with self.transaction() as db:
            identity=self._session(db,token,now)
            self._prune(db,now)
            existing=db.execute('SELECT job_id,request_digest FROM job_ownership WHERE identity=? AND idempotency=?',
                                (identity,idempotency)).fetchone()
            if existing:
                if not hmac.compare_digest(existing['request_digest'],digest):
                    raise IdempotencyConflict('Idempotency key already used for another request')
                job_id=existing['job_id']
            else:
                pending=db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','processing')").fetchone()[0]
                total=db.execute('SELECT count(*) FROM jobs').fetchone()[0]
                own=db.execute("SELECT 1 FROM jobs j JOIN job_ownership o USING(job_id) WHERE o.identity=? AND j.status IN ('queued','processing')",(identity,)).fetchone()
                if own or pending>=self.max_pending or total>=self.max_records:raise QueueFull('Job capacity reached')
                job_id=uuid4().hex
                db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',
                    (job_id,uuid4().hex[:10],'queued',None,now,now,'Waiting for Worker'))
                db.execute('INSERT INTO job_ownership VALUES(?,?,?,?,?,?)',
                    (job_id,identity,idempotency,digest,normalized,now+3600))
        return self.get_owned(token,job_id)

    def get_owned(self,token,job_id):
        # Missing/foreign/expired identifiers share one result. Do not expose
        # worker messages, URLs, execution-owner fences, or filesystem paths.
        if type(job_id) is not str or re.fullmatch('[0-9a-f]{32}',job_id) is None:return None
        now=self.clock()
        with self.connection() as db:
            try:identity=self._session(db,token,now)
            except OwnerRequired:return None
            row=db.execute('SELECT j.job_id,j.status,j.created_at,j.updated_at,(c.job_id IS NOT NULL) AS cancel_requested FROM jobs j JOIN job_ownership o USING(job_id) LEFT JOIN job_cancellation c USING(job_id) WHERE j.job_id=? AND o.identity=? AND o.expires_at>?',
                           (job_id,identity,now)).fetchone()
        if row is None:return None
        result=dict(row);result['cancel_requested']=bool(result['cancel_requested'])
        return result

    def cancel_owned(self,token,job_id):
        now=self.clock()
        with self.transaction() as db:
            try:identity=self._session(db,token,now)
            except OwnerRequired:return False
            row=db.execute('SELECT j.status FROM jobs j JOIN job_ownership o USING(job_id) WHERE j.job_id=? AND o.identity=? AND o.expires_at>?',
                           (job_id,identity,now)).fetchone()
            if row is None:return False
            if row['status'] in ('queued','processing'):
                db.execute('INSERT OR IGNORE INTO job_cancellation VALUES(?,?)',(job_id,now))
            # A running request remains processing until the resource owner
            # confirms worker/exporter termination. Its queue slot stays held.
            if row['status']=='queued':
                db.execute("UPDATE jobs SET status='failed',updated_at=?,message='Cancelled by owner' WHERE job_id=?",(now,job_id))
            return True

    def payload_for_runner(self,job_id,execution_owner):
        with self.connection() as db:
            row=db.execute("SELECT o.url FROM jobs j JOIN job_ownership o USING(job_id) JOIN browser_sessions s ON s.identity=o.identity WHERE j.job_id=? AND j.owner=? AND j.status='processing' AND NOT EXISTS(SELECT 1 FROM job_cancellation c WHERE c.job_id=j.job_id) AND o.expires_at>? AND s.expires_at>?",
                (job_id,execution_owner,self.clock(),self.clock())).fetchone()
        return row['url'] if row else None

    def stop_required(self,job_id,execution_owner):
        # Stale owners and expired payloads must stop rather than publish.
        return self.payload_for_runner(job_id,execution_owner) is None

    def interrupted(self,job_id):
        raise RuntimeError('Owned jobs require fenced stop confirmation')

    def confirm_stopped(self,job_id,execution_owner):
        # Trusted runner only: call after stop/reap/cleanup is confirmed. Never
        # expose this method as an HTTP endpoint accepting user assertions.
        with self.transaction() as db:
            result=db.execute("UPDATE jobs SET status='failed',owner=NULL,updated_at=?,message='Worker stopped' WHERE job_id=? AND status='processing' AND owner=?",
                              (self.clock(),job_id,execution_owner))
        return result.rowcount==1

    def finish(self,job_id,owner,success,message):
        with self.transaction() as db:
            row=db.execute("SELECT j.job_id FROM jobs j JOIN job_ownership o USING(job_id) JOIN browser_sessions s ON s.identity=o.identity WHERE j.job_id=? AND j.owner=? AND j.status='processing' AND NOT EXISTS(SELECT 1 FROM job_cancellation c WHERE c.job_id=j.job_id)" +
                           (' AND o.expires_at>? AND s.expires_at>?' if success else ''),
                           (job_id,owner,self.clock(),self.clock()) if success else (job_id,owner)).fetchone()
            if row is None:return False
            db.execute("UPDATE jobs SET status=?,owner=NULL,updated_at=?,message=? WHERE job_id=?",
                       ('completed' if success else 'failed',self.clock(),message,job_id))
        return True

    def delete_expired(self,job_id,cutoff):
        # Base queue's one-table deletion must not leave orphan authorization.
        with self.transaction() as db:
            row=db.execute("SELECT 1 FROM jobs WHERE job_id=? AND status IN ('completed','failed') AND updated_at<?",(job_id,cutoff)).fetchone()
            if row:
                db.execute('DELETE FROM job_ownership WHERE job_id=?',(job_id,))
                db.execute('DELETE FROM jobs WHERE job_id=?',(job_id,))
