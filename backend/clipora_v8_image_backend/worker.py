"""Decode fixed local input in a networkless, bounded container; never fetch URLs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from .archive import pack
from .formats import image_info,MAX_FILE,MAX_COUNT,MAX_TOTAL


def prepare(source,output):
    source=Path(source).absolute();output=Path(output).absolute()
    if any(p.is_symlink() for path in (source,output.parent) for p in (path,*path.parents)):
        raise ValueError('Symlinked worker directory')
    names=sorted(source.iterdir())
    if not 1<=len(names)<=MAX_COUNT:raise ValueError('Image count rejected')
    images=[];total=pixels=0
    for index,path in enumerate(names,1):
        if path.name not in tuple(f'image-{index:02d}.'+suffix for suffix in ('jpg','png','webp')):
            raise ValueError('Unexpected worker input name')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            before=os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not 1<=before.st_size<=MAX_FILE:raise ValueError('Invalid worker file')
            with os.fdopen(os.dup(fd),'rb') as stream:data=stream.read(MAX_FILE+1)
            info=image_info(data)
            if path.suffix!='.'+info['extension']:raise ValueError('Image extension mismatch')
            total+=len(data);pixels+=info['width']*info['height']
            if total>MAX_TOTAL or pixels>32000000:raise ValueError('Album budget exceeded')
            # Explicit demuxer/decoder and local file/pipe protocols only. A
            # descriptor path pins the inode while the worker fully decodes it.
            prefix='/proc/self/fd' if Path('/proc/self/fd').is_dir() else '/dev/fd'
            codec={'png':'png','jpg':'mjpeg','webp':'webp'}[info['extension']]
            os.lseek(fd,0,os.SEEK_SET)
            result=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-xerror',
                '-err_detect','explode','-threads','1','-protocol_whitelist','file,pipe','-f',
                {'png':'png_pipe','jpg':'jpeg_pipe','webp':'webp_pipe'}[info['extension']],
                '-c:v',codec,'-i',f'{prefix}/{fd}','-frames:v','1','-f','null','-'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,pass_fds=(fd,),timeout=5)
            if result.returncode:raise ValueError('Image decoder rejected file')
            after=os.fstat(fd)
            if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                raise ValueError('Image changed during decode')
            images.append(data)
        finally:os.close(fd)
    archive,manifest=pack(images)
    fd=os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(archive);stream.flush();os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True);raise
    return {'image_count':len(images),'all_images_decoded':True,'archive_sha256':hashlib.sha256(archive).hexdigest()}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();print(json.dumps(prepare(args.source,args.output)))
