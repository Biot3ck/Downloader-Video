"""Verify HTTP inside a disposable, unpublished internal web container."""
import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4


def docker(args):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=20)
    if result.returncode:raise RuntimeError(result.stderr[-1500:])
    return result.stdout.strip()


def main(*, owned=False, report_path=None):
    identity = uuid4().hex
    name = 'clipora-web-test-' + identity[:10]
    network = name + '-internal'
    label = 'clipora.web.test=' + identity
    before = set(docker(['ps', '-aq', '--no-trunc']).split())
    origin = 'http://127.0.0.1:8091'
    def http(path, data=None, headers=None):
        script = """import http.client,json,sys
p=json.loads(sys.argv[1]);c=http.client.HTTPConnection('127.0.0.1',8080,timeout=2)
c.request('POST' if p['body'] is not None else 'GET',p['path'],body=p['body'],headers=p['headers'])
r=c.getresponse();print(json.dumps([r.status,r.read().decode(),dict(r.getheaders())]));c.close()
"""
        payload = {'path':path, 'body':data.decode() if data is not None else None,
                   'headers':{'Host':'127.0.0.1:8091', **(headers or {})}}
        return json.loads(docker(['exec',name,'python','-B','-c',script,json.dumps(payload)]))
    made_network = made_container = False
    try:
        docker(['image', 'inspect', 'clipora-web:v8-staging'])
        docker(['network', 'create', '--internal', '--label', label, network]);made_network = True
        docker(['create', '--pull', 'never', '--name', name, '--label', label, '--network', network,
                '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                '--user', '10001:10001', '--memory', '192m', '--cpus', '1', '--pids-limit', '64',
                '--dns', '127.0.0.1', '--tmpfs', '/state:rw,nosuid,nodev,noexec,size=4m,uid=10001,gid=10001,mode=0700',
                '-e', 'CLIPORA_WEB_STATE=/state',
                '-e', 'CLIPORA_WEB_ORIGIN=' + origin] +
               (['--entrypoint','python'] if owned else []) + ['clipora-web:v8-staging'] +
               (['-B','-m','uvicorn','clipora_v8_web.owned_entry:app','--host','0.0.0.0','--port','8080',
                 '--no-proxy-headers','--no-access-log'] if owned else []));made_container = True
        docker(['start', name])
        for _ in range(50):
            try:
                if http('/healthz')[0] == 200:break
            except RuntimeError:pass
            time.sleep(.1)
        else:
            logs = subprocess.run(['docker','logs',name],capture_output=True,text=True,timeout=10)
            raise TimeoutError('Web staging startup failed: ' + logs.stderr[-1800:] + logs.stdout[-500:])
        info = json.loads(docker(['inspect', name]))[0]
        host = info['HostConfig']
        assert host['ReadonlyRootfs'] and host['CapDrop'] == ['ALL'] and not host.get('CapAdd')
        assert not host['Privileged'] and not host.get('Binds')
        assert all(m['Type']=='tmpfs' and m['Destination']=='/state' for m in info['Mounts'])
        assert 'size=4m' in host['Tmpfs']['/state']
        assert not host.get('PortBindings')
        assert len(info['NetworkSettings']['Networks']) == 1
        assert json.loads(docker(['network','inspect',network]))[0]['Internal'] is True
        for path in ('/', '/assets/app.js', '/assets/style.css'):
            status, body, headers = http(path)
            assert status == 200 and body
            assert "frame-ancestors 'none'" in headers['content-security-policy']
        checks = []
        for url in ('https://youtu.be/fixture','https://www.tiktok.com/@demo/video/123',
                    'https://www.instagram.com/reel/fixture/','https://pin.it/fixture'):
            status, body, _ = http('/api/v8/validate',json.dumps({'url':url}).encode(),
                                   {'Origin':origin,'Content-Type':'application/json'})
            assert status == 200
            result = json.loads(body);assert result['network_access_performed'] is False
            checks.append(result['platform'])
        for url in ('https://www.tiktok.com/@fixture/photo/123', 'https://www.instagram.com/p/fixture/', 'https://pin.it/fixture'):
            status,body,headers=http('/api/v8/validate',json.dumps({'url':url,'media_kind':'images'}).encode(),
                                    {'Origin':origin,'Content-Type':'application/json'})
            assert status==200 and json.loads(body)['media_kind']=='images'
            assert json.loads(body)['network_access_performed'] is False
            assert http('/api/v8/download',json.dumps({'url':url,'media_kind':'images'}).encode(),
                        {'Origin':origin,'Content-Type':'application/json'})[0]==503
        if owned:
            status,body,headers=http('/api/v8/session',b'',{'Origin':origin})
            assert status==204 and body=='' and 'HttpOnly' in headers['set-cookie']
            session_cookie=headers['set-cookie'].split(';',1)[0]
            setup=r'''import json,sys
from pathlib import Path
from clipora_v8_web.owned_entry import app,state
s=app.state.owned_jobs
job=s.create_owned(sys.argv[1],'https://youtu.be/fixture','a'*32)
s.claim('fixture-runner');assert s.finish(job['job_id'],'fixture-runner',True,'private')
(state/'artifacts'/(job['job_id']+'.mp4')).write_bytes(b'\x00\x00\x00\x20ftypisom'+b'x'*4096)
print(job['job_id'])
'''
            job_id=docker(['exec',name,'python','-B','-c',setup,session_cookie.split('=',1)[1]])
            path='/api/v8/jobs/'+job_id
            assert http(path,headers={'Cookie':session_cookie})[0]==200
            assert http(path)[0]==404 and http(path+'/file')[0]==404
            status,body,headers=http(path+'/file',headers={'Cookie':session_cookie,'Range':'bytes=4-7'})
            assert status==206 and body=='ftyp'
        status,body,_=http('/')
        assert status==200 and 'Photo Downloader' in body and 'Audio Downloader' in body and 'History' in body
        assert 'sample-start' not in body and 'type="file"' not in body
        source_probe="from pathlib import Path;r=Path('/srv/clipora_v8_web');assert all(not (r/p).exists() for p in ('dev.html','assets/dev.js','assets/dev.css','tools_archive'))"
        docker(['exec',name,'python','-B','-c',source_probe])
        assert http('/api/v8/download',b'{}',{'Origin':origin})[0] == 503
        for path in ('/dev','/docs','/openapi.json','/api/v8/real-offline/jobs'):
            assert http(path)[0] == 404
        assert http('/',headers={'Host':'evil.example'})[0] == 400
        assert http('/api/v8/validate',b'{}',{'Origin':'https://evil.example'})[0] == 403
        assert http('/api/v8/validate',b'x'*4097,{'Origin':origin})[0] == 413
        probe = "import json,os;from pathlib import Path;s=dict(l.split(':',1) for l in Path('/proc/self/status').read_text().splitlines() if ':' in l);assert os.getuid()==10001;assert all(int(s[n],16)==0 for n in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'));assert s['NoNewPrivs'].strip()=='1';print('PASS')"
        assert docker(['exec',name,'python','-B','-c',probe]) == 'PASS'
        # Each HTTP request uses a fresh process, while admission shares the container DB.
        for _ in range(41):
            limited_status, _, limited_headers = http('/api/v8/validate',b'{"url":"https://youtu.be/fixture"}',{'Origin':origin,'Content-Type':'application/json'})
            if limited_status == 429:break
            assert limited_status == 200
        assert limited_status == 429 and int(limited_headers['retry-after']) > 0
        dependency_check = docker(['exec',name,'python','-m','pip','check'])
        inventory_script = "import importlib.metadata as m,json;print(json.dumps(sorted((d.metadata['Name'],d.version) for d in m.distributions())))"
        inventory = json.loads(docker(['exec',name,'python','-B','-c',inventory_script]))
        report = {'ownership_contract_entrypoint':owned,'http_probe_location':'container loopback via docker exec','ports_published':False,'internal_network':True,'non_root_no_capabilities':True,
                  'platform_recognition':checks,'public_download_status':503,'developer_routes_status':404,
                  'cross_origin_status':403,'oversized_body_status':413,'image_id':info['Image'],
                  'dependency_check':dependency_check,'python_distribution_inventory':inventory,
                  'public_ready':False,'no_runtime_bind_mounts':True,'rate_limit_status':429,'rate_state_tmpfs_mib':4}
    finally:
        if made_container:
            info=json.loads(docker(['inspect',name]))[0]
            assert info['Config']['Labels'].get('clipora.web.test')==identity
            docker(['rm','-f',name])
        if made_network:
            info=json.loads(docker(['network','inspect',network]))[0]
            assert info['Labels'].get('clipora.web.test')==identity
            docker(['network','rm',network])
        assert before <= set(docker(['ps','-aq','--no-trunc']).split())
    report['owned_resources_removed']=True
    report['preexisting_containers_preserved']=True
    if report_path is not None:Path(report_path).write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: internal Docker web staging, four-platform validation, security boundary, cleanup')


if __name__=='__main__':main(report_path=sys.argv[1] if len(sys.argv)>1 else None)
