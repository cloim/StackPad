import { chromium, expect } from '@playwright/test';

// Run against the production assets served by scripts/padsets-ui-worker.py.
// The shared tray stylesheet is extracted before the main modal stylesheet by Vite.
const base = 'http://127.0.0.1:48743';
const browser = await chromium.launch({ headless: true });
let page, padId;
try {
  page = await browser.newPage({ locale: 'ko-KR' });
  await page.context().addCookies([{ name: 'stackpad_session', value: 'stackpad-ui-test-session', url: base }]);
  await page.goto(base);
  const response = await page.request.post(`${base}/api/pads`, {
    headers: { Origin: base },
    data: { name: '모달 검증', slot: 1, components: [
      { kind: 'local', name: 'postgres', command: 'echo fixture', cwd: process.cwd() },
      { kind: 'local', name: 'redis', command: 'echo fixture', cwd: process.cwd() },
    ] },
  });
  expect(response.ok(), await response.text()).toBe(true);
  padId = (await response.json()).id;
  await page.reload();
  for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.getByRole('button', { name: '모달 검증 메뉴', exact: true }).click();
    await page.getByRole('menuitem', { name: '상세', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '모달 검증', exact: true });
    await expect(dialog).toHaveCSS('background-color', 'rgb(40, 44, 46)');
    await expect(dialog.locator('.modal-body')).toHaveCSS('color', 'rgb(217, 223, 223)');
    await expect(dialog.locator('.modal-title')).toHaveCSS('color', 'rgb(228, 232, 231)');
    await expect(dialog.getByRole('tab', { name: 'postgres', exact: true })).toBeVisible();
    await expect(dialog.getByRole('tab', { name: 'redis', exact: true })).toBeVisible();
    expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    await page.screenshot({ path: `.jobs/modal-detail-${viewport.width}.png` });
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await page.getByRole('button', { name: '환경 설정', exact: true }).click();
    await expect(page.getByRole('dialog')).toHaveCSS('background-color', 'rgb(40, 44, 46)');
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: '패드 1 서비스 등록', exact: true }).click();
    await expect(page.getByRole('dialog')).toHaveCSS('background-color', 'rgb(40, 44, 46)');
    await page.keyboard.press('Escape');
  }
  console.log('MODAL THEME PASS: production CSS, group detail tabs, settings, registration, desktop/mobile, Escape');
} finally {
  if (padId) await page.request.delete(`${base}/api/pads/${padId}`, { headers: { Origin: base } });
  await browser.close();
}
