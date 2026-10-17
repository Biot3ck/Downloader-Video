"""All-local actual DNS, broker, TCP, TLS and namespace firewall fixture."""
import json
from pathlib import Path
import sys
import tempfile
from run_numeric_wire import main

PROBE="from clipora_v8_firewall_candidate.kernel_tls_fixture import parent\nparent()\n"
if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'clipora_v8_verified_tls'))
    from run_verified_tls import certificates
    reports=[]
    with tempfile.TemporaryDirectory(prefix='clipora-kernel-tls-') as tmp:
        for case in ('valid','wrong-host','untrusted-ca'):
            def prepare(bundle,case=case):
                certificates(bundle);(bundle/'tls-case.txt').write_text(case)
            path=Path(tmp)/(case+'.json')
            main(probe=PROBE,extra_files=tuple('clipora_v8_firewall_candidate/'+name for name in
                ('dns_snapshot.py','integrated_probe.py','kernel_tls_fixture.py')),
                prepare=prepare,report_path=path)
            reports.append(json.loads(path.read_text()))
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(reports,indent=2)+'\n')
