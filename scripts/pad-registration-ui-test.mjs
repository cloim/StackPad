import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ locale: 'ko-KR', viewport: { width: 1280, height: 930 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
let serial = 10;
let services = ['Shop 백엔드', 'Shop 프론트엔드', 'Wiki'].map((name, i) => ({ id: String(i), name, slot: i < 2 ? 0 : 2, color: '#7db5eb', command: 'npm run dev', cwd: 'C:/Users/me/projects', port: 8000 + i, health_url: '', autostart: false, pid: i < 2 ? i + 100 : null, status: i < 2 ? 'running' : 'stopped', uptime: 120 }));
let groups = [{ id: 'app', name: 'Shop', member_ids: ['0', '1'], slot: 0, color: '#7db5eb', autostart: false, wait_ready: true }];
const positions = [];
const actions = [];
await page.route('http://stackpad.test/**', async route => {
  const url = new URL(route.request().url());
  const method = route.request().method();
  let body;
  if (url.pathname.startsWith('/api/')) {
    if (url.pathname === '/api/auth') body = { configured: true, authenticated: true };
    else if (url.pathname === '/api/usage') body = { providers: [] };
    else if (url.pathname === '/api/services') body = { services, groups };
    else if (url.pathname === '/api/settings') body = { onboarding_done: true, recommend_roots: ['C:/Users/me/projects'], hostname: 'TEST', cpu: 10, memory: 20 };
    else if (url.pathname.endsWith('/logs')) body = { text: 'component log\nREADY' };
    else if (/\/pads\/[^/]+\/position$/.test(url.pathname)) {
      const id = url.pathname.split('/')[3];
      const slot = route.request().postDataJSON().slot;
      const group = groups.find(g => g.id === id);
      const ids = group?.member_ids || [id];
      if (services.some(s => s.slot === slot && !ids.includes(s.id))) return route.fulfill({ status: 409, json: { detail: '빈 패드로 이동해 주세요.' } });
      services.filter(s => ids.includes(s.id)).forEach(s => { s.slot = slot; });
      if (group) group.slot = slot;
      positions.push({ id, slot }); body = { ok: true };
    } else if (url.pathname === '/api/pads' || (method === 'PUT' && /^\/api\/pads\/[^/]+$/.test(url.pathname))) {
      const data = route.request().postDataJSON();
      const oldId = url.pathname.split('/')[3];
      const oldGroup = groups.find(g => g.id === oldId);
      const oldIds = oldGroup?.member_ids || (oldId ? [oldId] : []);
      const members = data.components.map(c => ({ ...c, id: c.id || String(serial++), name: data.components.length === 1 ? data.name : c.name, slot: data.slot, color: data.color, autostart: data.autostart, pid: null, status: 'stopped', uptime: 0 }));
      services = [...services.filter(s => !oldIds.includes(s.id)), ...members];
      groups = groups.filter(g => g.id !== oldId);
      const id = data.components.length > 1 ? oldGroup?.id || `group-${serial++}` : members[0].id;
      if (data.components.length > 1) groups.push({ id, name: data.name, slot: data.slot, color: data.color, autostart: data.autostart, wait_ready: data.wait_ready, member_ids: members.map(s => s.id) });
      body = { id };
    } else if (url.pathname.endsWith('/start') || url.pathname.endsWith('/stop')) { actions.push(url.pathname); body = { ok: true }; }
    else if (url.pathname === '/api/events') { await route.fulfill({ status: 503, body: 'SSE disabled in mock' }); return; }
    else throw new Error(`Unexpected API: ${method} ${url.pathname}`);
    if (url.pathname === '/api/services') {
      body.padsets = [{ id: 'default', name: '기본' }];
      body.services.forEach(service => { service.active = !!service.pid; });
      [...body.services, ...(body.groups || [])].forEach(pad => { pad.padset_id = 'default'; });
    }
    await route.fulfill({ json: body });
  } else {
    const file = path.resolve('dist', url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
    if (!file.startsWith(path.resolve('dist') + path.sep)) throw new Error('Invalid asset path');
    await route.fulfill({ body: await fs.readFile(file), contentType: file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html' });
  }
});
// dnd-kit starts a drag after a few pixels of pointer movement, so move in steps instead of one jump.
async function dragTo(page, source, target) {
  const from = await source.boundingBox();
  const to = await target.boundingBox();
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 12 });
  await page.waitForTimeout(100);
  await page.mouse.up();
}
try {
  await page.goto('http://stackpad.test/');
  await expect(page.getByRole('button', { name: '서비스 그룹', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '패드 2 서비스 등록', exact: true }).click();
  const registration = page.getByRole('dialog', { name: '서비스 등록', exact: true });
  await registration.getByLabel('패드 이름', { exact: true }).fill('NOVA');
  await registration.getByRole('button', { name: '오렌지', exact: true }).click();
  await registration.getByRole('tab', { name: '서비스', exact: true }).click();
  await registration.getByRole('region', { name: '서비스 1', exact: true }).getByLabel('실행 명령', { exact: false }).fill('uv run uvicorn main:app');
  await registration.getByRole('button', { name: '서비스 추가', exact: true }).click();
  const first = registration.getByRole('region', { name: '서비스 1', exact: true });
  const second = registration.getByRole('region', { name: '서비스 2', exact: true });
  await first.getByLabel('서비스 이름', { exact: true }).fill('백엔드');
  await second.getByLabel('서비스 이름', { exact: true }).fill('프론트엔드');
  await second.getByLabel('실행 명령', { exact: false }).fill('npm run dev');
  await expect(registration.locator('.color-field')).toHaveCount(1);
  await registration.getByRole('button', { name: '서비스 2 순서 앞으로' }).click();
  await expect(first.getByLabel('서비스 이름', { exact: true })).toHaveValue('프론트엔드');
  await registration.getByRole('button', { name: '서비스 1 순서 뒤로' }).click();
  await registration.getByRole('button', { name: '서비스 추가', exact: true }).click();
  await registration.getByRole('button', { name: '서비스 3 제거', exact: true }).click();
  await registration.locator('.modal-body').evaluate(element => { element.scrollTop = 0; });
  await page.screenshot({ path: '.jobs/pad-registration-desktop.png' });
  await registration.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByRole('button', { name: 'NOVA 실행', exact: true })).toBeVisible();
  const nova = groups.find(g => g.name === 'NOVA');
  expect(nova.member_ids.map(id => services.find(s => s.id === id).name)).toEqual(['백엔드', '프론트엔드']);
  expect(services.filter(s => nova.member_ids.includes(s.id)).every(s => s.color === '#f97316')).toBe(true);
  await dragTo(page, page.getByRole('button', { name: 'NOVA 자리 이동', exact: true }), page.getByRole('button', { name: '패드 5 서비스 등록', exact: true }));
  await expect.poll(() => nova.slot).toBe(4);
  await dragTo(page, page.getByRole('button', { name: 'Shop 자리 이동', exact: true }), page.getByRole('button', { name: '패드 9 서비스 등록', exact: true }));
  await expect.poll(() => groups.find(g => g.id === 'app').slot).toBe(8);
  expect(services.slice(0, 2).map(s => s.pid)).toEqual([100, 101]);
  await dragTo(page, page.getByRole('button', { name: 'NOVA 자리 이동', exact: true }), page.getByRole('button', { name: 'Wiki 실행', exact: true }));
  expect(positions).toHaveLength(2);
  expect(actions).toEqual([]);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  // A running pad keeps its run commands locked and says so; name and color stay editable pad settings.
  // dnd-kit swallows a click that lands in the same instant as a drag ends; a person never clicks that fast.
  await page.waitForTimeout(150);
  await page.getByRole('button', { name: 'Shop 메뉴', exact: true }).click(); await page.getByRole('menuitem', { name: '설정' }).click();
  const settings = page.getByRole('dialog', { name: '패드 설정', exact: true });
  await expect(settings.getByRole('note')).toContainText('실행 중인 패드');
  await expect(settings.getByLabel('패드 이름', { exact: true })).toBeEditable();
  await expect(settings.locator('fieldset', { hasText: '패드 색상' })).toHaveCount(1);
  await expect(settings.getByRole('button', { name: '블루', exact: true })).toBeEnabled();
  await settings.getByRole('tab', { name: '서비스', exact: true }).click();
  await expect(settings.locator('section[aria-label="서비스 1"] fieldset')).toHaveCount(0);
  await expect(settings.getByRole('button', { name: '서비스 추가', exact: true })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 390, height: 844 });
  // Use real Chromium touch input to exercise pointer capture and touch hit testing.
  const cdp = await page.context().newCDPSession(page);
  const handle = await page.getByRole('button', { name: 'Shop 자리 이동', exact: true }).boundingBox();
  const target = await page.getByRole('button', { name: '패드 8 서비스 등록', exact: true }).boundingBox();
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: handle.x + handle.width / 2, y: handle.y + handle.height / 2 }] });
  for (const step of [0.25, 0.5, 0.75, 1]) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: handle.x + handle.width / 2 + (target.x + target.width / 2 - handle.x - handle.width / 2) * step, y: handle.y + handle.height / 2 + (target.y + target.height / 2 - handle.y - handle.height / 2) * step }] });
  await expect(page.locator('[data-empty-slot].border-2')).toHaveCount(1);
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await expect.poll(() => groups.find(g => g.id === 'app').slot).toBe(7);
  expect(actions).toEqual([]);
  expect(services.slice(0, 2).map(s => s.pid)).toEqual([100, 101]);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '.jobs/pad-move-mobile.png' });
  await page.getByRole('button', { name: '서비스 등록', exact: true }).click();
  const mobile = page.getByRole('dialog');
  await mobile.getByLabel('패드 이름', { exact: true }).fill('모바일 등록');
  await mobile.getByRole('tab', { name: '서비스', exact: true }).click();
  await mobile.getByRole('button', { name: '서비스 추가', exact: true }).click();
  await expect(mobile.locator('section[aria-label^="서비스 "]')).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '.jobs/pad-registration-mobile.png' });
  expect(errors).toEqual([]);
  console.log('PAD REGISTRATION UI PASS: inline services, shared color, order/removal, atomic registration, readonly, native desktop drag, occupied target, real mobile touch drag, no pad numbers, no run/stop on drop, toolbar registration');
} catch (error) {
  await page.screenshot({ path: '.jobs/pad-registration-ui-test-fail.png', fullPage: true }).catch(() => {});
  throw error;
} finally { await browser.close(); }
