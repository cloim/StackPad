import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ locale: 'ko-KR', viewport: { width: 1280, height: 930 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const base = { kind: 'local', padset_id: 'default', command: 'node server.js', cwd: 'C:/Users/me/projects', health_url: '', color: '#97f7da', active: false, status: 'stopped', uptime: 120, memory: 42, autostart: false };
let services = [{ ...base, id: 'api', name: 'API', slot: 0, port: 8000 }, { ...base, id: 'web', name: 'Web', slot: 0, port: 5173 }, { ...base, id: 'single', name: '단독', slot: 1, port: 9000 }, { ...base, id: 'docker', kind: 'docker', name: '컨테이너', container: 'a'.repeat(64), container_ports: ['8080'], slot: 2 }];
const groups = [{ ...base, id: 'group', name: '통합 패드', member_ids: ['api', 'web'], slot: 0 }];
let deleted = 0;
let restarted = '';
let saved;
await page.route('http://stackpad.test/**', async route => {
  const url = new URL(route.request().url());
  if (url.pathname.startsWith('/api/')) {
    let body;
    if (url.pathname === '/api/auth') body = { configured: true, authenticated: true, local: true };
    else if (url.pathname === '/api/usage') body = { providers: [] };
    else if (url.pathname === '/api/services') body = { services, groups, padsets: [{ id: 'default', name: '기본' }], links: {} };
    else if (url.pathname === '/api/settings') body = { onboarding_done: true, recommend_roots: ['C:/Users/me/projects'], autostart: false, data_dir: 'C:/test' };
    else if (url.pathname === '/api/events') { await route.fulfill({ status: 503, body: 'SSE disabled in mock' }); return; }
    else if (url.pathname.endsWith('/logs')) body = { text: `${url.pathname.split('/')[3]} 로그` };
    else if (url.pathname.endsWith('/restart')) { restarted = url.pathname.split('/')[3]; body = { ok: true }; }
    else if (url.pathname.endsWith('/position')) { services.find(s => s.id === 'single').slot = route.request().postDataJSON().slot; body = { ok: true }; }
    else if (url.pathname === '/api/pads/single' && route.request().method() === 'DELETE') { deleted++; services = services.filter(s => s.id !== 'single'); body = { ok: true }; }
    else if (url.pathname === '/api/pads' && route.request().method() === 'POST') { saved = route.request().postDataJSON(); body = { id: 'new' }; }
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
  await expect(page.getByRole('button', { name: '통합 패드 메뉴', exact: true })).toBeVisible();
  await expect(page.locator('.toolbar-brand,.engine-status')).toHaveCount(0);
  await expect(page.locator('.pad-move svg')).toHaveCount(0);
  expect(await page.locator('.pad-move').first().evaluate(node => getComputedStyle(node).justifyContent)).toBe('flex-start');
  const rows = page.locator('.pad-wrap').first().locator('.pad-port>span');
  await expect(rows).toHaveText(['API :8000', 'Web :5173']);
  const boxes = await rows.evaluateAll(nodes => nodes.map(n => n.getBoundingClientRect().toJSON()));
  expect(boxes[1].top).toBeGreaterThanOrEqual(boxes[0].bottom);
  await page.getByRole('button', { name: '통합 패드 메뉴', exact: true }).click();
  await page.getByRole('menuitem', { name: '상세', exact: true }).click();
  const detail = page.getByRole('dialog');
  await expect(detail.getByRole('tab')).toHaveText(['API', 'Web']);
  await expect(detail.locator('dt')).toHaveText(['타입', '러닝타임', '메모리', 'PID', '포트']);
  await expect(detail.locator('pre')).toContainText('api 로그');
  await detail.getByRole('tab', { name: 'Web', exact: true }).click();
  await expect(detail.locator('pre')).toContainText('web 로그');
  await detail.getByRole('button', { name: 'Web 재시작' }).click();
  expect(restarted).toBe('web');
  await expect(detail.locator('.detail-name,.log-live,.delete-button')).toHaveCount(0);
  await expect(detail.getByRole('button', { name: /설정/ })).toHaveCount(0);
  await page.screenshot({ path: '.jobs/pad-ui-detail.png' });
  await page.keyboard.press('Escape');
  const title = page.getByRole('button', { name: '단독 자리 이동' });
  const source = await title.boundingBox();
  const target = await page.locator('[data-empty-slot="5"]').boundingBox();
  await page.mouse.move(source.x + source.width / 2, source.y + source.height / 2);
  await page.mouse.down();
  await page.mouse.move(target.x + target.width / 2, target.y + target.height / 2, { steps: 8 });
  await page.mouse.up();
  await expect.poll(() => services.find(s => s.id === 'single').slot).toBe(5);
  await page.getByRole('button', { name: '단독 메뉴', exact: true }).click();
  await page.getByRole('menuitem', { name: '삭제', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '패드 삭제' })).toBeVisible();
  expect(deleted).toBe(0);
  await page.getByRole('button', { name: '취소', exact: true }).click();
  expect(deleted).toBe(0);
  await page.getByRole('button', { name: '단독 메뉴', exact: true }).click();
  await page.getByRole('menuitem', { name: '삭제', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '삭제', exact: true }).click();
  await expect.poll(() => deleted).toBe(1);
  await page.getByRole('button', { name: '서비스 등록', exact: true }).click();
  const form = page.getByRole('dialog');
  await expect(form.getByRole('tab')).toHaveText(['일반', '서비스']);
  const selectBox = await form.getByLabel('패드셋', { exact: true }).boundingBox();
  const nameBox = await form.getByLabel('패드 이름', { exact: true }).boundingBox();
  expect(selectBox.height).toBe(nameBox.height);
  expect(Math.abs(selectBox.y - nameBox.y)).toBeLessThan(2);
  await expect(form.locator('.pad-location-row')).not.toContainText(/패드 \d/);
  await form.getByLabel('패드 이름', { exact: true }).fill('신규');
  await form.getByLabel('도메인 URL', { exact: true }).fill('https://example.com');
  await form.getByRole('button', { name: '저장', exact: true }).click();
  await expect(form.getByRole('tab', { name: '서비스', exact: true })).toHaveAttribute('aria-selected', 'true');
  await form.getByLabel('실행 명령', { exact: true }).fill('node server.js');
  await form.getByRole('tab', { name: '일반', exact: true }).click();
  await expect(form.getByLabel('도메인 URL', { exact: true })).toHaveValue('https://example.com');
  await form.getByRole('button', { name: '저장', exact: true }).click();
  await expect.poll(() => saved?.name).toBe('신규');
  expect(saved.components[0].command).toBe('node server.js');
  await page.getByRole('button', { name: '통합 패드 메뉴', exact: true }).click();
  await page.getByRole('menuitem', { name: '설정', exact: true }).click();
  await expect(form.getByText('표시된 순서대로 실행하고 역순으로 종료합니다. 색상은 패드 전체에 적용합니다.')).toHaveCount(0);
  await page.screenshot({ path: '.jobs/pad-ui-general.png' });
  await page.keyboard.press('Escape');
  services[0].active = true; services[0].pid = 12345; services[0].status = 'running';
  // The deck polls every two seconds, so wait for the running state instead of a refresh button.
  await expect(page.getByRole('button', { name: '통합 패드 종료', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '통합 패드 메뉴', exact: true }).click();
  await expect(page.getByRole('menuitem', { name: '삭제', exact: true })).toBeDisabled();
  await page.getByRole('menuitem', { name: '설정', exact: true }).click();
  await expect(form.getByLabel('패드 이름', { exact: true })).toHaveAttribute('readonly', '');
  await expect(form.getByText('실행 중인 패드의 설정을 확인하고 복사할 수 있어요. 변경하려면 패드를 중지해 주세요.')).toHaveCount(0);
  await expect(form.getByRole('button', { name: '저장', exact: true })).toHaveCount(0);
  await form.getByRole('tab', { name: '서비스', exact: true }).click();
  await expect(form.getByRole('textbox', { name: '실행 명령', exact: true }).first()).toHaveAttribute('readonly', '');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '컨테이너 메뉴', exact: true }).click();
  await page.getByRole('menuitem', { name: '상세', exact: true }).click();
  await expect(detail.getByRole('tab')).toHaveText(['컨테이너']);
  await expect(detail.locator('dd').first()).toHaveText('도커');
  await expect(detail.locator('dd').nth(4)).toHaveText('8080');
  await detail.getByRole('button', { name: '컨테이너 재시작' }).click();
  expect(restarted).toBe('docker');
  await page.keyboard.press('Escape');
  for (const viewport of [{ width: 640, height: 800 }, { width: 390, height: 844 }, { width: 1280, height: 500 }]) {
    await page.setViewportSize(viewport);
    await expect(page.getByRole('button', { name: '통합 패드 자리 이동' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `.jobs/pad-ui-${viewport.width}-${viewport.height}.png` });
  }
  expect(errors).toEqual([]);
  console.log('PASS: title drag, per-service ports, delete confirmation/cancel, detail tabs/restart/logs, form tabs/validation/save, responsive layouts');
} catch (error) {
  await page.screenshot({ path: '.jobs/pad-ui-test-fail.png', fullPage: true }).catch(() => {});
  throw error;
} finally { await browser.close(); }
