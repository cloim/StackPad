// Real engine with a scripted ssh: register, test, start, inspect and fail remote pads in the browser.
import { chromium, expect } from '@playwright/test';
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const work = await fs.mkdtemp(path.join(os.tmpdir(), 'stackpad-remote-ui-'));
const shots = process.argv[2] || work;
const python = path.join(root, '.venv', 'Scripts', 'python.exe');
const state = path.join(work, 'ssh');
await fs.mkdir(state);
await fs.mkdir(shots, { recursive: true });
const fakeSsh = path.join(work, 'fake-ssh.cmd');
await fs.writeFile(fakeSsh, `@"${python}" "${path.join(root, 'tests', 'fake_ssh.py')}" %*\r\n`);
await fs.writeFile(path.join(work, 'ssh_config'), 'Host *\n  ServerAliveInterval 30\nHost app\n  HostName 10.0.0.5\nHost down\n  HostName 10.0.0.9\n');
const port = 48735;
const base = `http://127.0.0.1:${port}`;
const session = 'stackpad-ui-test-session';
spawnSync(python, [path.join(root, 'scripts', 'ui_session.py'), path.join(work, 'data'), session], { stdio: 'ignore' });
const engine = spawn(python, [path.join(root, 'backend', 'main.py'), '--data-dir', path.join(work, 'data'), '--port', String(port), '--web-dir', path.join(root, 'dist')], {
  cwd: root, stdio: 'ignore', windowsHide: true,
  env: { ...process.env, STACKPAD_SSH: fakeSsh, STACKPAD_SSH_CONFIG: path.join(work, 'ssh_config'), FAKE_SSH_STATE: state },
});
const browser = await chromium.launch({ headless: true });
const errors = [];
try {
  for (let i = 0; ; i++) {
    try { if ((await fetch(`${base}/api/health`)).ok) break; } catch { /* starting */ }
    if (i > 100) throw new Error('engine did not start');
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  const page = await browser.newPage({ locale: 'ko-KR', viewport: { width: 1280, height: 930 } });
  page.on('pageerror', error => errors.push(error.message));
  await page.context().addCookies([{ name: 'stackpad_session', value: session, url: base }]);
  await page.goto(base);

  // Register a remote pad with the systemd helper and a connection test.
  await page.getByRole('button', { name: '패드 1 서비스 등록' }).click();
  await page.getByLabel('패드 이름').fill('주문 API');
  await page.getByRole('tab', { name: '서비스', exact: true }).click();
  await page.getByRole('radio', { name: '원격 서버' }).click();
  await expect(page.getByRole('radio', { name: '원격 서버' })).toHaveAttribute('aria-checked', 'true');
  await expect(page.getByLabel('실행 명령')).toHaveCount(0);
  await expect(page.locator('datalist option')).toHaveCount(2);
  await page.getByLabel('호스트', { exact: true }).fill('app');
  await page.getByRole('button', { name: '접속 테스트' }).click();
  await expect(page.getByRole('status').filter({ hasText: '접속을 확인했습니다.' })).toBeVisible();
  await page.getByLabel('systemd 서비스 이름').fill('order-api');
  await page.getByRole('button', { name: '명령 채우기' }).click();
  await expect(page.getByLabel('시작 명령', { exact: true })).toHaveValue('sudo systemctl start order-api');
  await expect(page.getByLabel('상태 명령', { exact: true })).toHaveValue('systemctl is-active --quiet order-api');
  await page.getByRole('tab', { name: '일반', exact: true }).click();
  await expect(page.getByText('자동 실행 대상에서 제외됩니다')).toBeVisible();
  await page.screenshot({ path: path.join(shots, 'remote-form-pc.png') });
  await page.getByRole('button', { name: '저장' }).click();

  const pad = page.getByRole('button', { name: '주문 API 실행' });
  await expect(pad).toContainText('app');
  await expect(pad).toContainText('중지됨', { timeout: 10000 });
  await pad.click();
  const running = page.getByRole('button', { name: '주문 API 종료' });
  await expect(running).toContainText(/시작 중|실행 중/, { timeout: 15000 });
  await expect(running).toContainText('실행 중', { timeout: 15000 });

  // The menu has no VS Code entry and the detail shows host, last command and remote logs.
  await page.getByRole('button', { name: '주문 API 메뉴' }).click();
  await expect(page.getByRole('menuitem', { name: 'VSCode로 열기' })).toHaveCount(0);
  await page.getByRole('menuitem', { name: '상세' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('호스트');
  await expect(dialog).toContainText('시작 성공');
  await expect(dialog.locator('.log-panel pre')).toContainText('line 2 한글', { timeout: 10000 });
  await expect(dialog).toContainText('실행 로그');
  await page.screenshot({ path: path.join(shots, 'remote-detail-pc.png') });
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);

  // An unreachable host shows a connection failure.
  await page.getByRole('button', { name: '패드 2 서비스 등록' }).click();
  await page.getByLabel('패드 이름').fill('NAS');
  await page.getByRole('tab', { name: '서비스', exact: true }).click();
  await page.getByRole('radio', { name: '원격 서버' }).click();
  await page.getByLabel('호스트', { exact: true }).fill('down');
  await page.getByLabel('systemd 서비스 이름').fill('nas-app');
  await page.getByRole('button', { name: '명령 채우기' }).click();
  await page.getByRole('button', { name: '저장' }).click();
  await expect(page.getByRole('button', { name: 'NAS 실행' })).toContainText('연결 실패', { timeout: 15000 });
  await page.screenshot({ path: path.join(shots, 'remote-pads-pc.png') });

  // Stopping runs the stop command.
  await running.click();
  await expect(page.getByRole('button', { name: '주문 API 실행' })).toContainText('중지됨', { timeout: 15000 });
  const calls = await fs.readFile(path.join(state, 'calls.log'), 'utf8');
  for (const expected of ['app\ttrue', 'app\tsudo systemctl start order-api', 'app\tsudo systemctl stop order-api', 'app\tjournalctl -u order-api -n 300 --no-pager']) {
    if (!calls.includes(expected)) throw new Error(`missing ssh call: ${expected}`);
  }

  // Pad menu links: domain and local addresses open in a new browser window; pads without addresses hide them.
  await page.evaluate(() => { window.__opened = []; window.open = url => { window.__opened.push(url); return null; }; });
  await page.getByRole('button', { name: '패드 4 서비스 등록' }).click();
  await page.getByLabel('패드 이름').fill('웹앱');
  await page.getByLabel('도메인 URL').fill('https://webapp.example.com/');
  await page.getByRole('tab', { name: '서비스', exact: true }).click();
  await page.getByLabel('실행 명령').fill('echo web');
  await page.getByLabel('작업 폴더').fill(root);
  await page.getByLabel('포트').fill('48799');
  await page.getByPlaceholder('http://127.0.0.1:8000/health').fill('http://127.0.0.1:48799/app/');
  await page.getByRole('button', { name: '저장' }).click();
  await page.getByRole('button', { name: '웹앱 메뉴' }).click();
  await page.screenshot({ path: path.join(shots, 'pad-menu-links-pc.png') });
  await page.getByRole('menuitem', { name: '도메인으로 열기' }).click();
  await page.getByRole('button', { name: '웹앱 메뉴' }).click();
  await page.getByRole('menuitem', { name: '로컬로 열기' }).click();
  const opened = await page.evaluate(() => window.__opened);
  if (JSON.stringify(opened) !== JSON.stringify(['https://webapp.example.com/', 'http://127.0.0.1:48799/app/'])) throw new Error(`unexpected opened links: ${opened}`);
  await page.getByRole('button', { name: '주문 API 메뉴' }).click();
  await expect(page.getByRole('menuitem', { name: '상세' })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: '도메인으로 열기' })).toHaveCount(0);
  await expect(page.getByRole('menuitem', { name: '로컬로 열기' })).toHaveCount(0);
  await page.keyboard.press('Escape');

  // Outside this PC the remote settings are read-only and remote cannot be chosen for new pads.
  await page.route(`${base}/api/auth`, async route => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), local: false } });
  });
  await page.reload();
  await page.getByRole('button', { name: '웹앱 메뉴' }).click();
  await expect(page.getByRole('menuitem', { name: '도메인으로 열기' })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: '로컬로 열기' })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '주문 API 메뉴' }).click();
  await page.getByRole('menuitem', { name: '설정' }).click();
  await page.getByRole('tab', { name: '서비스', exact: true }).click();
  await expect(page.getByLabel('시작 명령', { exact: true })).toHaveAttribute('readonly', '');
  await page.getByText('닫기', { exact: true }).click();
  await page.getByRole('button', { name: '패드 3 서비스 등록' }).click();
  await page.getByRole('tab', { name: '서비스', exact: true }).click();
  await expect(page.getByRole('radio', { name: '원격 서버' })).toBeDisabled();
  await page.getByRole('button', { name: '취소' }).click();
  await page.unroute(`${base}/api/auth`);

  // Phone layout keeps the form and pads inside the screen.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByRole('button', { name: 'NAS 실행' })).toBeVisible();
  await page.screenshot({ path: path.join(shots, 'remote-pads-mobile.png') });
  await page.getByRole('button', { name: '패드 3 서비스 등록' }).click();
  await page.getByRole('tab', { name: '서비스', exact: true }).click();
  await page.getByRole('radio', { name: '원격 서버' }).click();
  const overflow = await page.evaluate(() => [...document.querySelectorAll('.remote-fields *')].some(el => el.getBoundingClientRect().right > window.innerWidth + 1));
  if (overflow) throw new Error('remote form overflows on mobile');
  await page.screenshot({ path: path.join(shots, 'remote-form-mobile.png'), fullPage: true });
  if (errors.length) throw new Error(errors.join('\n'));
  console.log(`remote UI test passed; screenshots in ${shots}`);
} finally {
  await browser.close();
  // The venv launcher runs the engine as a child, so end the whole tree.
  spawnSync('taskkill.exe', ['/F', '/T', '/PID', String(engine.pid)], { stdio: 'ignore' });
}
