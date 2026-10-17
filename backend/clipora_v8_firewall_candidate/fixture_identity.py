"""Ephemeral mTLS leaf certificates for offline fixtures only."""
import subprocess
from pathlib import Path


def identities(root):
    root=Path(root)
    def command(args):subprocess.run(args,check=True,capture_output=True,timeout=15)
    for name,host,usage in [('ingress','egress.clipora.test','serverAuth'),
                            ('gateway','gateway.clipora.test','clientAuth'),
                            ('other-client','other.clipora.test','clientAuth')]:
        ext=root/(name+'.ext')
        ext.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage='+usage+'\nsubjectAltName=DNS:'+host+'\n')
        key=root/'server'/(name+'.key');csr=root/(name+'.csr')
        command(['openssl','req','-new','-newkey','rsa:2048','-nodes','-sha256','-subj','/CN='+host,
                 '-keyout',str(key),'-out',str(csr)])
        command(['openssl','x509','-req','-sha256','-days','1','-in',str(csr),'-CA',str(root/'trust/ca.pem'),
                 '-CAkey',str(root/'ca.key'),'-CAcreateserial','-extfile',str(ext),'-out',str(root/'server'/(name+'.pem'))])


def remove_authority_material(root):
    """Remove known ephemeral issuer artifacts before mounting a runtime bundle."""
    root=Path(root)
    names=['ca.key','other.key','openssl.cnf','trust/ca.srl']
    for leaf in ('valid','wrong-host','ingress','gateway','other-client'):
        names.extend((leaf+'.csr',leaf+'.ext'))
    for name in names:(root/name).unlink(missing_ok=True)
    if (root/'ca.key').exists() or (root/'other.key').exists():
        raise RuntimeError('Issuer private key remained in runtime bundle')
