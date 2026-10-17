"""Bounded, inode-lock-aware cleanup for the ownership API candidate."""
from pathlib import Path
import os
import re
from clipora_v8_browser_real_mp4.artifact_delivery import unlink_idle


def sweep(store,directory):
    root=Path(directory).absolute()
    if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('Artifact directory symlink rejected')
    removed=0
    with os.scandir(root) as entries:
        for count,entry in enumerate(entries,1):
            if count>256:raise RuntimeError('Artifact directory exceeds bounded inventory')
            if re.fullmatch('\\.[0-9a-f]{32}\\.[0-9a-f]{32}\\.tmp',entry.name):
                if unlink_idle(root/entry.name):removed+=1
                continue
            if not re.fullmatch('[0-9a-f]{32}\\.(mp4|zip)',entry.name):continue
            job_id=entry.name[:-4]
            with store.connection() as db:
                row=db.execute('SELECT j.status,o.expires_at,s.expires_at AS session_expiry FROM jobs j LEFT JOIN job_ownership o USING(job_id) LEFT JOIN browser_sessions s ON s.identity=o.identity WHERE j.job_id=?',(job_id,)).fetchone()
            if row is not None:
                if row['status']=='processing':continue
                if (row['status']=='completed' and row['expires_at'] is not None
                        and row['expires_at']>store.clock() and row['session_expiry']>store.clock()):continue
            if unlink_idle(root/entry.name):removed+=1
    return removed
