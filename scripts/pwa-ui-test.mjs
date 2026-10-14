import { chromium, expect } from '@playwright/test';

// Start the engine on a data folder seeded with scripts/ui_session.py.
const base = 'http://127.0.0.1:48739';
const sessionToken = process.env.STACKPAD_TEST_SESSION || 'stackpad-ui-test-session';
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ locale: 'ko-KR', viewport: { width: 390, height: 844 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(base);
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('crossorigin', 'use-credentials');
  await expect(page.getByRole('heading', { name: '컨트롤 룸에 입장하기' })).toBeVisible();
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  const manifest = await (await context.request.get(`${base}/manifest.webmanifest`)).json();
  expect(manifest).toMatchObject({ id: '/', start_url: '/', scope: '/', display: 'standalone', lang: 'en' });
  for (const icon of manifest.icons) {
    const response = await context.request.get(`${base}${icon.src}`);
    expect(response.ok()).toBe(true);
    expect(response.headers()['content-type']).toContain('image/png');
  }
  const session = await page.context().newCDPSession(page);
  const { installabilityErrors: installErrors } = await session.send('Page.getInstallabilityErrors');
  expect(installErrors).toEqual([]);
  await context.addCookies([{ name: 'stackpad_session', value: sessionToken, url: base }]);
  await page.reload();
  await expect(page.getByRole('main', { name: '서비스 패드' })).toBeVisible();
  const cachedUrls = await page.evaluate(async () => {
    const urls = [];
    for (const name of await caches.keys()) {
      for (const request of await (await caches.open(name)).keys()) urls.push(request.url);
    }
    return urls;
  });
  expect(cachedUrls.some(url => new URL(url).pathname.startsWith('/api'))).toBe(false);
  expect(cachedUrls.some(url => new URL(url).pathname === '/index.html')).toBe(true);
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText(/네트워크 연결 후 다시 시도해 주세요\.|관리 엔진과 연결을 확인해 주세요\./)).toBeVisible();
  await expect(page.getByRole('button', { name: '다시 연결' })).toBeVisible();
  const apiResult = await page.evaluate(async () => {
    try { await fetch('/api/services'); return 'cached'; } catch { return 'network-only'; }
  });
  expect(apiResult).toBe('network-only');
  await page.goto(`${base}/settings`);
  await expect(page.getByRole('button', { name: '다시 연결' })).toBeVisible();
  await context.setOffline(false);
  await expect(page.getByRole('main', { name: '서비스 패드' })).toBeVisible({ timeout: 15000 });
  expect(errors).toEqual([]);
  console.log('PWA PASS: installability, icons, API/cache isolation, offline route reload, automatic reconnect');
} finally {
  await browser.close();
}
