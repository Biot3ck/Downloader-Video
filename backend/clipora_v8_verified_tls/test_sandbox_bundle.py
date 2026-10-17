"""The offline worker receives an explicit, readonly runtime bundle."""
import tempfile
import unittest
from pathlib import Path
from clipora_v8_verified_tls.sandbox_bundle import (
    WORKER_FILES, STAGE_FILES, build_bundles, attest_worker_mounts, copy_regular,
)


class SandboxBundleTests(unittest.TestCase):
    def test_explicit_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bases = {name: root / name for name in ('backend', 'package', 'fixture', 'stage')}
            sources = {'backend': WORKER_FILES, 'package': ('worker_verified.py', 'egress_fixture.py'),
                       'fixture': ('gateway.py', 'fixtures/video.mp4'), 'stage': STAGE_FILES}
            for name, files in sources.items():
                for relative in (*files, '.env', 'jobs.sqlite3', 'private.key'):
                    p = bases[name] / relative
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text('fixture')
            result = build_bundles(**bases, destination=root / 'bundle')
            expected = {'worker': set(WORKER_FILES) | {'worker_verified.py'},
                        'services': {'gateway.py', 'fixtures/video.mp4', 'egress_fixture.py'},
                        'policies': set(STAGE_FILES)}
            for name, directory in result.items():
                files = {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()}
                self.assertEqual(files, expected[name])
                self.assertTrue(all(p.stat().st_mode & 0o222 == 0 for p in directory.rglob('*') if p.is_file()))

    def test_reject_symlink_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'real').write_text('fixture')
            (root / 'alias').symlink_to(root / 'real')
            for name in ('alias', '../outside', '/absolute'):
                with self.assertRaises(ValueError):
                    copy_regular(root, name, root / 'output')

    def test_attestation_canonical_path_and_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / 'bundle'
            bundle.mkdir()
            alias = root / 'alias'
            alias.symlink_to(bundle, target_is_directory=True)
            def info(source=alias):
                return {'Mounts': [{'Type': 'bind', 'Destination': '/app', 'Source': str(source), 'RW': False},
                                   {'Type': 'bind', 'Destination': '/trust', 'Source': '/trust-fixture', 'RW': False}]}
            attest_worker_mounts(info(), bundle)
            with self.assertRaises(RuntimeError):
                attest_worker_mounts(info(root), bundle)
            writable = info(); writable['Mounts'][0]['RW'] = True
            with self.assertRaises(RuntimeError):
                attest_worker_mounts(writable, bundle)
            extra = info(); extra['Mounts'].append({'Type': 'bind', 'Destination': '/backend', 'RW': False})
            with self.assertRaises(RuntimeError):
                attest_worker_mounts(extra, bundle)


if __name__ == '__main__':
    unittest.main()
