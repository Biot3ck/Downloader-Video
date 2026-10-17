"""Synthetic media proof, invoked only by run_formats_offline.py in Docker."""
import json
import os
from pathlib import Path
import subprocess
from video_formats import choices,verify_output


def run(args):
    result=subprocess.run(args,capture_output=True,timeout=20)
    if result.returncode:raise RuntimeError('Offline media command failed')
    if len(result.stdout)>65536:raise RuntimeError('Probe output too large')
    return result.stdout


def inspect(path):
    return json.loads(run(['ffprobe','-v','error','-protocol_whitelist','file,pipe',
        '-show_entries','format=duration,size,format_name:stream=codec_type,codec_name,width,height',
        '-of','json',str(path)]))


def main():
    status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    assert os.getuid()==10001 and status['NoNewPrivs'].strip()=='1'
    assert all(int(status[k],16)==0 for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
    base=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-xerror','-threads','1','-filter_threads','1']
    rows=[]
    for identity,dimensions in [('standard','854x480'),('landscape','1280x720'),('portrait','1080x1920')]:
        path=Path('/work')/(identity+'.mp4')
        run(base+['-f','lavfi','-i','testsrc2=size='+dimensions+':rate=12',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','0.5',
            '-c:v','libx264','-preset','ultrafast','-crf','30','-pix_fmt','yuv420p','-threads','1',
            '-c:a','aac','-b:a','96k','-shortest',str(path)])
        data=inspect(path);video=next(s for s in data['streams'] if s['codec_type']=='video')
        rows.append({'format_id':identity,'width':video['width'],'height':video['height'],
                     'vcodec':'h264','acodec':'aac','ext':'mp4','has_drm':False,'filesize':path.stat().st_size})
    metadata={'duration':.5,'formats':rows[:2]};plans=choices(metadata)
    portrait=choices({'duration':.5,'formats':[rows[0],rows[2]]})['hd']
    outputs={}
    for kind,plan in [('video',plans['video']),('hd',plans['hd']),('portrait_hd',portrait),('mp3',plans['mp3'])]:
        source=Path('/work')/(plan.format_ids[0]+'.mp4')
        output=Path('/work')/('result-'+kind+('.mp3' if kind=='mp3' else '.mp4'))
        options=['-map','0:a:0','-vn','-c:a','libmp3lame','-b:a','128k'] if kind=='mp3' else ['-map','0:v:0','-map','0:a:0','-c','copy']
        run(base+['-protocol_whitelist','file,pipe','-i',str(source),*options,'-map_metadata','-1',str(output)])
        data=inspect(output);verify_output(plan,data)
        # Decode the whole fixture, beyond ffprobe metadata/signature checks.
        run(base+['-protocol_whitelist','file,pipe','-i',str(output),'-f','null','-'])
        outputs[kind]={'width':plan.width,'height':plan.height,'bytes':output.stat().st_size,
                       'container':data['format']['format_name'],'decoded':True}
    rejected=[]
    for label,plan,data in [('480p_as_hd',plans['hd'],inspect(Path('/work/standard.mp4'))),
                            ('mp4_as_mp3',plans['mp3'],inspect(Path('/work/landscape.mp4')))]:
        try:verify_output(plan,data)
        except ValueError:rejected.append(label)
        else:raise AssertionError('Wrong output accepted')
    print(json.dumps({'synthetic_offline_media_only':True,'outputs':outputs,'wrong_outputs_rejected':rejected,
                      'video_stream_copy_without_upscale':True,'public_downloads_enabled':False,'ads_enabled':False}))


if __name__=='__main__':main()
