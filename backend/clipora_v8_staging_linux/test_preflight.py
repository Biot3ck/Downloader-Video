import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from clipora_v8_staging_linux.preflight import collect, evaluate, state_is_private


class PreflightTests(unittest.TestCase):
    def good(self):
        return {'host_system': 'Linux', 'local_docker_endpoint': True,
                'engine_os_type': 'linux', 'engine_desktop': False,
                'seccomp': True, 'cgroup_version': '2', 'private_state': True,
                'persistent_filesystem': True}

    def test_host_eligibility_never_releases_public_gate(self):
        report = evaluate(self.good())
        self.assertTrue(report['host_fixture_eligible'])
        self.assertFalse(report['production_ready'])
        self.assertFalse(report['public_egress_enabled'])
        self.assertGreater(len(report['unverified_release_requirements']), 6)

    def test_every_missing_or_false_requirement_blocks(self):
        for key in self.good():
            for value in (None, True if key == 'engine_desktop' else False, 'unexpected'):
                with self.subTest(key=key, value=value):
                    facts = self.good(); facts[key] = value
                    self.assertFalse(evaluate(facts)['host_fixture_eligible'])

    def test_macos_skips_docker_entirely(self):
        with patch('platform.system', return_value='Darwin'), patch(
                'clipora_v8_staging_linux.preflight.run_json') as probe:
            facts, errors = collect('/missing')
        probe.assert_not_called()
        self.assertFalse(evaluate(facts)['host_fixture_eligible'])
        self.assertTrue(errors)

    def test_remote_docker_never_contacted(self):
        for endpoint in ('ssh://staging', 'tcp://127.0.0.1:2375', 'https://host:2376'):
            with self.subTest(endpoint=endpoint), patch('platform.system', return_value='Linux'), patch.dict(
                    os.environ, {'DOCKER_HOST': endpoint, 'DOCKER_CONTEXT': ''}), patch(
                    'clipora_v8_staging_linux.preflight.run_json') as probe:
                facts, errors = collect('/missing')
                probe.assert_not_called()
                self.assertFalse(facts['local_docker_endpoint'])
                self.assertTrue(errors)

    def test_context_takes_precedence_and_info_is_pinned(self):
        metadata = [{'Endpoints': {'docker': {'Host': 'unix:///run/docker.sock'}}}]
        engine = {'OSType': 'linux', 'OperatingSystem': 'Linux', 'Name': 'staging',
                  'SecurityOptions': ['name=seccomp,profile=builtin'], 'CgroupVersion': '2'}
        with patch('platform.system', return_value='Linux'), patch.dict(os.environ, {
                'DOCKER_CONTEXT': 'local', 'DOCKER_HOST': 'ssh://remote'}), patch(
                'clipora_v8_staging_linux.preflight.run_json', side_effect=[metadata, engine]) as probe:
            facts, _ = collect('/missing')
        args, kwargs = probe.call_args_list[1]
        self.assertEqual(args[0][0:3], ['docker', '--host', 'unix:///run/docker.sock'])
        self.assertNotIn('DOCKER_CONTEXT', kwargs['env'])
        self.assertNotIn('DOCKER_HOST', kwargs['env'])
        self.assertTrue(facts['seccomp'])

    def test_private_state_rejects_shared_and_symlink_paths(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root).resolve(); state = root/'state'; state.mkdir(mode=0o700)
            self.assertTrue(state_is_private(state))
            link = root/'link'; link.symlink_to(state, target_is_directory=True)
            self.assertFalse(state_is_private(link))
            state.chmod(0o755)
            self.assertFalse(state_is_private(state))

    def test_docker_desktop_linux_metadata_is_not_native_attestation(self):
        with patch('platform.system', return_value='Linux'), patch.dict(os.environ, {
                'DOCKER_HOST': 'unix:///run/docker.sock', 'DOCKER_CONTEXT': ''}), patch(
                'clipora_v8_staging_linux.preflight.run_json', return_value={
                    'OSType': 'linux', 'OperatingSystem': 'Docker Desktop', 'CgroupVersion': '2',
                    'SecurityOptions': ['name=seccomp,profile=builtin']}):
            facts, _ = collect('/missing')
        self.assertTrue(facts['engine_desktop'])
        self.assertFalse(evaluate(facts)['host_fixture_eligible'])

    def test_quota_mount_flags_never_prove_quota_enforcement(self):
        facts = self.good(); facts['quota_mount_option_seen'] = True
        self.assertIn('enforced_total_host_quota_including_DB_WAL_logs_artifacts_and_temp',
                      evaluate(facts)['unverified_release_requirements'])


if __name__ == '__main__':
    unittest.main()
