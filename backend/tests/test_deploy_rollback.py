"""Execute the deploy script with a fake gcloud: no cloud access or Docker mutations."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('mode', ['healthy', 'start_failure', 'health_failure', 'health_ssh_failure', 'preflight_failure'])
def test_failed_container_start_and_health_checks_reach_rollback(tmp_path, mode):
    gcloud = tmp_path / 'gcloud'
    gcloud.write_text(f'#!{sys.executable}\n' + r'''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
mode = os.environ['FAKE_DEPLOY_MODE']
if args[:2] == ['auth', 'list']:
    print('fake-authenticated-account')
    sys.exit(0)
command = args[args.index('--command') + 1]
with open(os.environ['FAKE_COMMAND_LOG'], 'a') as log:
    log.write(json.dumps(command) + '\n')
if 'PREFLIGHT' in command or 'preflight' in command:
    print('fail' if mode == 'preflight_failure' else '200')
elif 'PREV=' in command:
    print('rolled-back')
elif command.startswith('docker run -d'):
    if mode == 'start_failure':
        sys.exit(125)
    print('new-container-id')
elif 'for i in' in command and 'curl' in command:
    if mode == 'health_ssh_failure':
        sys.exit(255)
    print('500' if mode == 'health_failure' else '200')
elif 'NEEDS_MIGRATION' in command or "echo 'yes'" in command:
    print('no')
else:
    print('ok')
''')
    gcloud.chmod(0o755)
    command_log = tmp_path / 'commands.jsonl'
    env = {**os.environ, 'PATH': f'{tmp_path}{os.pathsep}{os.environ["PATH"]}',
           'FAKE_DEPLOY_MODE': mode, 'FAKE_COMMAND_LOG': str(command_log)}
    result = subprocess.run(['bash', str(ROOT / 'scripts/deploy-gcp.sh'), '--gamma', '--skip-build'],
                            env=env, capture_output=True, text=True, timeout=10)
    commands = [json.loads(line) for line in command_log.read_text().splitlines()]
    output = result.stdout + result.stderr
    swaps = [command for command in commands if command.startswith('docker run -d')]
    rollbacks = [command for command in commands if 'PREV=' in command]
    if mode == 'healthy':
        assert result.returncode == 0, output
        assert len(swaps) == 1
        assert not rollbacks
    elif mode == 'preflight_failure':
        assert result.returncode == 1, output
        assert not swaps and not rollbacks, 'preflight must leave the live service alone'
    else:
        assert result.returncode == 1, output
        assert len(swaps) == len(rollbacks) == 1, output
        assert 'rollback succeeded' in output
        assert '--memory=768m --cpus=1.0' in rollbacks[0]
