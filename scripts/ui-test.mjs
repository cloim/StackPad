import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

// Start the engine on a data folder seeded with scripts/ui_session.py.
const base = 'http://127.0.0.1:48732';
const session = process.env.STACKPAD_TEST_SESSION || 'stackpad-ui-test-session';
const screenshots = path.resolve('.jobs/ui');
const root = path.resolve('.');
const python = path.join(root, '.venv', 'Scripts', 'python.exe');
await fs.mkdir(screenshots, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ locale: 'ko-KR', viewport: { width: 1440, height: 1120 }, locale: 'ko-KR' });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const ids = [];
async function request(endpoint, body, method = 'POST') {
  const result = await context.request.fetch(`${base}/api${endpoint}`, { method, headers: { Origin: base }, data: body });
  if (!result.ok()) throw new Error(`${endpoint}: ${await result.text()}`);
  return result.json();
}
try {
  await page.goto(base);
  await expect(page.getByRole('button', { name: 'Google로 로그인' })).toBeVisible();
  await page.screenshot({ path: path.join(screenshots, 'login-desktop.png') });
  await context.addCookies([{ name: 'stackpad_session', value: session, url: base }]);
  await page.reload();
  await expect(page.getByRole('main', { name: '서비스 패드' })).toBeVisible();
  await expect(page.getByRole('button', { name: '패드 1 서비스 등록', exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(screenshots, 'empty-desktop.png') });
  // Register the first fixture using the real editor UI.
  await page.getByRole('button', { name: '패드 1 서비스 등록', exact: true }).click();
  await page.getByLabel('패드 이름').fill('테스트 API');
  await page.getByRole('tab', { name: '서비스', exact: true }).click();
  await page.getByLabel('실행 명령').fill(`"${python}" -u -m http.server 48821 --bind 127.0.0.1`);
  await page.getByLabel('작업 폴더').fill(root);
  await page.getByLabel('포트', { exact: false }).fill('48821');
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  let services = await request('/services', undefined, 'GET');
  ids.push(services.services[0].id);
  const fixtures = [
    ['웹 프런트엔드', '#3b82f6', 48822], ['작업 큐', '#f97316', null], ['검색 서버', '#a855f7', null],
    ['문서 API', '#ef3994', null], ['파일 서버', '#facc15', null], ['알림 워커', '#22c55e', null], ['개발 프록시', '#3b82f6', null],
  ];
  for (let index = 0; index < fixtures.length; index++) {
    const [name, color, port] = fixtures[index];
    const result = await request('/services', { name, color, port, command: `"${python}" -u -m http.server ${port || 48830 + index} --bind 127.0.0.1`, cwd: root, health_url: '', slot: index + 1, autostart: index === 0 });
    ids.push(result.id);
  }
  await expect(page.getByRole('button', { name: '테스트 API 실행', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '테스트 API 실행', exact: true }).click();
  await expect(page.getByRole('button', { name: '테스트 API 종료', exact: true })).toBeEnabled({ timeout: 15000 });
  await request(`/services/${ids[1]}/start`);
  await expect(page.locator('.pad.running')).toHaveCount(2, { timeout: 15000 });
  await page.getByRole('button', { name: '테스트 API 메뉴', exact: true }).click(); await page.getByRole('menuitem', { name: '상세' }).click();
  await expect(page.locator('.log-panel pre')).toContainText('Serving HTTP', { timeout: 10000 });
  await page.keyboard.press('Escape');
  await page.screenshot({ path: path.join(screenshots, 'deck-desktop.png'), fullPage: true });
  await page.getByRole('button', { name: '환경 설정', exact: true }).click();
  await expect(page.getByRole('heading', { name: '환경 설정', exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(screenshots, 'settings-desktop.png') });
  await page.goto(`${base}/settings`);
  await expect(page.getByRole('heading', { name: '환경 설정', exact: true })).toBeVisible();
  await page.goto(base);
  await page.getByRole('button', { name: '작업 큐 메뉴', exact: true }).click(); await page.getByRole('menuitem', { name: '설정' }).click();
  const dialog = page.getByRole('dialog', { name: '패드 설정', exact: true });
  await expect(dialog).toBeVisible();
  // Verify the shared desktop modal can be moved and keeps focus inside.
  const header = dialog.locator('.modal-header');
  const before = await dialog.boundingBox();
  const headerBox = await header.boundingBox();
  await page.mouse.move(headerBox.x + 150, headerBox.y + 20);
  await page.mouse.down(); await page.mouse.move(headerBox.x + 200, headerBox.y + 45, { steps: 10 }); await page.mouse.up();
  const after = await dialog.boundingBox();
  if (after.x <= before.x + 20) throw new Error('Desktop dialog drag did not move');
  await page.screenshot({ path: path.join(screenshots, 'editor-desktop.png') });
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '테스트 API 메뉴', exact: true }).click(); await page.getByRole('menuitem', { name: '상세' }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.keyboard.press('Escape');
  await expect(page.locator('.pad.running')).toHaveCount(2);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  if (overflow) throw new Error('Mobile page has horizontal overflow');
  await page.screenshot({ path: path.join(screenshots, 'deck-mobile.png'), fullPage: true });
  await page.getByRole('button', { name: '패드 9 서비스 등록', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.screenshot({ path: path.join(screenshots, 'editor-mobile.png') });
  await page.getByRole('button', { name: '취소', exact: true }).click();
  await page.getByRole('button', { name: '테스트 API 종료', exact: true }).click();
  await expect(page.getByRole('button', { name: '테스트 API 실행', exact: true })).toBeEnabled({ timeout: 15000 });
  await page.getByRole('button', { name: '환경 설정', exact: true }).click();
  await page.getByRole('tab', { name: '계정', exact: true }).click();
  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(page.getByRole('heading', { name: '컨트롤 룸에 입장하기' })).toBeVisible();
  await page.screenshot({ path: path.join(screenshots, 'login-mobile.png') });
  if (errors.length) throw new Error(`Browser errors: ${errors.join('; ')}`);
  console.log('UI PASS: sign-in screen, editor, pad start/stop, logs, routing, drag, 390px mobile, logout; browser errors=0');
} finally {
  for (const id of ids) { try { await request(`/services/${id}/stop`); await request(`/services/${id}`, undefined, 'DELETE'); } catch (error) { console.error('Cleanup:', error.message); } }
  await browser.close();
}
