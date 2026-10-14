import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ locale: 'ko-KR', viewport: { width: 1440, height: 1120 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const services = [
  { id: 'running', name: '실행 서비스', command: 'uv run uvicorn app.main:app --port 8101', cwd: 'C:/Users/me/projects/Shop/backend', port: 8101, health_url: 'http://127.0.0.1:8101/health', color: '#7db5eb', autostart: true, slot: 0, pid: 1, status: 'running', uptime: 10 },
  { id: 'stopped', name: '중지 서비스', command: 'npm run dev', cwd: 'C:/Users/me/projects/Shop/frontend', port: 5174, health_url: 'http://127.0.0.1:5174/', color: '#f2ad62', autostart: false, slot: 1, pid: null, status: 'stopped', uptime: 0 },
];
let mutations = 0;
await page.route('http://stackpad.test/**', async route => {
  const url = new URL(route.request().url());
  if (url.pathname.startsWith('/api/')) {
    let body;
    if (route.request().method() !== 'GET') {
      mutations++;
      expect(url.pathname).toBe('/api/pads/stopped');
      const data = route.request().postDataJSON(); Object.assign(services[1], data.components[0], { name: data.name, color: data.color, autostart: data.autostart, slot: data.slot });
      body = { id: 'stopped' };
    } else if (url.pathname === '/api/auth') body = { configured: true, authenticated: true };
    else if (url.pathname === '/api/usage') body = { providers: [] };
    else if (url.pathname === '/api/services') body = { services };
    else if (url.pathname === '/api/settings') body = { hostname: '테스트 PC', data_dir: '테스트', cpu: 0, memory: 0 };
    else if (url.pathname.endsWith('/logs')) body = { text: '서비스 로그' };
    else throw new Error(`Unexpected API: ${url.pathname}`);
    if (url.pathname === '/api/services') {
      body.padsets = [{ id: 'default', name: '기본' }];
      [...body.services, ...(body.groups || [])].forEach(pad => { pad.padset_id = 'default'; });
    }
    await route.fulfill({ json: body });
  } else {
    const file = path.resolve('dist', url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
    if (!file.startsWith(path.resolve('dist') + path.sep)) throw new Error('Invalid asset path');
    const contentType = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.svg') ? 'image/svg+xml' : 'text/html';
    await route.fulfill({ body: await fs.readFile(file), contentType });
  }
});
const dialog = page.getByRole('dialog', { name: '패드 설정', exact: true });
try {
  await page.goto('http://stackpad.test/');
  await page.getByRole('button', { name: '실행 서비스 메뉴', exact: true }).click(); await page.getByRole('menuitem', { name: '상세' }).click();
  await expect(page.getByRole('button', { name: '설정', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '설정', exact: true }).click();
  for (const field of ['패드 이름', '실행 명령', '작업 폴더', '포트', '상태 확인 URL']) {
    await expect(dialog.getByLabel(field, { exact: false })).not.toBeEditable();
  }
  await expect(dialog.getByLabel('실행 명령', { exact: false })).toHaveValue(services[0].command);
  await expect(dialog.getByRole('button', { name: '블루', exact: true })).toBeDisabled();
  await expect(dialog.getByRole('checkbox')).toBeDisabled();
  await expect(dialog.getByRole('checkbox')).toBeChecked();
  await expect(dialog.getByRole('button', { name: '저장', exact: true })).toHaveCount(0);
  const selectedText = await dialog.getByLabel('실행 명령', { exact: false }).evaluate(el => { el.select(); return el.value.slice(el.selectionStart, el.selectionEnd); });
  expect(selectedText).toBe(services[0].command);
  await dialog.locator('form').evaluate(form => form.requestSubmit());
  expect(mutations).toBe(0);
  await fs.mkdir('docs/reviews/screenshots', { recursive: true });
  await page.screenshot({ path: 'docs/reviews/screenshots/running-settings-desktop.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(dialog).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'docs/reviews/screenshots/running-settings-mobile.png' });
  await dialog.locator('.form-actions').getByRole('button', { name: '닫기', exact: true }).click();
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 1440, height: 1120 });
  await page.getByRole('button', { name: '중지 서비스 메뉴', exact: true }).click(); await page.getByRole('menuitem', { name: '상세' }).click();
  await page.getByRole('button', { name: '설정', exact: true }).click();
  await expect(dialog.getByLabel('패드 이름', { exact: true })).toBeEditable();
  await dialog.getByLabel('패드 이름', { exact: true }).fill('저장 전 초안');
  services[1].pid = 2;
  services[1].status = 'starting';
  await expect(dialog.getByLabel('패드 이름', { exact: true })).not.toBeEditable();
  await expect(dialog.getByLabel('패드 이름', { exact: true })).toHaveValue('중지 서비스');
  await dialog.locator('form').evaluate(form => form.requestSubmit());
  expect(mutations).toBe(0);
  await dialog.locator('.form-actions').getByRole('button', { name: '닫기', exact: true }).click();
  services[1].pid = null;
  services[1].status = 'stopped';
  await expect(page.getByRole('button', { name: '중지 서비스 실행', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '설정', exact: true }).click();
  await dialog.getByLabel('패드 이름', { exact: true }).fill('수정된 서비스');
  await dialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(mutations).toBe(1);
  expect(services[1].name).toBe('수정된 서비스');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '패드 3 서비스 등록', exact: true }).click();
  await expect(page.getByRole('dialog').getByLabel('패드 이름', { exact: true })).toBeEditable();
  await expect(page.getByRole('dialog').getByRole('button', { name: '저장', exact: true })).toBeEnabled();
  expect(errors).toEqual([]);
  console.log('RUNNING SETTINGS PASS: read and select text, blocked mutations, live state lock, stopped edit, new registration, desktop and mobile');
} finally {
  await browser.close();
}
