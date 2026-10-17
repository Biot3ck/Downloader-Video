"""Bounded still-image headers/containers. Full decoding belongs in the worker."""
import struct
import zlib

MAX_FILE=10*1024*1024
MAX_TOTAL=50*1024*1024
MAX_ALBUM=MAX_TOTAL+32768
MAX_COUNT=20


def image_info(data):
    if not isinstance(data,bytes) or not 1<=len(data)<=MAX_FILE:raise ValueError('Image size rejected')
    width=height=0;extension=mime=None
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        position=8;seen=[]
        while position<len(data):
            if position+12>len(data):raise ValueError('Truncated PNG')
            size=struct.unpack_from('>I',data,position)[0];end=position+12+size
            if end>len(data):raise ValueError('Truncated PNG chunk')
            name=data[position+4:position+8];body=data[position+8:end-4]
            if zlib.crc32(name+body)!=struct.unpack_from('>I',data,end-4)[0]:raise ValueError('PNG CRC mismatch')
            if not seen and (name!=b'IHDR' or size!=13):raise ValueError('PNG header missing')
            if name==b'IHDR':
                if seen:raise ValueError('Duplicate PNG header')
                width,height=struct.unpack_from('>II',body)
            if name==b'acTL':raise ValueError('Animated PNG rejected')
            seen.append(name);position=end
            if name==b'IEND':
                if size or end!=len(data):raise ValueError('Invalid PNG end')
                break
        if not seen or seen[-1]!=b'IEND' or b'IDAT' not in seen:raise ValueError('Incomplete PNG')
        extension,mime='png','image/png'
    elif data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9'):
        position=2
        while position<len(data)-2:
            if data[position]!=255:break
            while position<len(data) and data[position]==255:position+=1
            if position>=len(data):break
            marker=data[position];position+=1
            if marker in (217,218):break
            if marker==1 or 208<=marker<=215:continue
            if position+2>len(data):break
            size=struct.unpack_from('>H',data,position)[0]
            if size<2 or position+size>len(data):break
            if marker in (192,193,194):
                if size<8:break
                height,width=struct.unpack_from('>HH',data,position+3)
                extension,mime='jpg','image/jpeg';break
            position+=size
    elif len(data)>=30 and data[:4]==b'RIFF' and data[8:12]==b'WEBP':
        if struct.unpack_from('<I',data,4)[0]+8!=len(data):raise ValueError('Invalid WebP length')
        position=12;chunks=[]
        while position<len(data):
            if position+8>len(data):raise ValueError('Truncated WebP')
            name=data[position:position+4];size=struct.unpack_from('<I',data,position+4)[0]
            start=position+8;end=start+size
            if end+(size%2)>len(data):raise ValueError('Truncated WebP chunk')
            chunks.append(name)
            if name in (b'ANIM',b'ANMF'):raise ValueError('Animated WebP rejected')
            if name==b'VP8X' and size==10:
                if data[start]&2:raise ValueError('Animated WebP rejected')
                width=1+int.from_bytes(data[start+4:start+7],'little')
                height=1+int.from_bytes(data[start+7:start+10],'little')
            elif not width and name==b'VP8 ' and size>=10 and data[start+3:start+6]==b'\x9d\x01\x2a':
                width,height=(n&16383 for n in struct.unpack_from('<HH',data,start+6))
            elif not width and name==b'VP8L' and size>=5 and data[start]==47:
                bits=struct.unpack_from('<I',data,start+1)[0]
                width,height=1+(bits&16383),1+((bits>>14)&16383)
            position=end+(size%2)
        if not any(name in chunks for name in (b'VP8 ',b'VP8L')):raise ValueError('WebP image payload missing')
        extension,mime='webp','image/webp'
    if not extension or not width or not height:raise ValueError('Unsupported still image')
    if max(width,height)>16384 or width*height>16000000:raise ValueError('Image dimensions rejected')
    return {'extension':extension,'mime':mime,'width':width,'height':height}
