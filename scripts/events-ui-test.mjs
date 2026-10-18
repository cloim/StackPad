import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ locale: 'ko-KR', viewport: { width: 1280, height: 930 } });
const page = await context.newPage();

const errors = [];
page.on('pageerror', error => errors.push(error.message));

let eventConnections = 0;
let eventAborts = 0;
let logRequests = 0;
let activeEventRoute = null;

let services = [{
  id: 'srv-1',
  name: 'SSE 테스트 서비스',
  kind: 'local',
  padset_id: 'default',
  command: 'node server.js',
  cwd: 'C:/test',
  port: 3000,
  slot: 0,
  color: '#22c55e',
  active: false,
  status: 'stopped',
  uptime: 0,
}];

await page.route('http://stackpad.test/**', async route => {
  const url = new URL(route.request().url());

  if (url.pathname.startsWith('/api/')) {
    if (url.pathname === '/api/auth') {
      await route.fulfill({ json: { configured: true, authenticated: true, local: true } });
    } else if (url.pathname === '/api/services') {
      await route.fulfill({
        json: {
          services,
          groups: [],
          padsets: [{ id: 'default', name: '기본' }],
          links: {},
        },
      });
    } else if (url.pathname === '/api/settings') {
      await route.fulfill({
        json: {
          onboarding_done: true,
          recommend_roots: ['C:/test'],
          autostart: false,
          data_dir: 'C:/test',
        },
      });
    } else if (url.pathname.endsWith('/logs')) {
      logRequests++;
      await route.fulfill({
        json: {
          file: '2026-10-19.log',
          offset: logRequests * 10,
          text: `Log entry ${logRequests}\n`,
          reset: logRequests === 1,
        },
      });
    } else if (url.pathname === '/api/events') {
      eventConnections++;
      activeEventRoute = route;

      route.request().response()?.then(() => {}).catch(() => {});

      // Send initial connection and services payload
      const initialPayload = JSON.stringify({
        services,
        groups: [],
        padsets: [{ id: 'default', name: '기본' }],
        links: {},
      });

      await route.fulfill({
        status: 200,
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
        },
        body: `: connected\n\nid: 1\nevent: services\ndata: ${initialPayload}\n\n`,
      });
    } else {
      await route.fulfill({ json: { ok: true } });
    }
  } else {
    const file = path.resolve('dist', url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
    const contentType = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html';
    await route.fulfill({ body: await fs.readFile(file), contentType });
  }
});

try {
  // 1. 초기 로드 및 SSE 연결 확인
  await page.goto('http://stackpad.test/');
  await expect(page.getByRole('button', { name: 'SSE 테스트 서비스 실행', exact: true })).toBeVisible();
  expect(eventConnections).toBeGreaterThanOrEqual(1);

  // 2. 패드 상세 열어서 로그 요청 시작 확인
  await page.getByRole('button', { name: 'SSE 테스트 서비스 메뉴', exact: true }).click();
  await page.getByRole('menuitem', { name: '상세' }).click();
  await expect(page.locator('.log-panel pre')).toContainText('Log entry 1');
  const initialLogCount = logRequests;
  expect(initialLogCount).toBeGreaterThanOrEqual(1);

  // 3. 숨김 상태(visibility: hidden) 전환 시 SSE 재연결/로그 요청 중단 검증
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });

  // 1.5초 대기 후 로그 요청이 추가로 발생하지 않았는지 확인
  await page.waitForTimeout(1500);
  const hiddenLogCount = logRequests;
  expect(hiddenLogCount).toBe(initialLogCount);

  // 4. 다시 표시(visibility: visible)로 전환 시 즉시 갱신 재개 검증
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });

  // 재개 후 로그 요청 증가 확인
  await expect.poll(() => logRequests, { timeout: 3000 }).toBeGreaterThan(hiddenLogCount);

  console.log('EVENTS & VISIBILITY UI PASS: SSE push, log increment, hidden state suppression & visible resume');
} finally {
  await browser.close();
}
