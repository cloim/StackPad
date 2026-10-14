// Sign-in screens against a mocked engine: first-run setup, Google sign-in start, errors and focus refresh.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const shots = process.argv[2] || '.jobs';
await fs.mkdir(shots, { recursive: true });
const browser = await chromium.launch({ headless: true });
const errors = [];
let auth = { configured: false, owner: false, authenticated: false, email: null, local: true };
let saved = null;
let started = 0;

async function open(viewport, locale = 'ko-KR') {
  const page = await browser.newPage({ locale, viewport });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('http://stackpad.test/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/auth/google/start') { started++; await route.fulfill({ body: 'google', contentType: 'text/plain' }); return; }
    if (url.pathname.startsWith('/api/')) {
      let body;
      if (url.pathname === '/api/auth') body = auth;
      else if (url.pathname === '/api/auth/settings') body = { configured: auth.configured, client_id: saved?.client_id || '', owner: null, accounts: [], external_url: 'https://pc.tail1234.ts.net', redirect_uris: ['http://127.0.0.1:48731/api/auth/google/callback', 'https://pc.tail1234.ts.net/api/auth/google/callback'] };
      else if (url.pathname === '/api/tailscale') body = { installed: true, running: true, host: 'pc.tail1234.ts.net', url: 'https://pc.tail1234.ts.net' };
      else if (url.pathname === '/api/auth/client') { saved = route.request().postDataJSON(); auth = { ...auth, configured: true }; body = { ok: true }; }
      else throw new Error(`Unexpected API: ${url.pathname}`);
      await route.fulfill({ json: body });
    } else {
      const file = path.resolve('dist', url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
      if (!file.startsWith(path.resolve('dist') + path.sep)) throw new Error('Invalid asset path');
      const contentType = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.svg') ? 'image/svg+xml' : 'text/html';
      await route.fulfill({ body: await fs.readFile(file), contentType });
    }
  });
  return page;
}

try {
  const page = await open({ width: 1280, height: 1000 });
  await page.goto('http://stackpad.test/');
  await expect(page.getByRole('heading', { name: 'StackPad 시작하기' })).toBeVisible();
  await expect(page.getByText('https://pc.tail1234.ts.net', { exact: true })).toBeVisible();
  await expect(page.getByText('https://pc.tail1234.ts.net/api/auth/google/callback', { exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(shots, 'signin-setup-desktop.png'), fullPage: true });
  await page.getByLabel('클라이언트 ID').fill('123-abc.apps.googleusercontent.com');
  await page.getByLabel('클라이언트 보안 비밀번호').fill('fixture-secret');
  await page.getByRole('button', { name: '저장', exact: true }).click();
  expect(saved).toEqual({ client_id: '123-abc.apps.googleusercontent.com', client_secret: 'fixture-secret' });
  await expect(page.getByRole('button', { name: 'Google로 로그인' })).toBeVisible();
  await expect(page.getByText('처음 로그인한 Google 계정이 이 StackPad의 소유자로 등록됩니다.')).toBeVisible();
  await page.screenshot({ path: path.join(shots, 'signin-owner-desktop.png') });
  await page.getByRole('button', { name: 'Google로 로그인' }).click();
  await expect.poll(() => started).toBe(1);

  auth = { configured: true, owner: true, authenticated: false, email: null, local: false };
  const phone = await open({ width: 390, height: 844 });
  await phone.goto('http://stackpad.test/?auth_error=' + encodeURIComponent('stranger@example.com 계정은 허용되지 않았습니다.'));
  await expect(phone.getByRole('alert')).toHaveText('stranger@example.com 계정은 허용되지 않았습니다.');
  expect(new URL(phone.url()).search).toBe('');
  await phone.screenshot({ path: path.join(shots, 'signin-error-mobile.png') });

  auth = { configured: true, owner: false, authenticated: false, email: null, local: false };
  await phone.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(phone.getByText('StackPad가 실행 중인 PC에서 먼저 로그인해 주세요.', { exact: false })).toBeVisible();
  await expect(phone.getByRole('button', { name: 'Google로 로그인' })).toHaveCount(0);

  auth = { configured: false, owner: false, authenticated: false, email: null, local: false };
  await phone.reload();
  await expect(phone.getByRole('heading', { name: 'PC에서 설정을 마쳐 주세요' })).toBeVisible();
  const english = await open({ width: 390, height: 844 }, 'en-US');
  auth = { configured: true, owner: true, authenticated: false, email: null, local: false };
  await english.goto('http://stackpad.test/');
  await expect(english.getByRole('button', { name: 'Sign in with Google' })).toBeVisible();
  await expect(english.locator('html')).toHaveAttribute('lang', 'en');
  await english.screenshot({ path: path.join(shots, 'signin-english-mobile.png') });
  expect(errors).toEqual([]);
  console.log('SIGN-IN UI PASS: English locale, first-run setup, OAuth client save, Google start, error display, owner and external states');
} finally {
  await browser.close();
}
