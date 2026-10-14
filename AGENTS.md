# StackPad 작업 지침

- 화면과 엔진 문구는 한국어로 쓰고 영어 번역을 함께 추가한다. 화면은 `src/locales/en.js`, 엔진은 `backend/i18n.py`이며 `node scripts/i18n-check.mjs`와 `tests/test_i18n.py`로 누락을 확인한다.
- 버전은 `package.json`, `src-tauri/Cargo.toml`, `backend/main.py`의 `VERSION`을 함께 올린다. `android/app/build.gradle`은 `scripts/build-android.py`가 맞춘다.
- `docs/`의 조사, 계획, 회고 문서는 로컬에만 보관하며 저장소에 올리지 않는다.

## PC 배포

- 형님 PC는 설치판(`%LOCALAPPDATA%\StackPad`)을 쓰며 태그 릴리스를 트레이의 업데이트 설치로 받는다. 로컬 빌드로 설치 폴더를 직접 덮어쓰지 않는다.
- 소스 수정과 웹 빌드 작업의 기본 완료 범위에 `scripts/build.py --release-dir <임시 경로>`(WMI 작업자) 패키징과 `scripts/package-smoke.py <임시 경로>\StackPadEngine.exe` 검증을 포함한다.
- 사용자에게 반영할 변경은 버전을 올려 태그 릴리스를 게시하고, 트레이 업데이트 후 엔진 버전, 등록된 패드, 인증 설정과 실행 중인 서비스 보존을 확인한 다음 완료를 보고한다.
- `scripts/deploy-local-update.py`는 포터블 폴더(`release/StackPad`)를 쓰는 환경에서만 사용한다.

## Android 앱

- `android/`, `src/`, `capacitor.config.json` 변경은 `scripts/build-android.py`를 WMI 작업자로 실행해 디버그 APK를 빌드하고 에뮬레이터나 기기에서 확인한다. `ANDROID_HOME`과 `JAVA_HOME`이 필요하다.
- 서명된 APK는 GitHub Actions 릴리스에서만 만든다. 서명 키는 GitHub Secrets와 로컬 백업에만 둔다.

## 릴리스

- `v1.2.3` 형식의 태그를 올리면 `.github/workflows/release.yml`이 설치 파일, 포터블 zip, 업데이트 파일(`latest.json`), 서명 APK를 빌드해 GitHub Releases에 게시한다.
- 게시 후 Releases 자산과 `latest.json`의 버전, 서명을 확인한 다음 완료를 보고한다.
