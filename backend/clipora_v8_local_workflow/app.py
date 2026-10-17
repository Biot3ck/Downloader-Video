"""Explicit loopback-only product workflow for the fixed offline sample."""
from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3
from fastapi import HTTPException,Request
from clipora_v8_web.main import validate_origin
from clipora_v8_web.owned_api import create_owned_app
from clipora_v8_web.owned_jobs import OwnerRequired,IdempotencyConflict,QueueFull
from .scheduler import Scheduler
from clipora_v8_image_backend.delivery import attach_album_routes
from clipora_v8_image_backend.jobs import create_fixture_job


def create_local_app(origin,state_dir,*,scheduler_factory=Scheduler):
    parsed=validate_origin(origin)
    if parsed.scheme!='http' or parsed.hostname!='127.0.0.1':
        raise ValueError('The offline workflow is restricted to loopback HTTP')
    state=Path(state_dir).absolute()
    if any(p.is_symlink() for p in (state,*state.parents)):raise ValueError('Symlinked local state rejected')
    artifacts=state/'artifacts'
    app=create_owned_app(origin,state,artifacts,offline_sample_enabled=True)
    attach_album_routes(app,artifacts)
    store=app.state.owned_jobs;scheduler=scheduler_factory(store,artifacts)
    app.state.sample_scheduler=scheduler
    @asynccontextmanager
    async def lifespan(app):
        await scheduler.start()
        try:yield
        finally:await scheduler.close()
    app.router.lifespan_context=lifespan
    async def submit_sample(request:Request,images=False):
        if not scheduler.available:raise HTTPException(503,'Sample processing is unavailable.')
        if request.headers.get('content-type','').split(';')[0].strip().lower()!='application/json':
            raise HTTPException(415,'Send application/json.')
        try:
            data=await request.json()
            if data!={}:raise ValueError('The local sample does not accept a video URL.')
            token=app.state.owned_session_token(request)
            keys=request.headers.getlist('idempotency-key')
            if len(keys)!=1:raise ValueError('Exactly one idempotency key required')
            return create_fixture_job(store,token,keys[0]) if images else store.create_sample(token,keys[0])
        except OwnerRequired:raise HTTPException(403,'Start a browser session first.') from None
        except QueueFull:raise HTTPException(429,'Sample queue is full. Please try again shortly.') from None
        except IdempotencyConflict:raise HTTPException(409,'Sample request already used.') from None
        except (ValueError,TypeError):raise HTTPException(422,'Send an empty object and a valid idempotency key.') from None
        except (OSError,sqlite3.Error):raise HTTPException(503,'Sample storage unavailable.') from None
    @app.post('/api/v8/samples',status_code=202)
    async def create_sample(request:Request):return await submit_sample(request)
    @app.post('/api/v8/samples/images',status_code=202)
    async def create_images(request:Request):return await submit_sample(request,images=True)
    return app
