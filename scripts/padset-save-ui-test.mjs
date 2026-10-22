import { chromium, expect } from '@playwright/test';

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
  await expect(editor.getByLabel('패드 이름', { exact: true })).not.toBeEditable();
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
  await request(`/services/${running.id}/stop`);
  expect(errors).toEqual([]);
  console.log('PASS: last single/group/running pad moves, occupied slots skipped, runtime preserved, settings locked, no detail modal, persisted after reload');
} finally {
  await browser.close();
}
