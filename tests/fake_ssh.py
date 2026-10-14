"""Stand-in for ssh.exe: hosts and commands are scripted, state lives in FAKE_SSH_STATE."""
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
while args and args[0] in ('-o', '-p'):
    args = args[2:]
host, command = args[0], args[1]
state = Path(os.environ['FAKE_SSH_STATE'])
with (state / 'calls.log').open('a', encoding='utf-8') as log:
    log.write(f'{host}\t{command}\n')
if host == 'down':
    sys.stderr.write('ssh: connect to host down port 22: Connection refused\r\n')
    sys.exit(255)
if host == 'newhost':
    sys.stderr.write('Host key verification failed.\r\n')
    sys.exit(255)
if host == 'slow':
    time.sleep(30)
running = state / f'{host}.running'
# systemd commands from the registration helper map onto the scripted ones.
words = command.replace('sudo ', '').split()
if words[:2] == ['systemctl', 'start']:
    command = 'start-app'
elif words[:2] == ['systemctl', 'stop']:
    command = 'stop-app'
elif words[:2] == ['systemctl', 'is-active']:
    command = 'status-app'
elif words[:1] == ['journalctl']:
    command = 'logs-app'
if command == 'true':
    sys.exit(0)
if command == 'start-app':
    running.touch()
    print('started')
elif command == 'start-later':
    print('accepted')
elif command == 'stop-app':
    running.unlink(missing_ok=True)
elif command == 'status-app':
    sys.exit(0 if running.exists() else 3)
elif command == 'logs-app':
    print('line 1\nline 2 한글')
elif command == 'sudo-fail':
    sys.stderr.write('sudo: a terminal is required to read the password\n')
    sys.exit(1)
else:
    sys.stderr.write(f'unknown command: {command}\n')
    sys.exit(127)
