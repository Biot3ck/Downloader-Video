"""Ephemeral CA TLS on DNS -> Broker -> numeric socket, network=none only."""
from pathlib import Path
import json
import sys
from run_numeric_wire import main

PROBE = r'''
import asyncio,json,ssl
from pathlib import Path
from clipora_v8_firewall_candidate.integrated_probe import bootstrap,run
case=Path('/fixture/tls-case.txt').read_text()
server=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
server.minimum_version=ssl.TLSVersion.TLSv1_2
cert='wrong-host' if case=='wrong-host' else 'valid'
server.load_cert_chain('/fixture/server/'+cert+'.pem','/fixture/server/'+cert+'.key')
client=ssl.create_default_context(cafile='/fixture/trust/'+('other' if case=='untrusted-ca' else 'ca')+'.pem')
client.minimum_version=ssl.TLSVersion.TLSv1_2
assert client.check_hostname and client.verify_mode==ssl.CERT_REQUIRED
report=asyncio.run(run(bootstrap(),server_context=server,client_context=client,
                       tls_hostname='example.com',expect_tls_failure=case!='valid'))
if case=='valid':assert report['tls_tested'] and report['actual_bytes_roundtrip']
else:assert report['tls_verification_failure_observed']
report['case']=case
report['hostname_and_CA_verification_enabled']=True
print(json.dumps(report))
'''

if __name__ == '__main__':
    # Reuse the verified offline suite's ephemeral certificate generator.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'clipora_v8_verified_tls'))
    from run_verified_tls import certificates
    reports=[]
    import tempfile
    with tempfile.TemporaryDirectory(prefix='clipora-integrated-tls-') as tmp:
        root=Path(tmp)
        for case in ('valid','wrong-host','untrusted-ca'):
            def prepare(bundle, case=case):
                certificates(bundle)
                (bundle/'tls-case.txt').write_text(case)
            report_path=root/(case+'.json')
            main(probe=PROBE,extra_files=(
                'clipora_v8_firewall_candidate/dns_snapshot.py',
                'clipora_v8_firewall_candidate/integrated_probe.py'),
                prepare=prepare,report_path=report_path)
            reports.append(json.loads(report_path.read_text()))
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(reports,indent=2)+'\n')
