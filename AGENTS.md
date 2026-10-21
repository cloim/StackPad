# StackPad 작업 지침

- 화면과 엔진 문구는 한국어로 쓰고 영어 번역을 함께 추가한다. 화면은 `src/locales/en.js`, 엔진은 `backend/i18n.py`이며 `node scripts/i18n-check.mjs`와 `tests/test_i18n.py`로 누락을 확인한다.
- 버전은 `package.json`, `src-tauri/Cargo.toml`, `backend/main.py`의 `VERSION`을 함께 올린다. `android/app/build.gradle`은 `scripts/build-android.py`가 맞춘다.
- `docs/`의 조사, 계획, 회고 문서는 로컬에만 보관하며 저장소에 올리지 않는다.

## PC 배포

- 개발 PC는 설치판(`%LOCALAPPDATA%\StackPad`)을 쓰며 태그 릴리스를 트레이의 업데이트 설치로 받는다. 로컬 빌드로 설치 폴더를 직접 덮어쓰지 않는다.
- 소스 수정과 웹 빌드 작업의 기본 완료 범위에 `scripts/build.py --release-dir <임시 경로>`(WMI 작업자) 패키징과 `scripts/package-smoke.py <임시 경로>\StackPadEngine.exe` 검증을 포함한다.
- 사용자에게 반영할 변경은 버전을 올려 태그 릴리스를 게시하고, 트레이 업데이트 후 엔진 버전, 등록된 패드, 인증 설정과 실행 중인 서비스 보존을 확인한 다음 완료를 보고한다.

## Android 앱 및 릴리스 배포

- Android 앱 배포는 GitHub Actions CI나 `.github` 폴더 없이 개발 PC 로컬 환경에서 일원화된 파이프라인으로 수행합니다.
- `android/`, `src/`, `capacitor.config.json` 관련 검증과 릴리스는 `scripts/build-android.py`를 WMI 작업자로 실행합니다.
  - 디버그 빌드: `python scripts/build-android.py --test`
  - 서명 빌드 및 보관: `python scripts/build-android.py` (로컬 백업 키스토어 자동 적용 및 `release/StackPad-Android/StackPad.apk` 보관)
  - 서명 빌드 및 GitHub Release 업로드: `python scripts/build-android.py --release`
- 서명 키스토어는 로컬 안전 저장소(`%USERPROFILE%\.config\backups\stackpad-keys\`)를 자동으로 참조하며, GitHub CLI(`gh`)를 통해 태그 생성 및 릴리스 자산 업로드를 로컬에서 직접 완결합니다.
- 게시 후 Releases 자산과 버전, 서명을 확인한 다음 완료를 보고합니다.
