# StackPad 작업 지침

- 화면과 엔진 문구는 한국어로 쓰고 영어 번역을 함께 추가한다. 화면은 `src/locales/en.js`, 엔진은 `backend/i18n.py`이며 `node scripts/i18n-check.mjs`와 `tests/test_i18n.py`로 누락을 확인한다.
- 버전은 `package.json`, `src-tauri/Cargo.toml`, `backend/main.py`의 `VERSION`을 함께 올린다. `android/app/build.gradle`은 `scripts/build-android.py`가 맞춘다.
- `docs/`의 조사, 계획, 회고 문서는 로컬에만 보관하며 저장소에 올리지 않는다.

## PC 배포

- 소스 수정과 웹 빌드 작업의 기본 완료 범위에 데스크톱 실행 파일 빌드, 로컬 배포와 적용 검증을 포함한다.
- `scripts/build.py --release-dir <임시 경로>`를 WMI 작업자로 실행해 별도 경로에 패키징하고 검증한 뒤 `scripts/deploy-local-update.py <임시 경로>`로 `release/StackPad`에 배포한다.
- 배포 전에 기존 실행 파일과 사용자 설정을 백업한다. 등록된 패드, 인증 설정, 로그와 실행 중인 서비스는 보존한다. 데이터 구조 변경 시 의도한 이전만 발생했는지 확인한다.
- 배포 후 패키지 파일, 관리 엔진 상태와 변경 기능을 확인한 다음 완료를 보고한다.

## Android 앱

- `android/`, `src/`, `capacitor.config.json` 변경은 `scripts/build-android.py`를 WMI 작업자로 실행해 디버그 APK를 빌드하고 에뮬레이터나 기기에서 확인한다. `ANDROID_HOME`과 `JAVA_HOME`이 필요하다.
- 서명된 APK는 GitHub Actions 릴리스에서만 만든다. 서명 키는 GitHub Secrets와 로컬 백업에만 둔다.

## 릴리스

- `v1.2.3` 형식의 태그를 올리면 `.github/workflows/release.yml`이 설치 파일, 포터블 zip, 업데이트 파일(`latest.json`), 서명 APK를 빌드해 GitHub Releases에 게시한다.
- 게시 후 Releases 자산과 `latest.json`의 버전, 서명을 확인한 다음 완료를 보고한다.
