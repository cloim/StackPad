// Run after npm run build. Uses an in-browser mock API; starts no local server.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ locale: 'ko-KR', viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const service = { id: 'api', kind: 'local', name: 'API', command: 'node server.js', cwd: 'C:/example', padset_id: 'default', slot: 0, color: '#97f7da', status: 'stopped', environment: 'development' };
let services = [service];
let scenes = [{ id: 'flow', name: '개발 환경', color: '#97f7da', pad_ids: ['api'] }];
let schedules = [{ id: 'existing', target_type: 'pad', target_id: 'api', action: 'start', time: '08:00', days: [0, 1, 2, 3, 4], enabled: true }];
const writes = [];
let failSchedule = false;
let sequence = 0;
await page.route('http://stackpad.test/**', async route => {
  const request = route.request();
  const url = new URL(request.url());
  if (!url.pathname.startsWith('/api/')) {
    const file = path.resolve('dist', url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
    if (!file.startsWith(path.resolve('dist') + path.sep)) throw Error('Invalid asset');
    await route.fulfill({ body: await fs.readFile(file), contentType: file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html' });
    return;
  }
  const endpoint = url.pathname.slice(4);
  let body;
  if (request.method() !== 'GET') {
    const values = request.postDataJSON();
    writes.push({ endpoint, method: request.method(), values });
    if (endpoint.startsWith('/pads')) {
      const id = endpoint.split('/')[2] || `pad-${++sequence}`;
      const entry = { ...service, ...values, id, ...values.components[0], name: values.name };
      services = [...services.filter(s => s.id !== id), entry];
      body = { id };
    } else if (endpoint.startsWith('/scenes')) {
      expect(values || {}).not.toHaveProperty('id');
      const id = endpoint.split('/')[2] || `flow-${++sequence}`;
      if (request.method() === 'DELETE') scenes = scenes.filter(s => s.id !== id);
      else scenes = [...scenes.filter(s => s.id !== id), { ...values, id }];
      body = { id };
    } else if (endpoint.startsWith('/schedules')) {
      if (failSchedule && values?.time === '12:00') { failSchedule = false; await route.fulfill({ status: 500, json: { detail: '테스트 저장 실패' } }); return; }
      expect(values || {}).not.toHaveProperty('id');
      const id = endpoint.split('/')[2] || `schedule-${++sequence}`;
      if (request.method() === 'DELETE') schedules = schedules.filter(s => s.id !== id);
      else schedules = [...schedules.filter(s => s.id !== id), { ...values, id }];
      body = { id };
    } else throw Error(`Unexpected write ${endpoint}`);
  } else if (endpoint === '/auth') body = { configured: true, authenticated: true, local: true, owner: true };
  else if (endpoint === '/services') body = { services, groups: [], scenes, schedules, padsets: [{ id: 'default', name: '기본' }], links: {} };
  else if (endpoint === '/usage') body = { providers: [] };
  else if (endpoint === '/settings') body = { onboarding_done: true, recommend_roots: ['C:/example'], tools: {} };
  else if (endpoint === '/events') { await route.fulfill({ status: 503, body: '' }); return; }
  else throw Error(`Unexpected API ${endpoint}`);
  await route.fulfill({ json: body });
});

const editor = () => page.getByRole('dialog', { name: /패드 설정|서비스 등록/, exact: true });
async function openPad() {
  await page.getByRole('button', { name: 'API 메뉴', exact: true }).click();
  await page.getByRole('menuitem', { name: '설정', exact: true }).click();
}
async function addSchedule(time, targetType = 'pad') {
  await editor().getByRole('tab', { name: '예약', exact: true }).click();
  await editor().getByRole('button', { name: '예약 추가', exact: true }).click();
  const modal = page.getByRole('dialog', { name: '예약 추가', exact: true });
  if (targetType === 'scene') await modal.getByLabel('대상 종류', { exact: true }).selectOption('scene');
  await modal.getByLabel('시각', { exact: true }).fill(time);
  await modal.getByRole('button', { name: '저장', exact: true }).click();
  await expect(modal).toHaveCount(0);
}
try {
  await page.goto('http://stackpad.test/');
  const registration = page.getByRole('button', { name: '서비스 등록', exact: true });
  await expect(registration.locator('xpath=following-sibling::button[1]')).toHaveAttribute('aria-label', '흐름 관리');
  await openPad();
  await expect(editor().getByRole('tab')).toHaveText(['일반', '서비스', '예약', '흐름']);
  await addSchedule('10:15');
  expect(writes).toHaveLength(0);
  await editor().getByRole('tab', { name: '흐름', exact: true }).click();
  await editor().getByLabel('개발 환경', { exact: true }).uncheck();
  await editor().getByRole('button', { name: '취소', exact: true }).click();
  await page.getByRole('dialog', { name: '저장하지 않은 변경 사항' }).getByRole('button', { name: '버리고 닫기' }).click();
  expect(writes).toHaveLength(0);
  expect(scenes[0].pad_ids).toEqual(['api']);
  expect(schedules).toHaveLength(1);

  await openPad();
  await editor().getByRole('tab', { name: '예약', exact: true }).click();
  await editor().getByRole('button', { name: '08:00 예약 편집', exact: true }).click();
  const scheduleEdit = page.getByRole('dialog', { name: '예약 편집', exact: true });
  await scheduleEdit.getByLabel('시각', { exact: true }).fill('08:30');
  await scheduleEdit.getByRole('button', { name: '저장', exact: true }).click();
  await editor().getByRole('switch').click();
  await addSchedule('10:15');
  await editor().getByRole('tab', { name: '흐름', exact: true }).click();
  await editor().getByRole('button', { name: '개발 환경 흐름 편집', exact: true }).click();
  const flowEdit = page.getByRole('dialog', { name: '흐름 편집', exact: true });
  await flowEdit.getByLabel('흐름 이름', { exact: true }).fill('작업 환경');
  await flowEdit.getByRole('button', { name: '저장', exact: true }).click();
  expect(writes).toHaveLength(0);
  await editor().getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor()).toHaveCount(0);
  expect(schedules.find(s => s.id === 'existing')).toMatchObject({ time: '08:30', enabled: false });
  expect(schedules.some(s => s.time === '10:15')).toBe(true);
  expect(scenes[0].name).toBe('작업 환경');

  await openPad();
  await editor().getByRole('tab', { name: '예약', exact: true }).click();
  await editor().getByRole('button', { name: '10:15 예약 삭제', exact: true }).click();
  await editor().getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor()).toHaveCount(0);
  expect(schedules).toHaveLength(1);

  // A new pad can link to an existing flow and get a schedule in the same save.
  await page.getByRole('button', { name: '서비스 등록', exact: true }).click();
  await editor().getByLabel('패드 이름', { exact: true }).fill('새 서비스');
  await editor().getByRole('tab', { name: '서비스', exact: true }).click();
  await editor().getByLabel('실행 명령', { exact: true }).fill('node app.js');
  await addSchedule('11:00');
  await addSchedule('12:00');
  await editor().getByRole('tab', { name: '흐름', exact: true }).click();
  await editor().getByLabel('작업 환경', { exact: true }).check();
  failSchedule = true;
  await editor().getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByText(/패드는 저장됐지만 예약 또는 흐름 반영/)).toBeVisible();
  await expect(editor()).toBeVisible();
  await editor().getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor()).toHaveCount(0);
  expect(writes.filter(w => w.endpoint === '/pads' && w.method === 'POST')).toHaveLength(1);
  const newPad = services.find(s => s.name === '새 서비스');
  expect(scenes[0].pad_ids).toEqual(['api', newPad.id]);
  expect(schedules.filter(s => s.target_id === newPad.id)).toHaveLength(2);
  expect(schedules.filter(s => s.target_id === newPad.id && s.time === '11:00')).toHaveLength(1);
  expect(schedules.find(s => s.target_id === newPad.id).time).toBe('11:00');

  // Global flow management remains available even with no flows.
  await page.getByRole('button', { name: '흐름 관리', exact: true }).click();
  const manager = page.getByRole('dialog', { name: '흐름 관리', exact: true });
  await manager.getByRole('button', { name: '작업 환경 흐름 편집', exact: true }).click();
  const orderedFlow = page.getByRole('dialog', { name: '흐름 편집', exact: true });
  await orderedFlow.getByRole('button', { name: '새 서비스 순서 앞으로', exact: true }).click();
  await orderedFlow.getByRole('button', { name: '저장', exact: true }).click();
  await expect(orderedFlow).toHaveCount(0);
  expect(scenes[0].pad_ids).toEqual([newPad.id, 'api']);
  await expect(manager.getByRole('button', { name: '예약 추가', exact: true })).toHaveCount(0);
  await expect(manager.getByRole('heading', { name: '예약 관리', exact: true })).toHaveCount(0);
  await page.keyboard.press('Escape');
  schedules.push({ id: 'flow-schedule', target_type: 'scene', target_id: 'flow', action: 'stop', time: '18:00', days: [0, 1, 2, 3, 4], enabled: true });
  await page.reload();
  await openPad();
  await editor().getByRole('tab', { name: '예약', exact: true }).click();
  await expect(editor().getByText('흐름: 작업 환경', { exact: true })).toBeVisible();
  await editor().getByRole('button', { name: '18:00 예약 편집', exact: true }).click();
  const legacySchedule = page.getByRole('dialog', { name: '예약 편집', exact: true });
  await expect(legacySchedule.getByLabel('대상 종류').locator('option')).toHaveText(['흐름']);
  await legacySchedule.getByLabel('시각', { exact: true }).fill('18:30');
  await legacySchedule.getByRole('button', { name: '저장', exact: true }).click();
  await addSchedule('19:00', 'scene');
  await editor().getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor()).toHaveCount(0);
  expect(schedules.find(s => s.id === 'flow-schedule')).toMatchObject({ target_type: 'scene', target_id: 'flow', time: '18:30' });
  expect(schedules.find(s => s.time === '19:00')).toMatchObject({ target_type: 'scene', target_id: 'flow' });
  scenes = [];
  await page.reload();
  await page.getByRole('button', { name: '흐름 관리', exact: true }).click();
  await manager.getByRole('button', { name: '흐름 추가', exact: true }).click();
  const newFlow = page.getByRole('dialog', { name: '흐름 추가', exact: true });
  await newFlow.getByLabel('흐름 이름', { exact: true }).fill('새 흐름');
  await newFlow.getByRole('button', { name: '저장', exact: true }).click();
  await expect(newFlow).toHaveCount(0);
  expect(scenes[0].name).toBe('새 흐름');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '환경 설정', exact: true }).click();
  await expect(page.getByRole('tab', { name: '흐름 및 예약', exact: true })).toHaveCount(0);
  await page.keyboard.press('Escape');
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await openPad();
    await editor().getByRole('tab', { name: '예약', exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `.jobs/pad-automation-${viewport.width}.png` });
    await page.keyboard.press('Escape');
  }
  expect(errors).toEqual([]);
  console.log('PASS: staged schedule CRUD/toggle, flow membership/edit, cancel, new pad, retry without duplicates, global flows, scene schedules, settings cleanup, mobile');
} catch (error) {
  await page.screenshot({ path: '.jobs/pad-automation-fail.png', fullPage: true }).catch(() => {});
  throw error;
} finally {
  await browser.close();
}
