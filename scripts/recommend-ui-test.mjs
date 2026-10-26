import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ locale: 'ko-KR', viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const services = [{ id: 'wiki', name: 'Wiki', command: 'uv run uvicorn main:app --port 8000', cwd: 'C:\\Users\\me\\projects\\Wiki', port: 8000, health_url: '', color: '#ef4444', autostart: false, slot: 0, pid: null, status: 'stopped', uptime: 0 }];
const candidate = { key: 'c:\\users\\me\\projects\\sampleapp|C:\\Users\\me\\projects\\SampleApp\\.venv\\Scripts\\pythonw.exe main.py', pid: 2572, name: 'SampleApp', command: 'C:\\Users\\me\\projects\\SampleApp\\.venv\\Scripts\\pythonw.exe main.py', cwd: 'C:\\Users\\me\\projects\\SampleApp', port: 8765, ports: [8765], health_url: '' };
const settings = { data_dir: '테스트', autostart: false, recommend_roots: ['C:\\Users\\me\\projects'], recommend_hidden: [] };
const hidden = new Map();
const calls = { scans: 0, pads: [], hides: [], unhides: [], roots: [], resets: 0 };
await page.route('http://stackpad.test/**', async route => {
  const url = new URL(route.request().url());
  const method = route.request().method();
  if (url.pathname.startsWith('/api/')) {
    let body;
    if (url.pathname === '/api/auth') body = { configured: true, authenticated: true };
    else if (url.pathname === '/api/usage') body = { providers: [] };
    else if (url.pathname === '/api/services') body = { services, groups: [] };
    else if (url.pathname === '/api/settings') body = settings;
    else if (url.pathname === '/api/recommendations') { calls.scans++; body = { roots: settings.recommend_roots, candidates: hidden.has(candidate.key) ? [] : [candidate] }; }
    else if (url.pathname === '/api/recommendations/hidden' && method === 'POST') { const data = route.request().postDataJSON(); calls.hides.push(data); hidden.set(data.key, data); settings.recommend_hidden = [...hidden.values()]; body = { ok: true }; }
    else if (url.pathname === '/api/recommendations/unhide' && method === 'POST') { const { key } = route.request().postDataJSON(); calls.unhides.push(key); hidden.delete(key); settings.recommend_hidden = [...hidden.values()]; body = { ok: true }; }
    else if (url.pathname === '/api/recommendations/hidden' && method === 'DELETE') { calls.resets++; hidden.clear(); settings.recommend_hidden = []; body = { ok: true }; }
    else if (url.pathname === '/api/settings/recommend' && method === 'PUT') { const { roots } = route.request().postDataJSON(); calls.roots.push(roots); settings.recommend_roots = roots; body = { roots }; }
    else if (url.pathname === '/api/pads' && method === 'POST') { const data = route.request().postDataJSON(); calls.pads.push(data); services.push({ ...data.components[0], id: 'new', name: data.name, color: data.color, slot: data.slot, autostart: false, pid: null, status: 'external', external_pid: 2572 }); body = { id: 'new' }; }
    else throw new Error(`Unexpected API: ${method} ${url.pathname}`);
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
try {
  await page.goto('http://stackpad.test/');
  await page.getByRole('button', { name: '등록 추천', exact: true }).click();
  const panel = page.getByRole('dialog', { name: '등록 추천', exact: true });
  await expect(panel.getByText('SampleApp', { exact: true })).toBeVisible();
  await expect(panel).toContainText('스캔 폴더: C:\\Users\\me\\projects');
  await expect(panel).toContainText(':8765');
  await expect(panel).toContainText(candidate.command);
  // The list scans once on open even though the app keeps polling.
  await page.waitForTimeout(4500);
  expect(calls.scans).toBe(1);
  await panel.getByRole('button', { name: 'SampleApp 등록', exact: true }).click();
  await expect(panel).toHaveCount(0);
  const form = page.getByRole('dialog', { name: '서비스 등록', exact: true });
  await expect(form.getByLabel('패드 이름', { exact: true })).toHaveValue('SampleApp');
  // The first color no pad uses is preselected; Wiki already uses red.
  await expect(form.getByRole('button', { name: '살몬', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(form.getByLabel('실행 명령', { exact: false })).toHaveValue(candidate.command);
  await expect(form.getByLabel('작업 폴더', { exact: false })).toHaveValue(candidate.cwd);
  await expect(form.getByLabel('포트', { exact: false })).toHaveValue('8765');
  await expect(form.getByLabel('상태 확인 URL', { exact: false })).toHaveValue(candidate.health_url);
  await form.getByRole('button', { name: '저장', exact: true }).click();
  await expect(form).toHaveCount(0);
  expect(calls.pads).toHaveLength(1);
  expect(calls.pads[0]).toMatchObject({ name: 'SampleApp', slot: 1, components: [{ command: candidate.command, cwd: candidate.cwd, port: 8765, health_url: candidate.health_url }] });
  await expect(page.getByRole('button', { name: 'SampleApp 실행', exact: true })).toContainText('외부 실행');

  await page.getByRole('button', { name: '등록 추천', exact: true }).click();
  await panel.getByRole('button', { name: 'SampleApp 숨기기', exact: true }).click();
  await expect(panel).toContainText('추천할 서비스가 없습니다.');
  const details = { key: candidate.key, name: candidate.name, cwd: candidate.cwd, command: candidate.command };
  expect(calls.hides).toEqual([details]);
  await page.keyboard.press('Escape');

  await page.getByRole('button', { name: '환경 설정', exact: true }).click();
  await page.getByRole('tab', { name: '등록 추천', exact: true }).click();
  const roots = page.getByLabel('등록 추천 스캔 폴더', { exact: true });
  await expect(roots).toHaveValue('C:\\Users\\me\\projects');
  await expect(page.getByRole('heading', { name: '숨긴 추천 1개', exact: true })).toBeVisible();
  await expect(page.locator('.hidden-recommendations')).toContainText(candidate.command);
  await page.getByRole('button', { name: 'SampleApp 다시 표시', exact: true }).click();
  await expect.poll(() => calls.unhides).toEqual([candidate.key]);
  await expect(page.locator('.hidden-recommendations')).toHaveCount(0);
  await roots.fill('C:\\Users\\me\\projects\n\nE:\\WORK  ');
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await expect.poll(() => calls.roots.length).toBe(1);
  expect(calls.roots[0]).toEqual(['C:\\Users\\me\\projects', 'E:\\WORK']);
  await expect(page.locator('[data-toast]')).toBeVisible();
  await page.keyboard.press('Escape');

  await page.getByRole('button', { name: '등록 추천', exact: true }).click();
  await panel.getByRole('button', { name: 'SampleApp 숨기기', exact: true }).click();
  await expect(panel).toContainText('추천할 서비스가 없습니다.');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '환경 설정', exact: true }).click();
  await page.getByRole('tab', { name: '등록 추천', exact: true }).click();
  await expect(page.getByRole('heading', { name: '숨긴 추천 1개', exact: true })).toBeVisible();
  await page.screenshot({ path: 'docs/reviews/screenshots/recommend-settings-desktop.png' });
  await page.getByRole('button', { name: '모두 다시 표시', exact: true }).click();
  await expect.poll(() => calls.resets).toBe(1);
  await expect(page.locator('[data-toast]')).toBeVisible();
  await expect(page.locator('.hidden-recommendations')).toHaveCount(0);
  await page.keyboard.press('Escape');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '등록 추천', exact: true }).click();
  await expect(panel.getByText('SampleApp', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'docs/reviews/screenshots/recommend-mobile.png' });
  expect(errors).toEqual([]);
  console.log('RECOMMEND UI PASS: single scan on open, prefilled registration, external state after register, default unused color, hide, restore one, scan folders, restore all, mobile');
} finally {
  await browser.close();
}
