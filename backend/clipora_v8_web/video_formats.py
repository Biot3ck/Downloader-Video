"""Offline candidate: source format planning and output inspection, no I/O.

Not imported by the active app, worker, or image allowlist. A plan authorizes
neither network access nor an ad reward. Transport/resource/ownership gates
must still run independently before this can be integrated.
"""
from dataclasses import dataclass
import math
import re

MAX_BYTES=64*1024*1024
MAX_SECONDS=1800


def number(value,maximum):
    return type(value) in (int,float) and 0<value<=maximum and math.isfinite(value)


@dataclass(frozen=True)
class Plan:
    kind:str
    format_ids:tuple
    width:int
    height:int
    duration:float
    estimated_bytes:int|None


def choices(metadata):
    """Return only native, non-DRM H264/AAC MP4 candidates for this MVP.

    Unknown formats are unavailable. URLs/headers/cookies are never copied
    into a plan. Size estimates are admission hints, not runtime byte limits.
    """
    if (type(metadata) is not dict or not number(metadata.get('duration'),MAX_SECONDS)
            or metadata.get('is_live') not in (None,False) or metadata.get('has_drm') is True
            or metadata.get('_type') not in (None,'video')
            or metadata.get('live_status') not in (None,'not_live','was_live')):
        raise ValueError('Unsupported video metadata')
    formats=metadata.get('formats')
    if type(formats) is not list or not 1<=len(formats)<=256:
        raise ValueError('Format list exceeds policy')
    seen=set();accepted=[]
    for item in formats:
        if type(item) is not dict:continue
        identity=item.get('format_id')
        if type(identity) is not str or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',identity):continue
        if identity in seen:raise ValueError('Ambiguous format identifier')
        seen.add(identity)
        if item.get('has_drm') is not False or item.get('ext') not in ('mp4','m4a'):continue
        size=item.get('filesize')
        if size is not None and (type(size) is not int or not 128<=size<=MAX_BYTES):continue
        video=item.get('vcodec');audio=item.get('acodec')
        if type(video) is not str or type(audio) is not str:continue
        if video!='none' and video!='h264' and not video.startswith('avc1.'):continue
        if audio not in ('none','aac','mp4a.40.2','mp4a.40.5'):continue
        width,height=item.get('width',0),item.get('height',0)
        if video!='none':
            if (item['ext']!='mp4' or type(width) is not int or type(height) is not int
                    or not 1<=min(width,height)<=1080 or max(width,height)>1920):continue
            fps=item.get('fps')
            if fps is not None and not number(fps,60):continue
        elif audio=='none':continue
        bitrate=item.get('abr',0)
        if not number(bitrate,1000):bitrate=0
        accepted.append((identity,video,audio,width,height,size,bitrate))
    audio=sorted((f for f in accepted if f[2]!='none'),key=lambda f:(f[1]=='none',f[6],f[0]),reverse=True)
    candidates=[]
    for f in accepted:
        if f[1]=='none':continue
        partner=next((a for a in audio if a[1]=='none' and (f[5] is None or a[5] is None or f[5]+a[5]<=MAX_BYTES)),None)
        if f[2]!='none':ids=(f[0],);size=f[5]
        elif partner:
            ids=(f[0],partner[0]);size=f[5]+partner[5] if f[5] is not None and partner[5] is not None else None
        else:continue
        candidates.append((f,ids,size))
    def plan(kind,candidate):
        f,ids,size=candidate
        return Plan(kind,ids,f[3],f[4],float(metadata['duration']),size)
    result={}
    standard=[c for c in candidates if min(c[0][3:5])<=480]
    high=[c for c in candidates if 720<=min(c[0][3:5])<=1080]
    rank=lambda c:(min(c[0][3:5]),c[0][3]*c[0][4],c[0][0])
    if standard:result['video']=plan('video',max(standard,key=rank))
    if high:result['hd']=plan('hd',max(high,key=rank))
    if audio:
        # Transcoding to MP3 needs its own bounded worker. Input size is not
        # an estimate of the MP3 output, so output estimate stays unknown.
        result['mp3']=Plan('mp3',(audio[0][0],),0,0,float(metadata['duration']),None)
    return result


def verify_output(plan,probe):
    """Check bounded ffprobe JSON from an isolated runner before publication.

    Does not itself read files, invoke ffprobe, decode media or prove that an
    upstream uploader never upscaled a source. Never accept probe from HTTP.
    """
    if (type(plan) is not Plan or plan.kind not in ('video','hd','mp3')
            or not number(plan.duration,MAX_SECONDS) or type(probe) is not dict):
        raise ValueError('Invalid output inspection')
    streams,info=probe.get('streams'),probe.get('format')
    if type(streams) is not list or type(info) is not dict:raise ValueError('Missing output inspection')
    try:
        raw_size=info['size']
        if not (type(raw_size) is int or (type(raw_size) is str and re.fullmatch('[0-9]{1,10}',raw_size))):
            raise ValueError('Invalid byte count')
        size=int(raw_size);duration=float(info['duration'])
    except (ValueError,TypeError,KeyError,OverflowError):raise ValueError('Invalid output limits') from None
    if not 128<=size<=MAX_BYTES or not number(duration,MAX_SECONDS) or abs(duration-plan.duration)>max(.5,plan.duration*.02):
        raise ValueError('Output size or duration rejected')
    if any(type(s) is not dict for s in streams):raise ValueError('Invalid streams')
    video=[s for s in streams if s.get('codec_type')=='video']
    audio=[s for s in streams if s.get('codec_type')=='audio']
    if plan.kind=='mp3':
        if len(streams)!=1 or len(audio)!=1 or audio[0].get('codec_name')!='mp3' or info.get('format_name')!='mp3':
            raise ValueError('Output is not audio-only MP3')
    else:
        if (len(streams)!=2 or len(video)!=1 or len(audio)!=1
                or video[0].get('codec_name')!='h264' or audio[0].get('codec_name')!='aac'
                or type(info.get('format_name')) is not str or 'mp4' not in info['format_name'].split(',')
                or type(video[0].get('width')) is not int or type(video[0].get('height')) is not int
                or (video[0]['width'],video[0]['height'])!=(plan.width,plan.height)):
            raise ValueError('Output differs from selected source')
        short=min(plan.width,plan.height)
        if (plan.kind=='hd' and not 720<=short<=1080) or (plan.kind=='video' and not 1<=short<=480):
            raise ValueError('Output quality tier rejected')
    return True
