import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

await fs.mkdir('.jobs', { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ locale: 'ko-KR', viewport: { width: 1280, height: 930 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));

const base = {
  kind: 'local',
  padset_id: 'default',
  command: 'node server.js',
  cwd: 'C:/Users/me/projects',
  health_url: '',
  color: '#22c55e',
  active: true,
  status: 'running',
  uptime: 120,
  memory: 128,
  cpu: 45,
  autostart: false,
};

let services = [
  { ...base, id: 'api', name: 'API Server', slot: 0, cpu: 45, memory: 128, color: '#22c55e', active: true, status: 'running' },
  { ...base, id: 'worker', name: 'Worker', slot: 1, cpu: 0, memory: 0, color: '#3b82f6', active: true, status: 'starting' },
  { ...base, id: 'cron', name: 'Cron Job', slot: 2, cpu: 0, memory: 0, color: '#ef4444', active: false, status: 'error', error: 'Process crashed' },
  { ...base, id: 'idle', name: 'Idle Service', slot: 3, cpu: 0, memory: 0, color: '#a855f7', active: false, status: 'stopped' },
];

const mockHistory = {
  interval: 10,
  cpu: Array.from({ length: 60 }, (_, i) => Math.round(Math.sin(i / 5) * 40 + 50)),
  memory: Array.from({ length: 60 }, (_, i) => 100 + i * 2),
};

await page.route('http://stackpad.test/**', async route => {
  const url = new URL(route.request().url());
  if (url.pathname.startsWith('/api/')) {
    let body;
    if (url.pathname === '/api/auth') body = { configured: true, authenticated: true, local: true };
    else if (url.pathname === '/api/usage') body = { providers: [] };
    else if (url.pathname === '/api/services') body = { services, groups: [], padsets: [{ id: 'default', name: '기본' }], links: {} };
    else if (url.pathname === '/api/settings') body = { onboarding_done: true, recommend_roots: ['C:/Users/me/projects'], autostart: false, data_dir: 'C:/test', notifications: { crash: true, unhealthy: true, schedule: true } };
    else if (url.pathname === '/api/events') { await route.fulfill({ status: 503, body: 'SSE disabled in mock' }); return; }
    else if (url.pathname.endsWith('/history')) body = mockHistory;
    else if (url.pathname.endsWith('/logs')) body = { text: 'Server started successfully.\nReady on port 8000.' };
    else if (url.pathname.endsWith('/start') || url.pathname.endsWith('/stop')) body = { ok: true };
    else throw new Error(`Unexpected API: ${url.pathname}`);
    await route.fulfill({ json: body });
  } else {
    const file = path.resolve('dist', url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
    if (!file.startsWith(path.resolve('dist') + path.sep)) throw new Error('Invalid asset');
    await route.fulfill({ body: await fs.readFile(file), contentType: file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html' });
  }
});

try {
  await page.goto('http://stackpad.test/');
  await expect(page.getByRole('button', { name: 'API Server 종료' })).toBeVisible();

  // 1. Verify --cpu property on running pad
  const runningPadWrap = page.locator('.pad-wrap').first();
  const cpuVal = await runningPadWrap.evaluate(el => el.style.getPropertyValue('--cpu'));
  expect(Number(cpuVal)).toBeCloseTo(0.45, 2);

  // 2. Check LED ring pseudo-elements via getComputedStyle
  const hasRunningAfter = await runningPadWrap.locator('.pad.running').evaluate(el => {
    const style = window.getComputedStyle(el, '::after');
    return style.content !== 'none' && style.position === 'absolute';
  });
  expect(hasRunningAfter).toBe(true);

  const startingPad = page.locator('.pad.starting');
  const hasStartingAfter = await startingPad.evaluate(el => {
    const style = window.getComputedStyle(el, '::after');
    return style.content !== 'none';
  });
  expect(hasStartingAfter).toBe(true);

  const errorPad = page.locator('.pad.error');
  const hasErrorAfter = await errorPad.evaluate(el => {
    const style = window.getComputedStyle(el, '::after');
    return style.content !== 'none';
  });
  expect(hasErrorAfter).toBe(true);

  // 3. Open Detail modal and check LCD DotMatrix
  await page.getByRole('button', { name: 'API Server 메뉴' }).click();
  await page.getByRole('menuitem', { name: '상세' }).click();
  const modal = page.getByRole('dialog');
  await expect(modal).toBeVisible();

  const lcd = modal.locator('.lcd');
  await expect(lcd).toBeVisible();

  // Check 60 columns in DotMatrix SVG
  const dotCols = lcd.locator('.dot-matrix-svg g');
  await expect(dotCols).toHaveCount(60);

  // Check 8 rows in each column (total 480 rect elements)
  const dotRects = lcd.locator('.dot-matrix-svg rect');
  await expect(dotRects).toHaveCount(480);

  // Check toggling CPU / MEM in LCD head
  const lcdHead = lcd.locator('.lcd-head');
  await expect(lcdHead).toContainText('CPU USAGE');
  await lcdHead.click();
  await expect(lcdHead).toContainText('MEM USAGE');
  await lcdHead.click();
  await expect(lcdHead).toContainText('CPU USAGE');

  await page.keyboard.press('Escape');
  await expect(modal).not.toBeVisible();

  // 4. Verify device feedback controls were removed
  await page.getByRole('button', { name: '설정' }).click();
  const settingsModal = page.getByRole('dialog');
  await expect(settingsModal).toBeVisible();

  await expect(settingsModal.getByText('이 기기의 피드백', { exact: true })).toHaveCount(0);
  await expect(settingsModal.getByRole('switch', { name: '촉각 피드백' })).toHaveCount(0);
  await expect(settingsModal.getByRole('switch', { name: '소리 피드백' })).toHaveCount(0);

  await page.keyboard.press('Escape');

  // 5. Test multi-resolution viewports and capture screenshots
  const viewports = [
    { width: 1500, height: 900, name: '.jobs/design-1500.png' },
    { width: 1100, height: 800, name: '.jobs/design-1100.png' },
    { width: 900, height: 700, name: '.jobs/design-900.png' },
    { width: 650, height: 700, name: '.jobs/design-650.png' },
  ];

  for (const vp of viewports) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.waitForTimeout(100);
    await page.screenshot({ path: vp.name });
  }

  expect(errors).toEqual([]);
  console.log('design-ui-test: ALL CHECKS PASSED');
} finally {
  await browser.close();
}
