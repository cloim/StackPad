import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';

const base = 'http://127.0.0.1:48743';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ locale: 'ko-KR' });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.context().addCookies([{ name: 'stackpad_session', value: process.env.STACKPAD_TEST_SESSION || 'stackpad-ui-test-session', url: base }]);
  const request = async (path, data) => {
    const response = await page.request.post(`${base}/api${path}`, { headers: { origin: base }, data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const target = await request('/padsets', { name: '이동 대상' });
  const settings = await (await page.request.get(`${base}/api/settings`)).json();
  for (const count of [1, 2]) {
    const name = count === 1 ? '마지막 단일 패드' : '마지막 통합 패드';
    await request('/pads', { name, slot: 0, components: Array.from({ length: count }, (_, i) => ({ name: `구성 ${i}`, command: 'echo fixture', cwd: settings.data_dir })) });
    await page.goto(base);
    await page.getByRole('tab', { name: '기본', exact: true }).click();
    await page.getByRole('button', { name: `${name} 메뉴`, exact: true }).click();
    await page.getByRole('menuitem', { name: '설정', exact: true }).click();
    const editor = page.getByRole('dialog', { name: '패드 설정', exact: true });
    if (count === 1) {
      await editor.getByRole('button', { name: '저장', exact: true }).click();
      const detail = page.getByRole('dialog', { name, exact: true });
      await expect(detail).toBeVisible();
      await detail.getByRole('button', { name: '닫기', exact: true }).click();
      await page.getByRole('button', { name: `${name} 메뉴`, exact: true }).click();
      await page.getByRole('menuitem', { name: '설정', exact: true }).click();
    }
    await expect(editor.getByRole('combobox', { name: '패드셋', exact: true })).toBeEnabled();
    await editor.getByRole('combobox', { name: '패드셋', exact: true }).selectOption(target.id);
    await editor.getByRole('button', { name: '저장', exact: true }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.locator('.pad-wrap')).toHaveCount(0);
    await page.getByRole('tab', { name: '이동 대상', exact: true }).click();
    await expect(page.getByRole('button', { name: `${name} 메뉴`, exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByRole('button', { name: `${name} 메뉴`, exact: true })).toBeVisible();
  }
  const running = await request('/pads', { name: '실행 중 마지막 패드', slot: 0, components: [{ kind: 'docker', name: '컨테이너', container: 'a'.repeat(64) }] });
  await request(`/services/${running.id}/start`);
  await page.goto(base);
  await page.getByRole('tab', { name: '기본', exact: true }).click();
  await page.getByRole('button', { name: '실행 중 마지막 패드 메뉴', exact: true }).click();
  await page.getByRole('menuitem', { name: '설정', exact: true }).click();
  const editor = page.getByRole('dialog', { name: '패드 설정', exact: true });
  await expect(editor.getByLabel('패드 이름', { exact: true })).toBeEditable();
  await editor.getByRole('combobox', { name: '서비스 용도', exact: true }).selectOption('production');
  await editor.getByLabel('도메인 URL', { exact: true }).fill('https://app.example.com/');
  await editor.getByLabel('로컬 URL', { exact: true }).fill('http://localhost:8080/');
  await editor.getByLabel('관리 엔진 시작 시 패드 자동 실행').check();
  await editor.getByRole('tab', { name: '서비스', exact: true }).click();
  await expect(editor.getByRole('button', { name: '서비스 추가', exact: true })).toHaveCount(0);
  await editor.getByRole('tab', { name: '일반', exact: true }).click();
  await editor.getByRole('combobox', { name: '패드셋', exact: true }).selectOption(target.id);
  await expect(editor.getByRole('button', { name: '저장', exact: true })).toBeEnabled();
  await editor.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const state = await (await page.request.get(`${base}/api/services`)).json();
  const moved = state.services.find(service => service.id === running.id);
  expect(moved.padset_id).toBe(target.id);
  expect(moved.slot).toBe(2);
  expect(moved.active).toBe(true);
  expect(state.services.filter(service => service.padset_id === 'default')).toHaveLength(0);
  expect(moved.environment).toBe('production');
  expect(moved.autostart).toBe(true);
  await page.getByRole('tab', { name: '이동 대상', exact: true }).click();
  const wrap = page.locator('.pad-wrap').filter({ has: page.getByRole('button', { name: '실행 중 마지막 패드 메뉴', exact: true }) });
  await expect(wrap.locator('.pad-environment')).toHaveText('PRD');
  await fs.mkdir('.jobs/live-settings-ui', { recursive: true });
  await page.screenshot({ path: '.jobs/live-settings-ui/desktop.png' });
  await page.addInitScript(() => { window.open = url => { window.lastOpenedUrl = url; }; });
  await page.reload();
  await page.getByRole('button', { name: '실행 중 마지막 패드 메뉴', exact: true }).click();
  await expect(page.getByRole('menuitem', { name: '브라우저에서 열기', exact: true })).toHaveCount(1);
  await page.getByRole('menuitem', { name: '브라우저에서 열기', exact: true }).click();
  expect(await page.evaluate(() => window.lastOpenedUrl)).toBe('https://app.example.com/');
  for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 1000 }]) {
    await page.setViewportSize(viewport);
    const badge = await wrap.locator('.pad-environment').boundingBox();
    const menu = await wrap.getByRole('button', { name: '실행 중 마지막 패드 메뉴', exact: true }).boundingBox();
    const box = await wrap.boundingBox();
    expect(badge.y).toBeGreaterThanOrEqual(menu.y + menu.height);
    expect(badge.x).toBeGreaterThan(box.x + box.width / 2);
    expect(badge.y + badge.height).toBeLessThanOrEqual(box.y + box.height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `.jobs/live-settings-ui/${viewport.width}.png` });
  }
  await page.getByRole('button', { name: '실행 중 마지막 패드 메뉴', exact: true }).click();
  await page.getByRole('menuitem', { name: '설정', exact: true }).click();
  await page.getByRole('combobox', { name: '서비스 용도', exact: true }).selectOption('development');
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '닫기', exact: true }).click();
  await expect(wrap.locator('.pad-environment')).toHaveCount(0);
  await page.getByRole('button', { name: '실행 중 마지막 패드 메뉴', exact: true }).click();
  await expect(page.getByRole('menuitem', { name: '브라우저에서 열기', exact: true })).toHaveCount(1);
  await page.getByRole('menuitem', { name: '브라우저에서 열기', exact: true }).click();
  expect(await page.evaluate(() => window.lastOpenedUrl)).toBe('http://localhost:8080/');
  await request(`/services/${running.id}/stop`);
  expect(errors).toEqual([]);
  console.log('PASS: last single/group/running pad moves, occupied slots skipped, runtime preserved, live metadata editable, PRD badge and environment-specific browser menu verified on desktop/mobile, no detail modal, persisted after reload');
} finally {
  await browser.close();
}
