"""Cancellation observer for an explicitly supplied, already owned resource.

No process/Docker launcher, scheduler, network, or public activation here.
Handle.wait() returns a stable local artifact path after successful execution.
Handle.stop() must return True only after its worker AND exporter have stopped.
"""
import asyncio
import time
from .owned_publish import publish,PublicationDenied


async def observe(store,job_id,execution_owner,handle,artifact_dir,*,poll=.05,timeout=150,stop_timeout=5,publisher=None):
    if not 0<poll<=1 or not 0<timeout<=150 or not 0<stop_timeout<=10:raise ValueError('Invalid runner deadlines')
    waited=asyncio.create_task(handle.wait())
    stopped=False
    async def stop():
        nonlocal stopped
        result=await asyncio.wait_for(handle.stop(),stop_timeout)
        if result is not True:raise RuntimeError('Worker termination not confirmed')
        if not waited.done():waited.cancel()
        done,_=await asyncio.wait({waited},timeout=1)
        if not done:raise RuntimeError('Exporter observation did not stop')
        if not waited.cancelled():waited.exception()
        stopped=True
    async def protected_stop():
        task=asyncio.create_task(stop())
        cancelled=False
        while not task.done():
            try:await asyncio.wait({task})
            except asyncio.CancelledError:cancelled=True
        task.result()
        return cancelled
    try:
        deadline=time.monotonic()+timeout
        while not waited.done():
            if store.stop_required(job_id,execution_owner) or time.monotonic()>=deadline:
                cancelled=await protected_stop()
                store.confirm_stopped(job_id,execution_owner)
                if cancelled:raise asyncio.CancelledError
                return False
            await asyncio.wait({waited},timeout=poll)
        # Capture result before cleanup: exporters may report their success
        # path while a Docker fixture is deliberately kept alive for export.
        source=waited.result()
        cancelled=await protected_stop()
        if cancelled:raise asyncio.CancelledError
        if store.stop_required(job_id,execution_owner):
            store.confirm_stopped(job_id,execution_owner)
            return False
        try:(publisher or publish)(store,job_id,execution_owner,source,artifact_dir)
        except PublicationDenied:
            store.confirm_stopped(job_id,execution_owner)
            return False
        return True
    except BaseException:
        if not stopped:
            try:await protected_stop()
            except BaseException:
                # Do not release queue capacity or mark failed while the
                # resource may still be writing. Recovery owns this fence.
                if not waited.done():waited.cancel()
                await asyncio.wait({waited},timeout=1)
                if waited.done() and not waited.cancelled():waited.exception()
                raise RuntimeError('Worker cleanup requires recovery') from None
        store.confirm_stopped(job_id,execution_owner)
        raise
