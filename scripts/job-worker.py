import json
import os
import subprocess
import sys
from pathlib import Path

job = Path(sys.argv[1]).resolve()
spec = json.loads(job.read_text(encoding='utf-8-sig'))
result = {'state': 'running', 'pid': os.getpid(), 'commands': spec['commands'], 'cwd': spec['cwd']}
state = job.with_suffix('.state.json')
state.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
code = 0
try:
    if not isinstance(spec['commands'], list) or not all(isinstance(command, list) and command and all(isinstance(arg, str) for arg in command) for command in spec['commands']):
        raise ValueError('commands must be an array of command argument arrays')
    with job.with_suffix('.log').open('w', encoding='utf-8') as output:
        for command in spec['commands']:
            output.write('COMMAND ' + repr(command) + '\n')
            output.flush()
            code = subprocess.run(command, cwd=spec['cwd'], stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, creationflags=0x08000000).returncode
            if code:
                break
except Exception as error:
    result['error'] = str(error)
    code = 1
result.update(state='completed' if code == 0 else 'failed', exit_code=code)
state.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
sys.exit(code)
