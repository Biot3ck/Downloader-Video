"""Atomic, fenced publication after a trusted runner confirms it is stopped."""
import fcntl
import os
from pathlib import Path
import re
import stat
from uuid import uuid4


class PublicationDenied(PermissionError):pass


def publish(store,job_id,execution_owner,source,directory):
    def validate(fd):
        if b'ftyp' not in os.pread(fd,16,0):raise PublicationDenied('Invalid MP4 signature')
    return publish_file(store,job_id,execution_owner,source,directory,
                        suffix='.mp4',minimum=128,maximum=64*1024*1024,validate=validate)


def publish_file(store,job_id,execution_owner,source,directory,*,suffix,minimum,maximum,validate,required_payload=None):
    # Internal runner interface only; no filename/validator comes from HTTP.
    if suffix not in ('.mp4','.zip') or not 1<=minimum<=maximum<=64*1024*1024:
        raise PublicationDenied('Invalid publication limits')
    if type(job_id) is not str or not re.fullmatch('[0-9a-f]{32}',job_id):raise PublicationDenied('Invalid job')
    root=Path(directory).absolute();source=Path(source).absolute()
    if any(p.is_symlink() for p in (root,*root.parents,source,*source.parents)):
        raise PublicationDenied('Symlinked publication path rejected')
    if store.stop_required(job_id,execution_owner):raise PublicationDenied('Job cannot publish')
    source_fd=temp_fd=directory_fd=None
    temp=root/('.'+job_id+'.'+uuid4().hex+'.tmp')
    destination=root/(job_id+suffix);linked=False
    try:
        source_fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        before=os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode) or not minimum<=before.st_size<=maximum:
            raise PublicationDenied('Invalid artifact size or type')
        directory_fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        temp_fd=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600)
        fcntl.flock(temp_fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
        copied=0
        while True:
            chunk=os.read(source_fd,65536)
            if not chunk:break
            copied+=len(chunk)
            if copied>before.st_size:raise PublicationDenied('Artifact changed during publication')
            view=memoryview(chunk)
            while view:
                written=os.write(temp_fd,view)
                if written<=0:raise OSError('Artifact copy made no progress')
                view=view[written:]
        after=os.fstat(source_fd)
        if copied!=before.st_size or (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise PublicationDenied('Artifact changed during publication')
        validate(temp_fd)
        os.fsync(temp_fd)
        with store.transaction() as db:
            sql="SELECT j.job_id FROM jobs j JOIN job_ownership o USING(job_id) JOIN browser_sessions s ON s.identity=o.identity WHERE j.job_id=? AND j.status='processing' AND j.owner=? AND o.expires_at>? AND s.expires_at>? AND NOT EXISTS(SELECT 1 FROM job_cancellation c WHERE c.job_id=j.job_id)"
            params=(job_id,execution_owner,store.clock(),store.clock())
            if required_payload is not None:
                sql+=' AND o.url=?';params+=(required_payload,)
            row=db.execute(sql,params).fetchone()
            if row is None:raise PublicationDenied('Job no longer authorized to publish')
            # Exclusive link avoids overwriting a previously published inode.
            os.link(temp,destination,follow_symlinks=False);linked=True
            os.fsync(directory_fd)
            db.execute("UPDATE jobs SET status='completed',owner=NULL,updated_at=?,message='Download ready' WHERE job_id=?",
                       (store.clock(),job_id))
        return destination
    except BaseException:
        if linked:
            # Only remove the inode this transaction installed, never a
            # replacement made by another actor after a filesystem failure.
            try:
                current=os.lstat(destination);mine=os.fstat(temp_fd)
                if (current.st_dev,current.st_ino)==(mine.st_dev,mine.st_ino):destination.unlink()
            except FileNotFoundError:pass
        raise
    finally:
        try:temp.unlink(missing_ok=True)
        finally:
            for fd in (source_fd,temp_fd,directory_fd):
                if fd is not None:os.close(fd)
