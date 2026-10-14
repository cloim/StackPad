import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ locale: 'ko-KR', viewport: { width: 1280, height: 930 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const services = ['Wiki', 'Shop 백엔드', 'Shop 프론트엔드', 'Blog 백엔드', 'Blog 프론트엔드'].map((name, slot) => ({ id: String(slot), name, slot, command: 'npm run dev', cwd: 'C:/Users/me/projects', port: 8000 + slot, health_url: '', color: ['#75d9a5','#7db5eb','#f2ad62','#c8a0ee','#75d9a5'][slot], pid: slot === 1 ? null : slot + 1, status: slot === 1 ? 'stopped' : 'running', autostart: true, uptime: 300, memory: 80 }));
let actions = 0;
let startup = false;
await page.route('http://stackpad.test/**', async route => {
  const url = new URL(route.request().url());
  let body;
  if (url.pathname.startsWith('/api/')) {
    if (url.pathname === '/api/auth') body = { configured: true, authenticated: true };
    else if (url.pathname === '/api/usage') body = { providers: [] };
    else if (url.pathname === '/api/services') body = { services };
    else if (url.pathname === '/api/settings') body = { hostname: '내 PC', data_dir: 'C:/Users/test/StackPad', autostart: startup, cpu: 12, memory: 38 };
    else if (url.pathname === '/api/settings/autostart') { startup = route.request().postDataJSON().enabled; body = { ok: true }; }
    else if (url.pathname.endsWith('/logs')) body = { text: '서비스 실행 로그\n' + '긴 로그 '.repeat(100) };
    else if (/\/services\/1\/(start|stop)$/.test(url.pathname)) { actions++; Object.assign(services[1], url.pathname.endsWith('/start') ? { pid: 2, status: 'running' } : { pid: null, status: 'stopped' }); body = { ok: true }; }
    else throw new Error(`Unexpected API: ${url.pathname}`);
    if (url.pathname === '/api/services') {
      body.padsets = [{ id: 'default', name: '기본' }];
      body.services.forEach(service => { service.active = !!service.pid; });
      [...body.services, ...(body.groups || [])].forEach(pad => { pad.padset_id = 'default'; });
    }
    await route.fulfill({ json: body });
  } else {
    const file = path.resolve('dist', url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
    if (!file.startsWith(path.resolve('dist') + path.sep)) throw new Error('Invalid asset path');
    await route.fulfill({ body: await fs.readFile(file), contentType: file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.svg') ? 'image/svg+xml' : 'text/html' });
  }
});
try {
  await page.goto('http://stackpad.test/');
  await expect(page.locator('.pads>.pad-wrap,.pads>.pad.empty')).toHaveCount(16);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('.sidebar,.right-stack,.page-heading,.log-panel')).toHaveCount(0);
  for (const [width, height] of [[1920, 1080], [1280, 930], [1000, 700], [390, 844], [360, 640], [844, 390]]) {
    await page.setViewportSize({ width, height });
    const layout = await page.evaluate(() => {
      const main = document.querySelector('main');
      const grid = document.querySelector('.pads');
      const bounds = grid.getBoundingClientRect();
      const style = getComputedStyle(grid);
      return { columns: style.gridTemplateColumns.split(' ').length, rows: style.gridTemplateRows.split(' ').length, fullWidth: Math.abs(bounds.width - main.clientWidth + parseFloat(getComputedStyle(main).paddingLeft) + parseFloat(getComputedStyle(main).paddingRight)) < 1, fullHeight: Math.abs(bounds.bottom - main.getBoundingClientRect().bottom + parseFloat(getComputedStyle(main).paddingBottom)) < 1 && bounds.top >= document.querySelector('[aria-label="패드셋"]').getBoundingClientRect().bottom, overflow: main.scrollHeight > main.clientHeight || document.documentElement.scrollWidth > innerWidth, visible: [...document.querySelectorAll('.pad')].every(pad => { const rect = pad.getBoundingClientRect(); const state = pad.querySelector('.pad-state')?.getBoundingClientRect(); return rect.top >= bounds.top - 1 && rect.bottom <= bounds.bottom + 1 && (!state || state.bottom <= rect.bottom + 1); }) };
    });
    expect(layout, `${width}x${height}`).toEqual({ columns: 4, rows: 4, fullWidth: true, fullHeight: true, overflow: false, visible: true });
  }
  await page.setViewportSize({ width: 1280, height: 930 });
  await fs.mkdir('docs/reviews/screenshots', { recursive: true });
  await page.screenshot({ path: 'docs/reviews/screenshots/compact-desktop.png' });
  await page.getByRole('button', { name: 'Shop 백엔드 실행', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Shop 백엔드 종료', exact: true })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: 'Shop 백엔드 종료', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Shop 백엔드 실행', exact: true })).toBeVisible();
  expect(actions).toBe(2);
  await page.getByRole('button', { name: '환경 설정', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '환경 설정', exact: true })).toBeVisible();
  await page.getByRole('switch').click();
  await expect(page.getByRole('dialog', { name: '설정을 반영했습니다' })).toBeVisible();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await expect(page.getByRole('switch')).toBeChecked();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: '시스템 모니터', exact: true })).toHaveCount(0);
  expect(await page.locator('.toolbar-actions .tool-button').evaluateAll(buttons => buttons.map(b => b.getAttribute('aria-label')))).toEqual(['새로고침', '등록 추천', '서비스 등록', '환경 설정']);
  await expect(page.locator('.toolbar-actions').getByRole('button', { name: '로그아웃', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '환경 설정', exact: true }).click();
  await page.getByRole('tab', { name: '계정', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '환경 설정', exact: true }).getByRole('button', { name: '로그아웃', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'docs/reviews/screenshots/compact-mobile.png' });
  await page.getByRole('button', { name: 'Blog 백엔드 메뉴', exact: true }).click(); await page.getByRole('menuitem', { name: '상세' }).click();
  await expect(page.getByRole('dialog', { name: 'Blog 백엔드', exact: true })).toBeVisible();
  await expect(page.locator('.log-panel pre')).toContainText('서비스 실행 로그');
  await page.screenshot({ path: 'docs/reviews/screenshots/compact-detail-mobile.png' });
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '패드 6 서비스 등록', exact: true }).click();
  await expect(page.getByRole('dialog').getByLabel('패드 이름', { exact: true })).toBeEditable();
  expect(errors).toEqual([]);
  console.log('COMPACT UI PASS: toolbar and 16 pads, start/stop, settings modal without system monitor, nested notice, detail/logs, new registration, desktop and mobile');
} finally { await browser.close(); }
