"""Owned, pinned-inode image/ZIP delivery. No user path or remote media URL."""
import os
from pathlib import Path
import re
import sqlite3
import stat
import struct
import zipfile
from fastapi import HTTPException,Request
from starlette.responses import FileResponse,Response,StreamingResponse
from .archive import read_manifest,checked_archive
from .formats import MAX_ALBUM
from .jobs import image_payload


class Album:
    def __init__(self,path):
        import fcntl
        self.fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            self.info=os.fstat(self.fd)
            if not stat.S_ISREG(self.info.st_mode) or not 64<=self.info.st_size<=MAX_ALBUM:raise ValueError('Invalid album')
            fcntl.flock(self.fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
            with os.fdopen(os.dup(self.fd),'rb') as stream,checked_archive(stream) as archive:
                self.manifest=read_manifest(archive)
                self.members={entry.filename:entry for entry in archive.infolist()}
            os.lseek(self.fd,0,os.SEEK_SET)
        except BaseException:self.close();raise

    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None

    def member_offset(self,item):
        entry=self.members[item['name']];header=os.pread(self.fd,30,entry.header_offset)
        if len(header)!=30 or header[:4]!=b'PK\x03\x04':raise ValueError('Invalid ZIP header')
        name_length,extra_length=struct.unpack_from('<HH',header,26)
        name=os.pread(self.fd,name_length,entry.header_offset+30)
        offset=entry.header_offset+30+name_length+extra_length
        if name!=item['name'].encode('ascii') or offset+item['size']>self.info.st_size:raise ValueError('Invalid member offset')
        return offset


class ArchiveResponse(FileResponse):
    def __init__(self,album):
        self.album=album
        prefix='/proc/self/fd' if Path('/proc/self/fd').is_dir() else '/dev/fd'
        try:super().__init__(f'{prefix}/{album.fd}',stat_result=album.info,media_type='application/zip',filename='clipora-images.zip')
        except BaseException:album.close();raise

    async def __call__(self,scope,receive,send):
        try:
            scope={**scope,'extensions':{key:value for key,value in scope.get('extensions',{}).items() if key!='http.response.pathsend'}}
            await super().__call__(scope,receive,send)
        finally:self.album.close()


class ImageResponse(StreamingResponse):
    def __init__(self,album,item,request):
        self.album=album
        try:
            offset=album.member_offset(item);size=item['size'];start=0;end=size-1;status=200
            ranges=request.headers.getlist('range')
            if ranges:
                if len(ranges)!=1:raise ValueError('Invalid range')
                match=re.fullmatch(r'bytes=([0-9]{0,12})-([0-9]{0,12})',ranges[0])
                if not match or not any(match.groups()):raise ValueError('Invalid range')
                first,last=match.groups()
                if first:
                    start=int(first);end=min(int(last),size-1) if last else size-1
                else:
                    suffix=int(last)
                    if not suffix:raise ValueError('Invalid suffix')
                    start=max(0,size-suffix)
                if start>end or start>=size:raise ValueError('Unsatisfiable range')
                status=206
            headers={'Content-Disposition':'attachment; filename="clipora-'+item['name']+'"',
                     'Content-Length':str(end-start+1),'Accept-Ranges':'bytes'}
            if status==206:headers['Content-Range']=f'bytes {start}-{end}/{size}'
            async def chunks():
                position=start
                while position<=end:
                    data=os.pread(album.fd,min(65536,end-position+1),offset+position)
                    if not data:raise RuntimeError('Image stream truncated')
                    position+=len(data);yield data
            self.head=request.method=='HEAD'
            super().__init__(chunks(),status_code=status,media_type=item['mime'],headers=headers)
        except BaseException:album.close();raise

    async def __call__(self,scope,receive,send):
        try:
            if self.head:
                await Response(status_code=self.status_code,headers=dict(self.headers))(scope,receive,send)
            else:await super().__call__(scope,receive,send)
        finally:self.album.close()


def attach_album_routes(app,directory):
    """Explicit candidate extension. Adds read routes, never job submission."""
    root=Path(directory).absolute()
    if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('Symlinked album directory')
    root.mkdir(mode=0o700,parents=True,exist_ok=True);root.chmod(0o700)
    store=app.state.owned_jobs;token=app.state.owned_session_token
    def open_owned(request,job_id):
        try:
            job=store.get_owned(token(request),job_id)
            if job is None or job['status']!='completed':raise ValueError('Not ready')
            with store.connection() as db:
                row=db.execute('SELECT url FROM job_ownership WHERE job_id=?',(job_id,)).fetchone()
            if row is None or not image_payload(row['url']):raise ValueError('Not an image job')
            return Album(root/(job_id+'.zip'))
        except sqlite3.Error:raise HTTPException(503,'Job storage unavailable.') from None
        except (OSError,ValueError,KeyError,zipfile.BadZipFile):raise HTTPException(404,'Job not found.') from None

    @app.get('/api/v8/jobs/{job_id}/images')
    def manifest(job_id:str,request:Request):
        album=open_owned(request,job_id)
        try:return album.manifest
        finally:album.close()

    @app.api_route('/api/v8/jobs/{job_id}/album.zip',methods=['GET','HEAD'])
    def archive(job_id:str,request:Request):return ArchiveResponse(open_owned(request,job_id))

    @app.api_route('/api/v8/jobs/{job_id}/images/{position}',methods=['GET','HEAD'])
    def image(job_id:str,position:str,request:Request):
        album=open_owned(request,job_id)
        if not re.fullmatch('[1-9][0-9]?',position) or int(position)>len(album.manifest['items']):
            album.close();raise HTTPException(404,'Job not found.')
        item=album.manifest['items'][int(position)-1]
        try:return ImageResponse(album,item,request)
        except ValueError:raise HTTPException(416,'Range not satisfiable.',headers={'Content-Range':f"bytes */{item['size']}"}) from None
