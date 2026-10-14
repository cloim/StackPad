// Account settings against a mocked engine: allowed accounts, Tailscale address, phone QR and connected devices.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const shots = process.argv[2] || '.jobs';
await fs.mkdir(shots, { recursive: true });
const browser = await chromium.launch({ headless: true });
const errors = [];
let accounts = ['owner@example.com'];
let usageProviders = [];
let devices = [{ id: 'abcd1234abcd1234', name: 'Pixel 9', email: 'owner@example.com', created_at: 1760400000 }];
const requests = [];
const page = await browser.newPage({ locale: 'ko-KR', viewport: { width: 1280, height: 1100 } });
page.on('pageerror', error => errors.push(error.message));
await page.route('http://stackpad.test/**', async route => {
  const url = new URL(route.request().url());
  const method = route.request().method();
  if (url.pathname.startsWith('/api/')) {
    requests.push(`${method} ${url.pathname}`);
    let body = { ok: true };
    if (url.pathname === '/api/auth') body = { configured: true, owner: true, authenticated: true, email: 'owner@example.com', local: true };
    else if (url.pathname === '/api/services') body = { services: [], groups: [], links: {}, padsets: [{ id: 'default', name: '기본' }] };
    else if (url.pathname === '/api/settings') body = { autostart: false, data_dir: 'C:/Users/me/.config/stackpad', can_select_data_dir: true, log_retention_days: 14, recommend_roots: [], recommend_hidden: [], onboarding_done: true, usage_providers: usageProviders };
    else if (url.pathname === '/api/usage') body = { providers: [], enabled: usageProviders };
    else if (url.pathname === '/api/settings/usage') { usageProviders = route.request().postDataJSON().providers; body = { providers: usageProviders }; }
    else if (url.pathname === '/api/auth/settings') body = { configured: true, client_id: '123-abc.apps.googleusercontent.com', owner: 'owner@example.com', accounts, external_url: 'https://pc.tail1234.ts.net', redirect_uris: ['http://127.0.0.1:48731/api/auth/google/callback', 'https://pc.tail1234.ts.net/api/auth/google/callback'] };
    else if (url.pathname === '/api/tailscale') body = { installed: true, running: true, host: 'pc.tail1234.ts.net', url: 'https://pc.tail1234.ts.net' };
    else if (url.pathname === '/api/devices' && method === 'GET') body = { devices, current: null };
    else if (url.pathname.startsWith('/api/devices/')) devices = [];
    else if (url.pathname === '/api/auth/accounts') accounts = [...accounts, route.request().postDataJSON().email];
    else if (url.pathname === '/api/pairing') body = { url: 'https://pc.tail1234.ts.net', code: 'fixture-code', expires_in: 300, link: 'stackpad://pair?server=https%3A%2F%2Fpc.tail1234.ts.net&code=fixture-code' };
    else throw new Error(`Unexpected API: ${method} ${url.pathname}`);
    await route.fulfill({ json: body });
  } else {
    const file = path.resolve('dist', url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
    if (!file.startsWith(path.resolve('dist') + path.sep)) throw new Error('Invalid asset path');
    const contentType = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.svg') ? 'image/svg+xml' : 'text/html';
    await route.fulfill({ body: await fs.readFile(file), contentType });
  }
});
try {
  await page.goto('http://stackpad.test/');
  await page.getByRole('button', { name: '환경 설정', exact: true }).click();
  await expect(page.locator('.usage-bar')).toHaveCount(0);
  await page.getByRole('switch', { name: 'Codex 사용량 표시' }).click();
  await expect(page.getByRole('switch', { name: 'Codex 사용량 표시' })).toHaveAttribute('aria-checked', 'true');
  expect(usageProviders).toEqual(['codex']);
  await page.screenshot({ path: path.join(shots, 'general-settings-desktop.png'), fullPage: true });
  await page.getByRole('tab', { name: '계정', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'owner@example.com' })).toBeVisible();
  await expect(page.getByText('소유자', { exact: true })).toBeVisible();
  await page.getByLabel('추가할 Google 계정').fill('friend@example.com');
  await page.getByRole('button', { name: '추가', exact: true }).click();
  await expect(page.getByText('friend@example.com', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'QR 코드 표시' }).click();
  await expect(page.getByRole('img', { name: '휴대폰 연결 QR 코드' })).toBeVisible();
  await expect(page.getByText(/4분 5\d초 동안 한 번 사용할 수 있어요\.|5분 0초 동안/)).toBeVisible();
  await page.screenshot({ path: path.join(shots, 'account-settings-desktop.png'), fullPage: true });
  await page.getByRole('button', { name: 'Pixel 9 연결 해제' }).click();
  await expect(page.getByText('연결된 기기가 없습니다.')).toBeVisible();
  expect(requests).toContain('DELETE /api/devices/abcd1234abcd1234');
  expect(errors).toEqual([]);
  console.log('ACCOUNT UI PASS: usage switches hidden bar, accounts, Tailscale address, pairing QR, device revoke');
} finally {
  await browser.close();
}
