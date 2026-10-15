import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const browser = await chromium.launch({ headless: true });
const errors = [];
const snapshot = { providers: ['Claude', 'Codex', 'AG Gemini', 'AG Claude/GPT'].map((name, index) => ({
  id: name, name, status: 'ok', stale_minutes: index === 2 ? 64 : undefined,
  windows: [{ key: 'five_hour', label: '5h', used_percent: 12.5 + index * 26, resets_at: new Date(Date.now() + 91 * 60000).toISOString() },
    { key: 'weekly', label: 'w', used_percent: 94, resets_at: new Date(Date.now() + 3 * 86400000).toISOString() }],
})) };
await fs.mkdir('.jobs/tray-popup/screenshots', { recursive: true });
try {
  for (const locale of ['ko-KR', 'en-US']) {
    const context = await browser.newContext({ viewport: { width: 360, height: 456 }, locale, deviceScaleFactor: locale === 'ko-KR' ? 1 : 2 });
    await context.route('http://stackpad.test/**', async route => {
      const name = new URL(route.request().url()).pathname.slice(1);
      const type = name.endsWith('.html') ? 'text/html' : name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'image/png';
      await route.fulfill({ contentType: type, body: await fs.readFile(path.join('dist', name)) });
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://stackpad.test/tray-usage.html');
    await expect(page.locator('.tray-loading')).toBeVisible();
    async function update(data) {
      await page.evaluate(data => { window.__STACKPAD_USAGE__ = data; window.dispatchEvent(new Event('stackpad-usage')); }, data);
    }
    await update(snapshot);
    await expect(page.getByRole('progressbar')).toHaveCount(8);
    await expect(page.getByRole('progressbar').first()).toHaveAttribute('aria-valuenow', '12.5');
    await expect(page.locator('.usage-percent').first()).toHaveText('13%');
    await expect(page.locator('.usage-reset').first()).toContainText('1h 31m');
    await expect(page.locator('.usage-window.warning')).toHaveCount(5);
    await expect(page.locator('.usage-provider').nth(2).locator('strong')).toContainText(locale === 'ko-KR' ? '1시간 전' : '1h ago');
    expect(await page.evaluate(() => document.querySelector('main').scrollHeight <= document.querySelector('main').clientHeight)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
    await page.screenshot({ path: `.jobs/tray-popup/screenshots/${locale}.png` });
    await update({ providers: [{ name: 'Claude', id: 'claude', status: 'login_required', message: 'CLI 사용 시 갱신' },
      { name: 'AG Gemini', id: 'ag', status: 'unavailable' }] });
    await expect(page.locator('.usage-message').first()).toHaveText(locale === 'ko-KR' ? 'CLI 사용 시 갱신' : 'Updated when the CLI is used');
    await update({ error: true, providers: [] });
    await expect(page.locator('.tray-message')).toHaveText(locale === 'ko-KR' ? '사용량 조회 실패' : 'Usage unavailable');
    await update({ providers: [], update_available: true });
    await expect(page.getByRole('progressbar')).toHaveCount(0);
    await expect(page.locator('.tray-message')).toHaveText(locale === 'ko-KR' ? '사용량 표시가 꺼져 있어요.' : 'Usage display is turned off.');
    await expect(page.locator('.tray-update')).toBeVisible();
    await context.close();
  }
  expect(errors).toEqual([]);
  console.log('TRAY UI PASS: shared usage bars, rounding, reset times, stale snapshots, loading, errors, empty settings, updates, Korean/English and 1x/2x layout');
} finally { await browser.close(); }
