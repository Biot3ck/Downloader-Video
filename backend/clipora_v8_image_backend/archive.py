"""One immutable album ZIP: ordered manifest, original bytes, no remote URLs."""
import hashlib
import io
import json
import re
import stat
import struct
import zipfile
from .formats import image_info,MAX_TOTAL,MAX_ALBUM,MAX_COUNT


def pack(images):
    if type(images) is not list or not 1<=len(images)<=MAX_COUNT:raise ValueError('Album count rejected')
    items=[];total=pixels=0
    for index,data in enumerate(images,1):
        info=image_info(data);total+=len(data);pixels+=info['width']*info['height']
        if total>MAX_TOTAL or pixels>32000000:raise ValueError('Album budget exceeded')
        items.append({'position':index,'name':f'image-{index:02d}.'+info.pop('extension'),
                      **info,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    manifest={'version':1,'media_kind':'images','image_count':len(items),'items':items}
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED,allowZip64=False) as archive:
        for name,data in [('manifest.json',json.dumps(manifest,separators=(',',':')).encode()),
                          *[(item['name'],data) for item,data in zip(items,images)]]:
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.external_attr=(stat.S_IFREG|0o600)<<16
            archive.writestr(info,data)
    result=output.getvalue()
    if len(result)>MAX_ALBUM:raise ValueError('Album archive budget exceeded')
    return result,manifest


def checked_archive(stream):
    # Bound the directory before ZipFile allocates entry objects. The worker
    # writes a small, single-disk ZIP without comments or ZIP64 extensions.
    stream.seek(0,2);size=stream.tell()
    if not 64<=size<=MAX_ALBUM:raise ValueError('Archive size rejected')
    stream.seek(size-22);record=stream.read(22)
    if len(record)!=22:raise ValueError('Archive end missing')
    signature,disk,directory_disk,count,total,directory_size,offset,comment=struct.unpack('<4s4H2IH',record)
    if (signature!=b'PK\x05\x06' or disk or directory_disk or comment or count!=total
            or not 2<=total<=MAX_COUNT+1 or not 1<=directory_size<=8192
            or offset+directory_size!=size-22):raise ValueError('Archive directory bounds rejected')
    stream.seek(0)
    if stream.read(4)!=b'PK\x03\x04':raise ValueError('Archive prefix rejected')
    stream.seek(0)
    return zipfile.ZipFile(stream)


def read_manifest(archive):
    entries=archive.infolist();names=[entry.filename for entry in entries]
    if not 2<=len(entries)<=MAX_COUNT+1 or len(set(names))!=len(names) or names[0]!='manifest.json':raise ValueError('Invalid archive entries')
    for entry in entries:
        if (entry.compress_type!=zipfile.ZIP_STORED or entry.flag_bits&1 or entry.file_size!=entry.compress_size
                or stat.S_IFMT(entry.external_attr>>16) not in (0,stat.S_IFREG)):
            raise ValueError('Compressed, encrypted or special entry rejected')
    first=entries[0]
    if not 1<=first.file_size<=16384:raise ValueError('Manifest size rejected')
    manifest=json.loads(archive.read(first))
    if (type(manifest) is not dict or set(manifest)!={'version','media_kind','image_count','items'}
            or type(manifest['version']) is not int or manifest['version']!=1 or manifest['media_kind']!='images'
            or type(manifest['items']) is not list or not 1<=len(manifest['items'])<=MAX_COUNT
            or type(manifest['image_count']) is not int or manifest['image_count']!=len(manifest['items'])):
        raise ValueError('Invalid image manifest')
    total=pixels=0
    for position,item in enumerate(manifest['items'],1):
        if type(item) is not dict or set(item)!={'position','name','mime','width','height','size','sha256'}:raise ValueError('Unexpected image fields')
        if type(item['position']) is not int or item['position']!=position:raise ValueError('Invalid image order')
        if type(item['name']) is not str or not re.fullmatch(f'image-{position:02d}\\.(jpg|png|webp)',item['name']):raise ValueError('Invalid image name')
        for key in ('width','height','size'):
            if type(item[key]) is not int or item[key]<=0:raise ValueError('Invalid image bound')
        if max(item['width'],item['height'])>16384 or item['width']*item['height']>16000000 or item['size']>10*1024*1024:raise ValueError('Image budget rejected')
        total+=item['size'];pixels+=item['width']*item['height']
        extension=item['name'].rsplit('.',1)[1]
        if item['mime']!={'jpg':'image/jpeg','png':'image/png','webp':'image/webp'}[extension]:raise ValueError('Image type mismatch')
        if type(item['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',item['sha256']):raise ValueError('Invalid image hash')
    if total>MAX_TOTAL or pixels>32000000 or names!=['manifest.json',*[item['name'] for item in manifest['items']]]:raise ValueError('Album budget or ordering rejected')
    for item,entry in zip(manifest['items'],entries[1:]):
        if item['size']!=entry.file_size:raise ValueError('Image entry size mismatch')
    return manifest


def verify(stream):
    with checked_archive(stream) as archive:
        manifest=read_manifest(archive)
        for item in manifest['items']:
            data=archive.read(item['name']);info=image_info(data)
            if (hashlib.sha256(data).hexdigest()!=item['sha256'] or info['width']!=item['width']
                    or info['height']!=item['height'] or info['mime']!=item['mime']):raise ValueError('Image integrity mismatch')
        return manifest
