import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ locale: 'ko-KR', viewport: { width: 1440, height: 1120 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const esc = String.fromCharCode(27);
const longLine = '긴 로그 메시지 '.repeat(80).trim();
const text = `${esc}[32mREADY${esc}[0m\n${esc}[1mBOLD${esc}[0m\n${esc}[38;5;196mPALETTE${esc}[0m\n${esc}[38;2;20;180;220mRGB${esc}[0m\n<script>window.logInjected=true</script>\nplain 한국어\n${esc}[2J${esc}[1;1Hscreen clear\n${esc}[32m${longLine}${esc}[0m\n`;
await page.route('http://stackpad.test/**', async route => {
  const url = new URL(route.request().url());
  if (url.pathname.startsWith('/api/')) {
    let body;
    if (url.pathname === '/api/auth') body = { configured: true, authenticated: true };
    else if (url.pathname === '/api/usage') body = { providers: [] };
    else if (url.pathname === '/api/services') body = { services: [{ id: 'ansi-fixture', name: 'ANSI 테스트', command: 'npm run dev', cwd: 'C:/Users/me/projects/Shop/frontend', port: 5174, slot: 0, color: '#7db5eb', autostart: false, status: 'running', pid: 1, uptime: 1 }] };
    else if (url.pathname === '/api/settings') body = { hostname: '테스트 PC', data_dir: '테스트', endpoint: 'http://127.0.0.1:48731' };
    else if (url.pathname === '/api/services/ansi-fixture/logs') body = { text };
    else throw new Error(`Unexpected API: ${url.pathname}`);
    if (url.pathname === '/api/services') {
      body.padsets = [{ id: 'default', name: '기본' }];
      [...body.services, ...(body.groups || [])].forEach(pad => { pad.padset_id = 'default'; });
    }
    await route.fulfill({ json: body });
  } else {
    const file = path.resolve('dist', url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
    if (!file.startsWith(path.resolve('dist') + path.sep)) throw new Error('Invalid asset path');
    const contentType = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html';
    await route.fulfill({ body: await fs.readFile(file), contentType });
  }
});
try {
  await page.goto('http://stackpad.test/');
  await page.getByRole('button', { name: 'ANSI 테스트 메뉴', exact: true }).click(); await page.getByRole('menuitem', { name: '상세' }).click();
  const logs = page.locator('.log-panel pre');
  await expect(logs).toContainText('plain 한국어');
  await expect(logs).toContainText('<script>window.logInjected=true</script>');
  const rendered = await logs.textContent();
  expect(rendered).not.toContain(esc);
  expect(rendered).not.toContain('[32m');
  expect(rendered).toContain('READY\nBOLD\nPALETTE\nRGB');
  expect(await logs.getByText('READY', { exact: true }).evaluate(el => getComputedStyle(el).color)).toBe('rgb(0, 187, 0)');
  expect(await logs.getByText('BOLD', { exact: true }).evaluate(el => getComputedStyle(el).fontWeight)).toBe('700');
  expect(await logs.getByText('PALETTE', { exact: true }).evaluate(el => getComputedStyle(el).color)).toBe('rgb(255, 0, 0)');
  expect(await logs.getByText('RGB', { exact: true }).evaluate(el => getComputedStyle(el).color)).toBe('rgb(20, 180, 220)');
  expect(await page.evaluate(() => window.logInjected)).toBeUndefined();
  expect(await logs.evaluate(el => getComputedStyle(el).whiteSpace)).toBe('pre');
  expect(await logs.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true);
  expect(await logs.getByText(longLine, { exact: true }).evaluate(el => el.getClientRects().length)).toBe(1);
  await logs.evaluate(el => { el.scrollLeft = el.scrollWidth; });
  expect(await logs.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
  await logs.evaluate(el => { el.scrollLeft = 0; });
  await fs.mkdir('docs/reviews/screenshots', { recursive: true });
  await page.screenshot({ path: 'docs/reviews/screenshots/ansi-logs-desktop.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  await logs.scrollIntoViewIfNeeded();
  await expect(logs).toBeVisible();
  expect(await logs.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true);
  expect(await logs.getByText(longLine, { exact: true }).evaluate(el => el.getClientRects().length)).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'docs/reviews/screenshots/ansi-logs-mobile.png' });
  expect(errors).toEqual([]);
  console.log('ANSI UI PASS: colors, bold, plain HTML, line breaks, control codes, horizontal scrolling without wrapping, desktop and mobile');
} finally {
  await browser.close();
}
