# 위젯

이 폴더의 `<id>.jsx` 파일 하나가 위젯 하나입니다. 파일을 넣고 다시 빌드하면 위젯 영역 설정의 드롭다운에 나타납니다.

- 파일 이름이 위젯 ID입니다. 영문 소문자, 숫자, `-`만 쓰며 40자 이하입니다. `_`로 시작하는 파일은 위젯으로 읽지 않으므로 공용 코드에 씁니다.
- 기본 내보내기로 `{ name, View, order }`를 내보냅니다.
  - `name`: 드롭다운에 보일 이름입니다. 번역되도록 `() => t('이름')` 형태로 쓰고 `src/locales/en.js`에 영어를 추가합니다.
  - `View`: 위젯 영역에 그릴 React 컴포넌트입니다. `api`(엔진 API 호출 함수)와 `settings`(엔진 설정)를 받습니다.
  - `order`: 드롭다운 순서입니다. 작을수록 위에 보이며 생략하면 맨 뒤입니다.

```jsx
import React from 'react';
import { t } from '../i18n.js';

function Clock() {
  return <section>{new Date().toLocaleTimeString()}</section>;
}

export default { name: () => t('시계'), order: 30, View: Clock };
```
