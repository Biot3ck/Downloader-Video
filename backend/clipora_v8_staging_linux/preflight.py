"""Read-only host eligibility check. Never provisions, pulls, or enables egress."""
import argparse
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys


def run_json(args, *, env=None):
    result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=True, env=env)
    return json.loads(result.stdout)


def evaluate(facts):
    checks = {
        'native_linux_host': facts.get('host_system') == 'Linux',
        'local_unix_docker_endpoint': facts.get('local_docker_endpoint') is True,
        'linux_engine_outside_docker_desktop': (
            facts.get('engine_os_type') == 'linux'
            and facts.get('engine_desktop') is False
        ),
        'docker_seccomp_available': facts.get('seccomp') is True,
        'docker_cgroup_v2': facts.get('cgroup_version') == '2',
        'private_regular_state_directory': facts.get('private_state') is True,
        'state_on_persistent_filesystem': facts.get('persistent_filesystem') is True,
    }
    return {
        'schema_version': 1,
        'scope': 'host_preflight_only',
        'checks': checks,
        'host_fixture_eligible': all(checks.values()),
        'blocked_checks': [key for key, passed in checks.items() if not passed],
        'unverified_release_requirements': [
            'enforced_total_host_quota_including_DB_WAL_logs_artifacts_and_temp',
            'sustained_load_disk_full_restart_and_controller_crash',
            'production_DNS_IP_binding_and_public_domain_CDN_redirect_policy',
            'production_TLS_service_identity_and_certificate_lifecycle',
            'runtime_non_root_readonly_cap_drop_and_no_new_privileges',
            'dependency_and_OS_vulnerability_review',
            'authorized_live_tests_for_all_four_platforms',
            'release_and_deployment_approval',
        ],
        'production_ready': False,
        'public_egress_enabled': False,
    }


def state_is_private(path):
    try:
        path = Path(path).absolute()
        if any(p.is_symlink() for p in (path, *path.parents)):
            return False
        info = path.stat()
        return (stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o700)
    except OSError:
        return False


def collect(state):
    facts = {'host_system': platform.system(), 'private_state': state_is_private(state)}
    errors = []
    # Docker Desktop runs a Linux VM; its daemon metadata cannot attest to a
    # native Linux staging host. Also never contact a remote configured daemon.
    if facts['host_system'] != 'Linux':
        return facts, ['native_linux_required_no_docker_probe_performed']
    try:
        endpoint_override = os.environ.get('DOCKER_HOST')
        if os.environ.get('DOCKER_CONTEXT') or endpoint_override is None:
            context = run_json(['docker', 'context', 'inspect'])
            if len(context) != 1:
                raise ValueError('Ambiguous context')
            endpoint = context[0]['Endpoints']['docker']['Host']
        else:
            endpoint = endpoint_override
        facts['local_docker_endpoint'] = (
            isinstance(endpoint, str) and endpoint.startswith('unix:///')
            and not any(c in endpoint for c in ('\n', '\r', '\x00', '?', '#'))
        )
        if not facts['local_docker_endpoint']:
            return facts, ['remote_or_unsupported_docker_endpoint_not_contacted']
        pinned_env = dict(os.environ)
        pinned_env.pop('DOCKER_HOST', None)
        pinned_env.pop('DOCKER_CONTEXT', None)
        info = run_json(['docker', '--host', endpoint, 'info', '--format', '{{json .}}'], env=pinned_env)
        facts['engine_os_type'] = info.get('OSType')
        facts['engine_desktop'] = any('docker desktop' in str(info.get(key, '')).lower()
                                      or 'docker-desktop' in str(info.get(key, '')).lower()
                                      for key in ('OperatingSystem', 'Name'))
        security = info.get('SecurityOptions', [])
        facts['seccomp'] = any(str(value).split(',')[0] == 'name=seccomp' for value in security)
        facts['cgroup_version'] = str(info.get('CgroupVersion', ''))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        errors.append('docker_metadata_unavailable_or_invalid')
    if facts['private_state']:
        try:
            mount = run_json(['findmnt', '--json', '--target', str(Path(state).absolute()),
                              '--output', 'FSTYPE,OPTIONS'])['filesystems']
            if len(mount) != 1:
                raise ValueError('Ambiguous mount')
            fs = mount[0]
            facts['persistent_filesystem'] = fs['fstype'] in ('ext4', 'xfs', 'btrfs')
            # Mount flags are a diagnostic, never evidence that a directory's
            # quota is configured or that ENOSPC enforcement has been tested.
            options = set(fs.get('options', '').split(','))
            facts['quota_mount_option_seen'] = bool(options & {'prjquota', 'pquota', 'usrquota', 'grpquota'})
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            errors.append('state_mount_metadata_unavailable_or_invalid')
    return facts, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True, help='Existing private staging directory; never created')
    parser.add_argument('--report', type=Path, help='New report file; refuses overwrite')
    args = parser.parse_args()
    facts, errors = collect(args.state)
    report = evaluate(facts)
    report['probe_errors'] = errors
    report['quota_mount_option_seen'] = facts.get('quota_mount_option_seen')
    payload = json.dumps(report, indent=2) + '\n'
    if args.report:
        fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as output:
            output.write(payload)
    print(payload, end='')
    return 0 if report['host_fixture_eligible'] else 2


if __name__ == '__main__':
    sys.exit(main())
