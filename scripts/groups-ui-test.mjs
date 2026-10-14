import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ locale: 'ko-KR', viewport: { width: 1280, height: 930 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const services = ['Shop 백엔드', 'Shop 프론트엔드', 'Wiki'].map((name, index) => ({ id: String(index), name, slot: index < 2 ? 0 : 2, command: 'npm run dev', cwd: 'C:/Users/me/projects', port: 8000 + index, health_url: '', color: '#75d9a5', pid: index === 0 ? 10 : null, active: index === 0, status: index === 0 ? 'running' : 'stopped', autostart: false, uptime: 60, memory: 30 }));
let groups = [{ id: 'app', name: 'Shop', member_ids: ['0', '1'], slot: 0, color: '#7db5eb', wait_ready: true, autostart: false }];
const actions = [];
await page.route('http://stackpad.test/**', async route => {
  const url = new URL(route.request().url());
  const method = route.request().method();
  let body;
  if (url.pathname.startsWith('/api/')) {
    if (url.pathname === '/api/auth') body = { configured: true, authenticated: true };
    else if (url.pathname === '/api/usage') body = { providers: [] };
    else if (url.pathname === '/api/services') body = { services, groups };
    else if (url.pathname === '/api/settings') body = { onboarding_done: true, hostname: 'TEST', cpu: 12, memory: 34, autostart: false };
    else if (/\/services\/\d\/logs$/.test(url.pathname)) body = { text: `${services[Number(url.pathname.split('/')[3])].name} LOG\n\u001b[32mREADY\u001b[0m` };
    else if (/\/groups\/app\/(start|stop)$/.test(url.pathname)) {
      const start = url.pathname.endsWith('start');
      actions.push(start ? 'start' : 'stop');
      services.slice(0, 2).forEach((s, i) => Object.assign(s, { pid: start ? 10 + i : null, active: start, status: start ? 'running' : 'stopped' }));
      body = { ok: true };
    } else if (url.pathname.endsWith('/restart')) { actions.push('restart'); body = { ok: true }; }
    else if (method === 'POST' && url.pathname === '/api/pads/app/code') { actions.push('code'); body = { folder: 'C:/Users/me/projects' }; }
    else if (method === 'POST' && url.pathname === '/api/groups') { groups.push({ ...route.request().postDataJSON(), id: 'new' }); body = { id: 'new' }; }
    else if (method === 'PUT' && url.pathname === '/api/groups/app') { groups[0] = { ...route.request().postDataJSON(), id: 'app' }; body = { id: 'app' }; }
    else if (method === 'DELETE' && url.pathname === '/api/groups/app') { groups = []; services[1].slot = 1; body = { ok: true }; }
    else throw new Error(`Unexpected API: ${method} ${url.pathname}`);
    if (url.pathname === '/api/services') {
      body.padsets = [{ id: 'default', name: '기본' }];
      [...body.services, ...(body.groups || [])].forEach(pad => { pad.padset_id = 'default'; });
    }
    await route.fulfill({ json: body });
  } else {
    const file = path.resolve('dist', url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
    if (!file.startsWith(path.resolve('dist') + path.sep)) throw new Error('Invalid asset path');
    await route.fulfill({ body: await fs.readFile(file), contentType: file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html' });
  }
});
try {
  await page.goto('http://stackpad.test/');
  await expect(page.locator('.pads>.pad-wrap,.pads>.pad.empty')).toHaveCount(16);
  await expect(page.locator('.pad.assigned')).toHaveCount(2);
  await expect(page.getByRole('button', { name: 'Shop 종료', exact: true })).toContainText('일부 실행');
  await expect(page.getByRole('button', { name: 'Shop 종료', exact: true }).locator('.pad-port span')).toHaveText(['Shop 백엔드 :8000', 'Shop 프론트엔드 :8001']);
  await expect(page.getByRole('button', { name: '패드 2 서비스 등록', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Shop 메뉴', exact: true }).click();
  await expect(page.getByRole('menuitem')).toHaveText(['상세', '설정', '삭제', 'VSCode로 열기']);
  await page.screenshot({ path: '.jobs/pad-menu-desktop.png' });
  await page.keyboard.press('Escape');
  // The left-edge pad's menu must stay inside a window as narrow as the desktop app.
  await page.setViewportSize({ width: 460, height: 560 });
  await page.getByRole('button', { name: 'Shop 메뉴', exact: true }).click();
  const menuBox = await page.getByRole('menu').boundingBox();
  expect(menuBox.x >= 0 && menuBox.y >= 0 && menuBox.x + menuBox.width <= 460 && menuBox.y + menuBox.height <= 560).toBe(true);
  await page.screenshot({ path: '.jobs/pad-menu-edge.png' });
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 1280, height: 930 });
  await expect(page.getByRole('menu')).toHaveCount(0);
  await page.getByRole('button', { name: 'Shop 메뉴', exact: true }).click(); await page.getByRole('menuitem', { name: 'VSCode로 열기' }).click();
  await expect.poll(() => actions.includes('code')).toBe(true);
  await expect(page.getByRole('menu')).toHaveCount(0);
  await page.getByRole('button', { name: 'Shop 메뉴', exact: true }).click(); await page.getByRole('menuitem', { name: '설정' }).click();
  await expect(page.getByRole('dialog', { name: '패드 설정', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Shop 메뉴', exact: true }).click(); await page.getByRole('menuitem', { name: '상세' }).click();
  const detail = page.getByRole('dialog', { name: 'Shop', exact: true });
  await expect(detail.getByRole('tab')).toHaveText(['Shop 백엔드', 'Shop 프론트엔드']);
  await expect(detail.locator('.log-panel pre')).toContainText('Shop 백엔드 LOG');
  await detail.getByRole('tab', { name: 'Shop 프론트엔드', exact: true }).click();
  await expect(detail.locator('.log-panel pre')).toContainText('Shop 프론트엔드 LOG');
  await detail.getByRole('tab', { name: 'Shop 백엔드', exact: true }).click();
  await detail.getByRole('button', { name: 'Shop 백엔드 재시작', exact: true }).click();
  await expect.poll(() => actions.includes('restart')).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '.jobs/groups-detail-mobile.png' });
  await page.keyboard.press('Escape');
  // A running group shows its settings read-only.
  await page.getByRole('button', { name: 'Shop 메뉴', exact: true }).click(); await page.getByRole('menuitem', { name: '설정' }).click();
  await expect(page.getByRole('dialog', { name: '패드 설정', exact: true }).getByLabel('패드 이름', { exact: true })).not.toBeEditable();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Shop 종료', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Shop 실행', exact: true })).toContainText('중지됨');
  await page.getByRole('button', { name: 'Shop 실행', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Shop 종료', exact: true })).toContainText('실행 중');
  await page.screenshot({ path: '.jobs/groups-mobile.png' });
  services[1].status = 'unhealthy';
  await expect(page.getByRole('button', { name: 'Shop 종료', exact: true })).toContainText('응답 이상');
  await page.getByRole('button', { name: 'Shop 종료', exact: true }).click();
  await page.setViewportSize({ width: 1280, height: 930 });
  await page.screenshot({ path: '.jobs/groups-desktop.png' });
  expect(errors).toEqual([]);
  console.log('GROUP UI PASS: partial and unhealthy states, grouped pads, pad menu detail/settings/VSCode, service tabs with logs and restart, read-only running settings, desktop/mobile');
} catch (error) {
  await page.screenshot({ path: '.jobs/groups-ui-test-fail.png', fullPage: true }).catch(() => {});
  throw error;
} finally { await browser.close(); }
