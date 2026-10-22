# StackPad

[English](README.md)

StackPad는 Windows PC의 서버들을 버튼 패드로 바꿔 줍니다. 패드를 누르면 개발 서버, 여러 서비스 묶음, Docker 컨테이너, 원격 Linux 서버의 systemd 서비스가 켜지고, 다시 누르면 꺼집니다. 로그, 상태와 AI CLI 사용량을 PC와 휴대폰에서 확인할 수 있어요.

- 패드셋마다 16개의 패드, 패드셋은 원하는 만큼
- 로컬 명령, Docker 컨테이너, SSH 원격 서버를 단독 또는 그룹 패드로 묶어 순서대로 실행하고 역순으로 종료
- 여러 패드를 순차적으로 켜고 끄는 장면과 시간 및 요일별 자동 실행 예약
- 비정상 종료 시 지수 백오프 자동 재시작, 오류 줄 자동 감지, 즉각적인 장애 알림 (PC 토스트 알림과 Android 상시 포그라운드 알림)
- 실시간 SSE 푸시 갱신, 로그 증분 전송, 오류 줄 강조 및 필터링을 지원하는 로그 검색
- CPU 활동에 연동되는 숨쉬는 LED 링, 60칸 LCD 도트 매트릭스 스파크라인
- 프로젝트 폴더 아래에서 이미 실행 중인 서버를 등록 추천
- Google 계정으로 로그인, Tailscale로 휴대폰에서 PC에 접속
- Claude Code, Codex, Antigravity 사용 한도를 보여 주는 홈 화면 위젯이 있는 Android 앱
- 한국어와 영어 지원

## 준비물

- Windows 10 또는 11 (64비트). Microsoft Edge WebView2가 없으면 설치 파일이 함께 설치합니다.
- Google 계정과 직접 만드는 Google OAuth 클라이언트 (무료, 5분 정도, 아래 안내 참고)
- 선택: 외부 접속용 [Tailscale](https://tailscale.com/download) (PC와 휴대폰)
- 선택: 해당 기능을 쓸 때 Docker Desktop, VS Code, OpenSSH

## 설치

[Releases](https://github.com/cloim/StackPad/releases/latest)에서 내려받으세요.

| 파일 | 용도 |
|---|---|
| `StackPad_x.y.z_x64-setup.exe` | 설치 파일. 트레이 메뉴에서 스스로 업데이트합니다. |
| `StackPad-Windows-x64-portable.zip` | 압축을 풀고 `StackPad.exe`를 실행합니다. `StackPadEngine.exe`를 같은 폴더에 두세요. 새 버전은 트레이에서 내려받기 링크로 안내합니다. |
| `StackPad.apk` | Android 앱 (Android 8 이상) |

StackPad는 코드 서명을 하지 않아요. Windows SmartScreen이 "Windows의 PC 보호" 창을 띄우면 **추가 정보 > 실행**을 누르세요. 서명 없는 앱이 백그라운드 프로세스를 실행하면 일부 백신이 경고할 수 있으니, 그때는 StackPad를 허용해 주세요.

## 처음 실행

StackPad는 `http://127.0.0.1:48731`에서 작은 관리 엔진을 실행하고, 창을 닫아도 서비스를 계속 유지합니다. 처음 실행하면 다음 순서로 안내해요.

1. **외부 접속 (선택).** Tailscale이 설치되어 로그인되어 있으면 **연결** 버튼으로 `https://내PC.tailnet이름.ts.net` 같은 HTTPS 주소를 만들어요. 내 Tailscale 기기에서만 열 수 있고, 기존 `tailscale serve` 설정은 그대로 둡니다.
2. **Google 로그인 설정.** OAuth 클라이언트를 만듭니다.
   1. [Google Cloud Console > Google 인증 플랫폼 > 클라이언트](https://console.cloud.google.com/auth/clients)에서 프로젝트를 고르거나 새로 만듭니다.
   2. 인증 플랫폼 구성을 요청하면 대상을 **외부**로 고릅니다. **대상 > 테스트 사용자**에 로그인할 Google 계정을 모두 추가하세요. StackPad에는 이것으로 충분하고, 이메일 주소만 받는 앱이라 Google 검수도 필요 없어요.
      테스트 사용자 목록 없이 쓰려고 게시하려면 브랜딩에 홈페이지와 개인정보처리방침 링크가 필요합니다. `https://cloim.github.io/StackPad/`와 `https://cloim.github.io/StackPad/privacy.html`을 쓸 수 있어요.
   3. **클라이언트 만들기**에서 유형을 **웹 애플리케이션**으로 고르고, StackPad가 보여 주는 리디렉션 URI를 모두 추가합니다. 예: `http://127.0.0.1:48731/api/auth/google/callback`, `https://내PC.tailnet이름.ts.net/api/auth/google/callback`
   4. 클라이언트 ID와 보안 비밀번호를 StackPad에 붙여 넣습니다.
3. **PC에서 로그인.** PC에서 처음 로그인한 Google 계정이 소유자가 됩니다. 다른 계정은 **환경 설정 > 계정**에서 추가하세요.
4. **프로젝트 폴더.** 프로젝트를 모아 두는 폴더를 알려 주세요. 서비스 등록의 기본 작업 폴더이자 등록 추천이 살펴보는 폴더가 됩니다.

설정, 로그와 로그인 기록은 `%USERPROFILE%\.config\stackpad`에 저장합니다. 로그인할 때 Google과 주고받는 것 외에는 비밀값을 어디로도 보내지 않고, 로그인 세션은 해시로만 저장해요.

## 사용법

- 빈 패드(또는 **+**)를 눌러 서비스를 등록합니다. 실행 명령과 작업 폴더, Docker 컨테이너, 시작/종료/상태 명령이 있는 원격 서버 중에서 고르고, 서비스를 더 추가하면 그룹 패드가 됩니다.
- 자동 재시작 정책(`on-failure` 시 최대 재시도 횟수까지 지수 백오프)과 비정상 종료 장애 알림을 설정할 수 있어요.
- 여러 패드를 묶어 순서대로 실행하고 역순으로 종료하는 **장면**을 구성할 수 있습니다.
- **장면 > 예약**에서 원하는 시간과 요일에 패드나 장면이 자동으로 시작/종료되도록 일정을 등록합니다.
- 패드를 누르면 실행, 다시 누르면 종료합니다. 패드 메뉴에서 상세와 로그, 설정, 브라우저로 열기, VS Code로 열기를 고를 수 있어요.
- 실시간 로그 검색과 오류 줄 강조 기능을 제공하며, "오류만" 보기로 장애 원인을 빠르게 추적할 수 있습니다.
- CPU 부하에 따라 호흡하듯 빛나는 LED 링, 60칸 LCD 도트 매트릭스 스파크라인을 확인할 수 있어요.
- 패드를 끌어 위치를 바꿉니다. 터치 화면에서는 왼쪽 위 손잡이를 끄세요.
- StackPad 밖에서 실행한 서버는 **외부 실행**으로 표시되고, 누르면 StackPad가 넘겨받습니다.
- **환경 설정 > 일반**: 언어, Windows 로그인 시 자동 실행, 로그 보관 기간, AI 사용량, 저장 폴더
- 트레이 메뉴: 열기, 창 닫기(엔진과 서비스 유지), 완전 종료(서비스 유지 또는 모두 중지), 업데이트 설치

## 명령줄

`StackPad.exe` 옆에 설치되는 `stackpad-cli`로 스크립트나 AI 코딩 에이전트가 화면 없이 패드를 관리할 수 있어요. 설치 프로그램이 StackPad 폴더를 사용자 PATH에 추가하므로 설치 후 새 터미널을 여세요. `StackPad.exe`도 같은 명령을 받지만 창 앱이라서 출력을 파이프로 받을 때(Bash, Python)만 끝날 때까지 기다리므로, PowerShell과 cmd에서는 `stackpad-cli`를 쓰세요.

```powershell
stackpad-cli help                     # 전체 명령, help pad는 패드 옵션과 색상
stackpad-cli padset list              # 패드셋과 빈 슬롯
stackpad-cli padset add 업무
stackpad-cli pad add --name API --command "uv run main.py" --cwd D:\app --port 8000 --padset 업무 --restart on-failure
stackpad-cli pad list --padset 업무
stackpad-cli pad start API
stackpad-cli pad logs API
stackpad-cli pad update API --environment production  # 개발용과 운영용 환경 설정
stackpad-cli pad show API             # input 항목을 고쳐 pad update API --json - 로 넘길 수 있습니다
stackpad-cli scene add --name 개발스택 --pads API,Web
stackpad-cli scene start 개발스택
stackpad-cli schedule add --scene 개발스택 --action start --time 09:00 --days mon-fri
```

- 패드, 장면, 패드셋은 ID 또는 이름으로 지정합니다. 슬롯은 왼쪽 위부터 행 순서로 0~15입니다.
- 결과는 표준 출력에 JSON으로, 오류는 표준 오류로 나옵니다. 종료 코드는 0 성공, 1 실행 오류, 2 명령 형식 오류, 3 엔진 미실행입니다.
- 그룹 패드와 원격 서버 패드는 `--json 파일` 또는 `--json -`(표준 입력)로 JSON을 넘겨 지정합니다.
- 명령은 엔진이 `%USERPROFILE%\.config\stackpad`에 둔 토큰으로 실행 중인 엔진에 요청하므로, StackPad가 실행 중일 때 이 PC의 현재 Windows 사용자만 쓸 수 있어요. (`StackPad.exe --hidden`은 창 없이 시작합니다)

## 휴대폰

- **Android:** `StackPad.apk`를 설치하고 휴대폰의 Tailscale을 켭니다. PC에서 **환경 설정 > 계정 > 휴대폰 연결**의 QR 코드를 앱으로 찍으면 연결돼요. QR 코드는 5분 동안 한 번만 쓸 수 있습니다. 연결된 뒤에는 PC의 화면을 그대로 열기 때문에, PC를 업데이트하면 앱을 다시 설치하지 않아도 휴대폰 화면이 함께 바뀌어요. 연결된 휴대폰은 같은 화면에서 확인하고 해제합니다. 홈 화면을 길게 눌러 **에이전트 한도** 위젯을 추가하세요.
  - Android 앱은 백그라운드에서도 엔진과 상시 SSE 연결을 유지하는 포그라운드 서비스를 갖추어 장애 및 재시작 알림을 즉각 수신합니다. 안정적인 상시 연결을 위해 기기 설정에서 StackPad의 배터리 최적화 예외와 백그라운드 자동 실행을 허용해 주세요.
- **iPhone 등:** Safari나 Chrome에서 Tailscale 주소를 열고 Google로 로그인한 뒤 홈 화면에 추가하세요.

## AI 사용량 (선택)

PC에 로그인된 AI CLI(Claude Code, Codex, Antigravity)의 5시간, 1주일 사용 한도를 보여 줍니다. 기본은 꺼져 있고 **환경 설정 > 일반**에서 CLI별로 켤 수 있어요. 각 CLI가 저장해 둔 자격 증명을 읽기만 하고 비공개 사용량 API를 호출하므로, 해당 서비스가 바뀌면 숫자가 보이지 않을 수 있습니다.

## 원격 서버

원격 패드는 내 SSH 키로 명령을 실행합니다(`~/.ssh/config` 별칭 사용 가능). 서버에는 아무것도 설치하지 않아요. 처음 쓰는 호스트는 터미널에서 한 번 접속해 호스트 키를 저장하고, `sudo`가 필요한 명령은 서버의 sudoers에서 비밀번호 없이 허용해 주세요. 원격 패드는 PC 화면에서만 추가하고 변경할 수 있습니다.

## 보안

- 엔진은 `127.0.0.1`에서만 열립니다. 외부 접속은 Tailscale을 거치므로 내 tailnet 기기만 닿을 수 있고, 모든 요청에 허용된 Google 계정 로그인이 필요해요.
- 명령은 현재 Windows 사용자 권한으로 실행됩니다. 그 권한을 맡겨도 되는 계정만 추가하세요.
- OAuth 클라이언트 보안 비밀번호는 로컬 설정 파일에 저장됩니다.
- 명령줄은 Google 로그인 없이 동작합니다. 현재 Windows 사용자만 읽을 수 있는 엔진 토큰을 쓰고, 엔진은 이 PC에서 온 요청만 받습니다.

## 개발

```powershell
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
npm install
npm run dev                         # 화면 개발 서버, /api는 엔진으로 전달
.venv\Scripts\python backend\main.py --data-dir .test-data --port 48731
.venv\Scripts\python -m unittest discover tests
node scripts/i18n-check.mjs         # 모든 화면 문구의 영어 번역 확인
python scripts/build.py             # release/StackPad에 포터블 빌드
python scripts/build-android.py     # Android APK, ANDROID_HOME과 JAVA_HOME 필요
```

문구는 소스에 한국어로 쓰고 `src/locales/en.js`(화면)와 `backend/i18n.py`(엔진)에서 영어로 번역합니다.

`v1.2.0` 같은 태그를 올리면 GitHub Actions가 설치 파일, 포터블 zip, 업데이트 파일과 서명된 APK를 빌드해 Releases에 게시합니다. `package.json`, `src-tauri/Cargo.toml`, `backend/main.py`의 버전을 함께 올려 주세요. `tests/test_version.py`가 확인합니다.

## 라이선스

[MIT](LICENSE)
