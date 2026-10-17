"""MP4 over CONNECT, actual local DNS/firewall/TLS, no outside network."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from run_numeric_wire import main

PROBE='from clipora_v8_firewall_candidate.kernel_tls_fixture import parent\nparent()\n'
if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'clipora_v8_verified_tls'))
    from run_verified_tls import certificates
    reports=[]
    with tempfile.TemporaryDirectory(prefix='clipora-connect-tls-') as tmp:
        for case in ('valid','wrong-host','untrusted-ca'):
            def prepare(bundle,case=case):
                certificates(bundle)
                (bundle/'tls-case.txt').write_text(case)
                (bundle/'connect-mode').touch()
                subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
                    'color=c=purple:s=160x90:r=10','-t','0.2','-c:v','libx264','-pix_fmt','yuv420p',
                    '-movflags','+faststart',str(bundle/'sample.mp4')],check=True,capture_output=True,timeout=15)
            path=Path(tmp)/(case+'.json')
            main(probe=PROBE,extra_files=tuple('clipora_v8_firewall_candidate/'+name for name in
                ('dns_snapshot.py','integrated_probe.py','kernel_tls_fixture.py','connect_tls_probe.py','connect_relay.py'))+
                ('clipora_v8_secure_egress_stage/http_parser.py',),prepare=prepare,report_path=path)
            reports.append(json.loads(path.read_text()))
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(reports,indent=2)+'\n')
