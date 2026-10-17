"""Only the fixed, internal-network sample runner. No user URL or command input."""
import asyncio
import json
import os
from pathlib import Path
import re
import signal
import sys

BACKEND=Path(__file__).resolve().parent.parent
LABEL='clipora.three.kernel'


async def docker(*args):
    process=await asyncio.create_subprocess_exec('docker',*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:
        stdout,stderr=await asyncio.wait_for(process.communicate(),5)
    except BaseException:
        if process.returncode is None:process.kill()
        await process.wait();raise
    return process.returncode,stdout,stderr


async def cleanup(owner):
    if not re.fullmatch('[0-9a-f]{32}',owner):raise ValueError('Invalid recovery scope')
    for kind in ('container','network'):
        query=['ps','-aq','--no-trunc'] if kind=='container' else ['network','ls','-q','--no-trunc']
        code,stdout,_=await docker(*query,'--filter','label='+LABEL+'='+owner)
        if code:raise RuntimeError('Resource inventory unavailable')
        for identity in stdout.decode().split():
            if not re.fullmatch('[0-9a-f]{64}',identity):raise RuntimeError('Unexpected resource identity')
            code,data,_=await docker('inspect',identity)
            if code:continue
            info=json.loads(data)[0]
            labels=info.get('Config',{}).get('Labels',{}) if kind=='container' else info.get('Labels',{})
            if labels.get(LABEL)!=owner:raise RuntimeError('Resource owner mismatch')
            code,_,_=await docker(*(['rm','-f',identity] if kind=='container' else ['network','rm',identity]))
            if code:
                remaining,_,_=await docker('inspect',identity)
                if remaining==0:raise RuntimeError('Resource cleanup failed')
    for query in (['ps','-aq'],['network','ls','-q']):
        code,stdout,_=await docker(*query,'--filter','label='+LABEL+'='+owner)
        if code or stdout.strip():raise RuntimeError('Resource cleanup not confirmed')


class SampleResource:
    artifact_name="video.mp4"

    def command(self):
        args=[sys.executable,"-B",str(BACKEND/"clipora_v8_firewall_candidate/run_three_tier_kernel.py"),
              "--mutual","--resource-owner",self.owner,"--artifact",str(self.path)]
        if self.hold:args.append("--interactive-hold")
        return args

    def verified(self,report):
        return report.get("mp4_h264_verified") and report.get("gateway_egress_mutual_TLS") and report.get("owned_resources_removed")
    def __init__(self,owner,directory,lock_fd,*,hold=False):
        if not re.fullmatch('[0-9a-f]{32}',owner):raise ValueError('Invalid runner owner')
        self.owner=owner;self.directory=Path(directory);self.lock_fd=lock_fd
        self.path=self.directory/self.artifact_name;self.hold=hold
        self.process=None;self.stopping=False;self.lock=asyncio.Lock();self.readers=[];self.output=[]

    async def drain(self,reader):
        data=bytearray()
        while chunk:=await reader.read(8192):
            if len(data)<65536:data.extend(chunk[:65536-len(data)])
        return bytes(data)

    async def wait(self):
        async with self.lock:
            if self.stopping:raise RuntimeError('Sample stopped before launch')
            self.directory.mkdir(parents=True,exist_ok=False,mode=0o700)
            args=self.command()
            self.process=await asyncio.wait_for(asyncio.create_subprocess_exec(*args,cwd=BACKEND,
                start_new_session=True,pass_fds=(self.lock_fd,),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE),5)
            self.readers=[asyncio.create_task(self.drain(self.process.stdout)),asyncio.create_task(self.drain(self.process.stderr))]
        code=await self.process.wait()
        stdout,stderr=await asyncio.gather(*self.readers)
        if code:raise RuntimeError('Local sample worker failed')
        report=json.loads(stdout)
        if not (self.verified(report) and self.path.is_file()):
            raise RuntimeError('Sample verification incomplete')
        return self.path

    async def stop(self):
        async with self.lock:
            self.stopping=True
            if self.process is not None and self.process.returncode is None:
                self.process.terminate()
                try:await asyncio.wait_for(self.process.wait(),4)
                except TimeoutError:
                    try:os.killpg(self.process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    await self.process.wait()
            if self.readers:await asyncio.wait_for(asyncio.gather(*self.readers),2)
            await cleanup(self.owner)
            return True


class ImageSampleResource(SampleResource):
    artifact_name='album.zip'

    def command(self):
        args=[sys.executable,'-B',str(BACKEND/'clipora_v8_image_backend/run_offline.py'),
              '--resource-owner',self.owner,'--artifact',str(self.path)]
        if self.hold:args.append('--interactive-hold')
        return args

    def verified(self,report):
        return (report.get('actual_FFmpeg_decoded')==['PNG','JPEG','WebP']
                and report.get('owned_container_removed') is True and report.get('worker_network')=='none'
                and report.get('corrupt_image_payload_rejected') is True)
