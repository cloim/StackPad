"""Engine messages are written in Korean and translated when a client prefers English.

Messages with values use numbered placeholders here; the Korean text at the raise site is matched back to its template.
"""
import ctypes
import os
import re

EN = {
    # Docker
    '도커 컨테이너 이름 또는 ID를 입력해 주세요.': 'Enter a Docker container name or ID.',
    'Docker 데몬 연결과 컨테이너 상태를 확인해 주세요.': 'Check the Docker daemon connection and the container state.',
    '서비스 이름을 한 줄로 입력해 주세요.': 'Enter the service name on one line.',
    '제공된 패드 색상을 선택해 주세요.': 'Choose one of the pad colors.',
    'Docker 설치와 PATH 설정을 확인해 주세요.': 'Check that Docker is installed and on PATH.',
    'Docker 응답 시간이 초과되었습니다. 데몬 연결을 확인해 주세요.': 'Docker did not respond in time. Check the daemon connection.',
    '일시 정지된 컨테이너입니다.': 'The container is paused.',
    '컨테이너 작업을 완료한 뒤 다시 시도해 주세요.': 'Wait for the container operation to finish, then try again.',
    '컨테이너 실행 결과를 확인해 주세요.': 'Check the container result.',
    # Engine
    '서비스를 찾을 수 없습니다.': 'Service not found.',
    '한 줄로 입력해 주세요.': 'Enter it on one line.',
    '존재하는 폴더의 전체 경로를 입력해 주세요.': 'Enter the full path of an existing folder.',
    '포트 {0}를 다른 프로그램이 사용 중입니다. 기존 서버를 확인해 주세요.': 'Another program is using port {0}. Check the existing server.',
    '작업 폴더를 확인해 주세요.': 'Check the working folder.',
    'VS Code 설치 위치를 확인해 주세요.': 'Could not find VS Code. Check the installation.',
    '상태 확인 URL은 로컬 HTTP 또는 HTTPS 주소로 입력해 주세요.': 'Enter a local HTTP or HTTPS address for the health check URL.',
    '외부 실행의 종료를 확인하지 못했습니다. 포트 사용 상태를 확인해 주세요.': 'Could not confirm that the outside server stopped. Check the port.',
    '그룹 관리에서 패드 위치를 변경해 주세요.': 'Move the pad from its group instead.',
    '이 패드에는 이미 서비스가 등록되어 있습니다.': 'This pad already has a service.',
    '그룹 관리에서 구성을 분리한 다음 삭제해 주세요.': 'Separate the service from its group before deleting it.',
    '서비스를 중지한 다음 삭제해 주세요.': 'Stop the service before deleting it.',
    '이미 실행 중인 서비스입니다.': 'The service is already running.',
    '서비스 실행 실패: WMI {0}': 'Failed to start the service: WMI {0}',
    '원격 서버 패드는 VS Code로 열 수 없습니다.': 'Remote server pads cannot be opened in VS Code.',
    '응답을 확인하고 있습니다.': 'Waiting for a response.',
    '이미 등록된 컨테이너입니다.': 'This container is already registered.',
    '서비스를 중지한 다음 설정을 변경해 주세요.': 'Stop the service before changing its settings.',
    '포트 {0}를 사용 중입니다. 기존 서버를 확인해 주세요.': 'Port {0} is in use. Check the existing server.',
    '종료에 실패했습니다. 프로세스 권한을 확인해 주세요.': 'Could not stop it. Check the process permissions.',
    '프로세스 종료 상태를 확인해 주세요.': 'Check whether the process stopped.',
    '명령이 곧바로 종료되었습니다. 로그를 확인해 주세요.': 'The command exited right away. Check the logs.',
    '실행 중인 서비스 로그의 새 저장 위치를 확인해 주세요.': 'Check the new location of the running service logs.',
    '프로세스가 종료되었습니다. 로그를 확인해 주세요.': 'The process exited. Check the logs.',
    '재시작 한도를 초과했습니다. 로그를 확인해 주세요.': 'Exceeded restart limit. Check the logs.',
    '재시작 대기 중': 'Waiting to restart',
    '재시작 중': 'Restarting',
    '응답 이상이 감지되었습니다.': 'Unhealthy response detected.',
    # Folder picker
    'Windows PC에서 폴더를 선택해 주세요.': 'Choose the folder on the Windows PC.',
    '폴더 선택 창을 다시 열어 주세요.': 'Open the folder picker again.',
    '폴더 선택을 다시 시도해 주세요.': 'Try choosing the folder again.',
    '폴더 선택 창을 열지 못했습니다. 다시 시도해 주세요.': 'Could not open the folder picker. Try again.',
    # Google sign-in
    'Google 계정 이메일을 확인해 주세요.': 'Check the Google account email.',
    'OAuth 클라이언트 ID를 확인해 주세요. `.apps.googleusercontent.com`으로 끝나야 합니다.': 'Check the OAuth client ID. It ends with `.apps.googleusercontent.com`.',
    'OAuth 클라이언트 보안 비밀번호를 입력해 주세요.': 'Enter the OAuth client secret.',
    '이미 허용된 계정입니다.': 'This account is already allowed.',
    '허용 계정은 20개까지 등록할 수 있습니다.': 'You can allow up to 20 accounts.',
    '소유자 계정은 삭제할 수 없습니다.': 'The owner account cannot be removed.',
    '허용 계정을 찾을 수 없습니다.': 'Allowed account not found.',
    'Google 로그인 설정을 먼저 마쳐 주세요.': 'Set up Google sign-in first.',
    '로그인 시간이 지났습니다. 다시 로그인해 주세요.': 'Sign-in timed out. Please sign in again.',
    'Google 로그인을 확인하지 못했습니다. OAuth 클라이언트 설정과 리디렉션 주소를 확인해 주세요.': 'Google sign-in failed. Check the OAuth client and its redirect URIs.',
    'Google 로그인 정보를 확인하지 못했습니다.': 'Could not verify the Google sign-in.',
    '연결 코드를 만든 계정이 더 이상 허용되지 않습니다.': 'The account that created this code is no longer allowed.',
    '{0} 계정은 허용되지 않았습니다. PC의 환경 설정에서 계정을 추가해 주세요.': '{0} is not allowed. Add the account in Settings on the PC.',
    '로그인 요청이 많습니다. 잠시 후 다시 시도해 주세요.': 'Too many sign-in attempts. Try again shortly.',
    'PC 앱에서 로그인을 다시 시작해 주세요.': 'Start signing in again from the PC app.',
    '연결 코드가 만료되었습니다. PC에서 새 QR 코드를 띄워 주세요.': 'The code has expired. Show a new QR code on the PC.',
    'StackPad가 실행 중인 PC에서 먼저 로그인해 주세요.': 'Sign in on the PC running StackPad first.',
    # Groups
    '그룹을 찾을 수 없습니다.': 'Group not found.',
    '그룹 이름을 한 줄로 입력해 주세요.': 'Enter the group name on one line.',
    '구성을 중복으로 선택했습니다.': 'A service was chosen twice.',
    '패드를 찾을 수 없습니다.': 'Pad not found.',
    '패드 설정에서 열 주소를 입력해 주세요.': 'Enter the address to open in the pad settings.',
    '그룹 작업이 진행 중입니다. 완료 후 다시 시도해 주세요.': 'A group operation is running. Try again when it finishes.',
    '도메인 URL은 http 또는 https 주소로 입력해 주세요.': 'Enter an http or https address for the domain URL.',
    '로컬 URL은 localhost 또는 127.0.0.1 주소로 입력해 주세요.': 'Enter a localhost or 127.0.0.1 address for the local URL.',
    '전체 패드의 설정에서 삭제해 주세요.': 'Delete it from the pad settings.',
    '구성이 속한 패드의 설정에서 변경해 주세요.': 'Change it from the settings of its pad.',
    '이 패드에 속한 구성만 편집할 수 있습니다.': 'Only services in this pad can be edited.',
    '구성별 이동 대신 전체 패드를 이동해 주세요.': 'Move the whole pad instead of one service.',
    '빈 패드로 이동해 주세요.': 'Drop it on an empty pad.',
    '같은 패드셋의 구성으로 패드를 만들어 주세요.': 'Build the pad from services in the same pad set.',
    '분리할 구성에 필요한 빈 패드를 확보해 주세요.': 'Free up pads for the services you are separating.',
    '그룹을 중지한 다음 해제해 주세요.': 'Stop the group before separating it.',
    '구성별로 사용할 빈 패드를 확보해 주세요.': 'Free up a pad for each service.',
    '패드를 중지한 다음 삭제해 주세요.': 'Stop the pad before deleting it.',
    '패드를 중지한 다음 설정을 변경해 주세요.': 'Stop the pad before changing its settings.',
    '그룹을 중지한 다음 구성을 변경해 주세요.': 'Stop the group before changing its services.',
    '다른 그룹에 속한 구성입니다.': 'This service belongs to another group.',
    '그룹 작업이 진행 중입니다.': 'A group operation is running.',
    '원격 서버의 호스트와 명령을 입력해 주세요.': 'Enter the remote host and commands.',
    '{0}: 실행에 실패했습니다. 로그를 확인해 주세요.': '{0}: failed to start. Check the logs.',
    '{0}\n시작한 구성의 종료 상태를 확인해 주세요: {1}': '{0}\nCheck whether these started services stopped: {1}',
    '{0}: 실행이 종료되었습니다. 로그를 확인해 주세요.': '{0}: exited. Check the logs.',
    '{0}: 준비 확인 시간이 초과되었습니다.': '{0}: timed out waiting to be ready.',
    # API
    '로그인해 주세요.': 'Please sign in.',
    '설정된 외부 주소로 접속해 주세요.': 'Open StackPad at its configured remote address.',
    '화면 빌드를 확인해 주세요.': 'The web build is missing.',
    'StackPad가 실행 중인 PC에서 설정해 주세요.': 'Change this on the PC running StackPad.',
    '원격 서버 패드는 이 PC에서 접속해 등록하고 변경해 주세요.': 'Add and change remote server pads from this PC.',
    'PC 앱 로그인은 이 PC에서만 진행할 수 있습니다.': 'PC app sign-in only works on this PC.',
    'Google 로그인을 취소했거나 시간이 지났습니다. 다시 로그인해 주세요.': 'Google sign-in was cancelled or timed out. Please sign in again.',
    '로그인을 마쳤어요': 'You are signed in',
    'StackPad 앱으로 돌아가 주세요. 이 창은 닫아도 됩니다.': 'Go back to the StackPad app. You can close this window.',
    '먼저 Tailscale로 외부 주소를 연결해 주세요.': 'Connect a remote address with Tailscale first.',
    '위젯 연결을 다시 설정해 주세요.': 'Connect the widget again.',
    '위젯 토큰은 알림만 수신할 수 있습니다.': 'Widget tokens can only receive alerts.',
    '이 PC에서 접속한 화면에서 열 수 있습니다.': 'This opens only from the screen on this PC.',
    '이 PC에서 접속한 화면에서 저장 폴더를 선택해 주세요.': 'Choose the storage folder from the screen on this PC.',
    '열려 있는 폴더 선택 창을 먼저 닫아 주세요.': 'Close the open folder picker first.',
    '로그인을 시작하지 못했어요': 'Could not start sign-in',
    '로그인하지 못했어요': 'Sign-in failed',
    '로그인을 시작한 주소에서 다시 로그인해 주세요.': 'Sign in again from the address where you started.',
    '같은 앱 화면에서 요청해 주세요.': 'Send the request from the StackPad screen.',
    '잠시 후 다시 시도해 주세요.': 'Try again shortly.',
    'Google에 연결하지 못했습니다. 네트워크를 확인해 주세요.': 'Could not reach Google. Check the network.',
    # Pad sets
    '패드셋을 선택해 주세요.': 'Choose a pad set.',
    '패드셋 이름을 한 줄로 입력해 주세요.': 'Enter the pad set name on one line.',
    '현재 패드셋 전체를 한 번씩 지정해 주세요.': 'List every current pad set exactly once.',
    '다른 패드셋 이름을 입력해 주세요.': 'Enter a different pad set name.',
    '패드셋을 하나 이상 유지해 주세요.': 'Keep at least one pad set.',
    '패드를 다른 셋으로 옮기거나 삭제한 다음 빈 패드셋을 삭제해 주세요.': 'Move or delete its pads before deleting the pad set.',
    # Suggestions
    '스캔 폴더를 1개 이상 10개 이하로 지정해 주세요.': 'Choose between 1 and 10 scan folders.',
    '숨길 추천을 확인해 주세요.': 'Check the suggestion to hide.',
    '존재하는 폴더의 전체 경로를 입력해 주세요: {0}': 'Enter the full path of an existing folder: {0}',
    '숨긴 추천을 찾을 수 없습니다.': 'Hidden suggestion not found.',
    # Remote servers
    '종료 코드 {0}': 'Exit code {0}',
    '{0}\n터미널에서 ssh {1} 로 한 번 접속해 호스트 키를 등록해 주세요.': '{0}\nConnect once with `ssh {1}` in a terminal to save the host key.',
    '{0}\nSSH 키 인증과 ssh-agent 상태를 확인해 주세요.': '{0}\nCheck the SSH key and ssh-agent.',
    '{0}\n원격 서버의 sudoers에 이 명령을 비밀번호 없이 허용해 주세요.': '{0}\nAllow this command without a password in the server sudoers file.',
    '로그 명령이 등록되지 않았습니다. 패드 설정에서 로그 명령을 입력하면 여기에 표시됩니다.': 'No log command yet. Add one in the pad settings to see logs here.',
    '호스트는 SSH 설정의 별칭이나 user@host[:port] 형식으로 입력해 주세요.': 'Enter the host as an SSH config alias or user@host[:port].',
    '시작, 종료, 상태 명령을 입력해 주세요.': 'Enter the start, stop and status commands.',
    '{0}초 안에 응답이 없습니다.': 'No response within {0} seconds.',
    'ssh를 실행하지 못했습니다: {0}': 'Could not run ssh: {0}',
    '시작': 'start',
    '종료': 'stop',
    '{0}: 원격 {1} 명령이 실패했습니다.\n{2}': '{0}: the remote {1} command failed.\n{2}',
    '접속을 확인했습니다.': 'Connected successfully.',
    '상태 확인 URL은 사설망 주소나 등록한 호스트의 HTTP, HTTPS 주소로 입력해 주세요.': 'Use a private network address or the host address, over HTTP or HTTPS, for the health check URL.',
    '원격 명령을 처리하고 있습니다. 완료 후 다시 시도해 주세요.': 'A remote command is running. Try again when it finishes.',
    '시작 명령 뒤 실행 상태를 확인하지 못했습니다. 상태 명령과 로그를 확인해 주세요.': 'Could not confirm the service started. Check the status command and logs.',
    # Sessions and storage
    '연결된 기기를 찾을 수 없습니다.': 'Connected device not found.',
    '설정과 로그 저장 폴더를 확인해 주세요.': 'Check the settings and logs folder.',
    '존재하는 폴더의 전체 경로를 선택해 주세요.': 'Choose the full path of an existing folder.',
    '현재 저장 폴더와 겹치지 않는 별도의 빈 폴더를 선택해 주세요.': 'Choose a separate empty folder that does not overlap the current one.',
    '기존 파일을 보존할 수 있도록 빈 폴더를 선택해 주세요.': 'Choose an empty folder so existing files stay safe.',
    '저장 폴더를 변경하지 못했습니다. 기존 위치와 데이터는 유지됩니다. 쓰기 권한과 여유 공간을 확인한 뒤 빈 폴더를 선택해 주세요.': 'Could not change the folder. The current folder and data are unchanged. Check write access and free space, then choose an empty folder.',
    # Tailscale
    'Tailscale을 설치해 주세요.': 'Install Tailscale.',
    'Tailscale에 로그인하고 연결해 주세요.': 'Sign in to Tailscale and connect.',
    '비어 있는 Tailscale HTTPS 포트를 찾지 못했습니다.': 'No free Tailscale HTTPS port was found.',
    'Tailscale 명령을 실행하지 못했습니다.': 'Could not run the Tailscale command.',
    # Usage and widgets
    'CLI 로그인 필요': 'Sign in to the CLI',
    'CLI 사용 시 갱신': 'Updates when you use the CLI',
    '사용량 조회 실패': 'Usage unavailable',
    'Antigravity 실행 후 표시': 'Shown after running Antigravity',
    '위젯 연결 기기가 너무 많습니다. 사용하지 않는 기기를 해제해 주세요.': 'Too many widget devices. Disconnect ones you no longer use.',
    '위젯 연결을 찾지 못했습니다.': 'Widget connection not found.',
    # Command line
    '명령 형식을 확인해 주세요: {0}': 'Check the command: {0}',
    'stackpad-cli help로 사용법을 볼 수 있습니다.': 'Run stackpad-cli help to see the usage.',
    'JSON 형식을 확인해 주세요: {0}': 'Check the JSON: {0}',
    '패드 설정 JSON은 객체로 입력해 주세요.': 'Write the pad settings as a JSON object.',
    '패드셋을 찾을 수 없습니다: {0}': 'Pad set not found: {0}',
    '패드를 찾을 수 없습니다: {0}': 'Pad not found: {0}',
    '구성을 찾을 수 없습니다: {0}': 'Component not found: {0}',
    '같은 이름의 패드가 여러 개입니다. ID로 지정해 주세요: {0}': 'Several pads have this name. Use an ID: {0}',
    '여러 구성을 가진 패드는 --json으로 구성을 지정해 주세요.': 'Set the components of a pad with several components with --json.',
    '패드셋에 빈 슬롯이 없습니다.': 'The pad set has no free slot.',
    '--name으로 패드 이름을 입력해 주세요.': 'Enter the pad name with --name.',
    '--command, --container 또는 --json으로 구성을 입력해 주세요.': 'Enter the component with --command, --container or --json.',
}

# Text written to Windows or into files follows the Windows display language instead of a browser.
SYSTEM = {
    'StackPad 자동 실행': 'Start StackPad',
    '폴더를 선택해 주세요.': 'Choose a folder.',
    '설정과 로그를 저장할 빈 폴더를 선택해 주세요.': 'Choose an empty folder for settings and logs.',
    '기본': 'Default',
    '서비스 시작': 'Service started',
    '로그 명령 실패': 'Log command failed',
}

_TEMPLATES = [(re.compile('^' + re.sub(r'\\\{(\d+)\\\}', r'(?P<p\1>.*?)', re.escape(key)) + '$', re.S), value)
              for key, value in EN.items() if re.search(r'\{\d+\}', key)]
_VALUE_PREFIX = 'Value error, '


def translate(text, lang):
    if lang != 'en' or not isinstance(text, str) or not text:
        return text
    if text.startswith(_VALUE_PREFIX):
        return _VALUE_PREFIX + translate(text[len(_VALUE_PREFIX):], lang)
    if text in EN:
        return EN[text]
    for pattern, english in _TEMPLATES:
        match = pattern.match(text)
        if match:
            values = {name[1:]: translate(value, lang) for name, value in match.groupdict().items()}
            return re.sub(r'\{(\d+)\}', lambda m: values.get(m.group(1), ''), english)
    return text


FIELDS = {'detail', 'message', 'error', 'msg'}


def translate_payload(data, lang):
    """Translate message fields anywhere in a JSON payload, leaving user data alone."""
    if lang != 'en':
        return data
    if isinstance(data, dict):
        return {key: translate(value, lang) if key in FIELDS and isinstance(value, str) else translate_payload(value, lang) for key, value in data.items()}
    if isinstance(data, list):
        return [translate_payload(item, lang) for item in data]
    return data


def request_lang(headers):
    chosen = (headers.get('x-stackpad-lang') or '').lower()
    if chosen in ('ko', 'en'):
        return chosen
    accepted = (headers.get('accept-language') or '').strip().lower()
    if accepted:
        return 'ko' if accepted.startswith('ko') else 'en'
    return system_lang()


def system_lang():
    if os.environ.get('STACKPAD_LANG') in ('ko', 'en'):
        return os.environ['STACKPAD_LANG']
    try:
        # 0x12 is the Korean primary language id.
        return 'ko' if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x12 else 'en'
    except (AttributeError, OSError):
        return 'en'


def system_text(korean):
    return korean if system_lang() == 'ko' else SYSTEM.get(korean, korean)


# The command line help lives in cli.py in Korean; cli.py pairs it with these.
CLI_HELP = {
    'main': '''StackPad command line

Usage: stackpad-cli <command> [options]

  help [padset|pad]          Help
  version                    Engine version

  padset list                Pad sets with their pad count and free slots
  padset add <name>          Add a pad set
  padset rename <padset> <new name>
  padset order <padset>...   Put these first in this order and keep the rest as they are
  padset delete <padset>     Delete an empty pad set

  pad list [--padset P]      Pads and their status
  pad show <pad>             Pad details; its input can be passed back to --json as is
  pad add [options]          Add a pad
  pad update <pad> [options] Change a pad; only the given options change
  pad move <pad> --slot S [--padset P]
  pad delete <pad>           Delete a stopped pad
  pad start <pad> [--takeover]
  pad stop <pad>
  pad restart <pad>
  pad logs <pad> [--component C]

Pads and pad sets are named by ID or by name (case does not matter).
Results are printed as JSON; only pad logs and help print text.
Exit codes: 0 success, 1 failed, 2 wrong command, 3 engine not reachable''',
    'pad': '''pad add and pad update options

  --name N                  Pad name (required for add)
  --padset P                Pad set; the first pad set by default
  --slot S                  0 to 15, row by row from the top left. The first free slot by default
  --color C                 Pad color
  --autostart / --no-autostart       Start with Windows
  --wait-ready / --no-wait-ready     Wait for each component to be ready when a group starts
  --domain-url U, --local-url U      Addresses in the pad menu; an empty value clears them

Single component options
  --command CMD --cwd DIR   Local command and working folder. --cwd defaults to the current folder
  --port N                  Port to check; none clears it
  --health-url U            Local health check address
  --container NAME          Docker container
  --restart never|on-failure  Auto-restart policy on failure
  --restart-max N           Maximum restart attempts in 10 min (default 3)

--json FILE|-  The whole pad as a JSON file or standard input. Use it for group pads and remote server pads.
  {"name": "App", "components": [{"kind": "local", "name": "API", "command": "uv run main.py", "cwd": "D:/app", "port": 8000},
                                {"kind": "remote", "name": "DB", "remote": {"host": "nas", "start": "...", "stop": "...", "status": "..."}}]}
  In update, a component without its id becomes a new component. Editing the input from pad show is the safe way.

Colors:''',
    'padset': '''padset commands

  padset list
  padset add <name>
  padset rename <padset> <new name>
  padset order <padset>...
  padset delete <padset>     Move or delete its pads first''',
}
