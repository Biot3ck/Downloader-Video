"""Reviewable ownership API candidate; not the running preview launcher.

Submission/download activation stays disabled. Jobs can only be populated by
trusted in-process code until a reviewed scheduler and egress gate are supplied.
"""
from pathlib import Path
import sqlite3
from fastapi import HTTPException,Request,Response
from clipora_v8_browser_real_mp4.artifact_delivery import PinnedVideoResponse
from clipora_v8_browser_real_mp4.job_store import QueueFull
from .main import create_app,validate_origin
from .owned_jobs import OwnedJobs
from .owned_artifacts import sweep


def create_owned_app(origin,state_dir,artifact_dir,*,offline_sample_enabled=False):
    secure=validate_origin(origin).scheme=='https'
    cookie='__Host-clipora-session' if secure else 'clipora_session'
    root=Path(artifact_dir).absolute()
    if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('Artifact directory symlink rejected')
    app=create_app(origin,state_dir,offline_sample_enabled=offline_sample_enabled)
    # Create/check state before either artifact or queue child directories.
    # Otherwise mkdir(parents=True) implicitly creates a 0755 state root.
    app.state.admission_limiter.initialize()
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    root.chmod(0o700)
    store=OwnedJobs(state_dir)
    # Testing/internal scheduler access; this is not an HTTP authorization path.
    app.state.owned_jobs=store

    def token(request):
        values=[]
        for header in request.headers.getlist('cookie'):
            for item in header.split(';'):
                key,separator,value=item.strip().partition('=')
                if key==cookie and separator:values.append(value)
        return values[0] if len(values)==1 else None

    app.state.owned_session_token=token

    def owned(request,job_id):
        try:job=store.get_owned(token(request),job_id)
        except (OSError,sqlite3.Error):raise HTTPException(503,'Job storage unavailable.') from None
        if job is None:raise HTTPException(404,'Job not found.')
        return job

    @app.post('/api/v8/session',status_code=204)
    def session(request:Request,response:Response):
        try:
            sweep(store,root)
            if store.session_valid(token(request)):return
            value=store.issue_session()
        except QueueFull:raise HTTPException(429,'Session capacity reached.') from None
        except (OSError,ValueError,RuntimeError,sqlite3.Error):raise HTTPException(503,'Session storage unavailable.') from None
        response.set_cookie(cookie,value,max_age=86400,path='/',secure=secure,httponly=True,samesite='strict')
        response.headers['Cache-Control']='no-store'

    @app.get('/api/v8/jobs/{job_id}')
    def status(job_id:str,request:Request):return owned(request,job_id)

    @app.post('/api/v8/jobs/{job_id}/cancel',status_code=204)
    def cancel(job_id:str,request:Request):
        owned(request,job_id)
        try:result=store.cancel_owned(token(request),job_id)
        except (OSError,sqlite3.Error):raise HTTPException(503,'Job storage unavailable.') from None
        if not result:raise HTTPException(404,'Job not found.')

    @app.api_route('/api/v8/jobs/{job_id}/file',methods=['GET','HEAD'])
    def download(job_id:str,request:Request):
        job=owned(request,job_id)
        if job['status']!='completed':raise HTTPException(404,'Job not found.')
        try:
            # Authorization is checked before touching the artifact path.
            response=PinnedVideoResponse(root/(job_id+'.mp4'),64*1024*1024)
            response.headers['Content-Disposition']='attachment; filename="clipora-video.mp4"'
            return response
        except (OSError,ValueError):raise HTTPException(404,'Job not found.') from None
    return app
