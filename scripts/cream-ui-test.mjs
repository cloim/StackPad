import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ locale: 'ko-KR', viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const base = { kind: 'local', padset_id: 'default', command: 'echo fixture', cwd: 'C:/example', health_url: '', color: '#75d9a5', active: true, status: 'running', uptime: 120, memory: 128, cpu: 45, autostart: false };
const services = ['API 서버','웹 프런트엔드','작업 워커','문서 서버','개발 프록시','테스트 서버'].map((name, slot) => ({ ...base, id: String(slot), name, slot, port: [8000,5173,8001,3000,8080,9000][slot], color: ['#75d9a5','#c8a0ee','#75d9a5','#e5a2aa','#f2ad62','#75d9a5'][slot], active: ![2,5].includes(slot), status: [2,5].includes(slot) ? 'stopped' : 'running' }));
const providers = ['Claude Code','Codex','Antigravity'].map((name, index) => ({ id: String(index), name, status: 'ok', windows: [{ key: 'five_hour', label: '5h', used_percent: [42,23,76][index], resets_at: new Date(Date.now()+7200000).toISOString() }, { key:'weekly',label:'w',used_percent:[68,51,34][index],resets_at:new Date(Date.now()+345600000).toISOString() }] }));
let actions = 0;
await page.route('http://stackpad.test/**', async route => {
  const url = new URL(route.request().url());
  if (url.pathname.startsWith('/api/')) {
    let body;
    if (url.pathname === '/api/auth') body = { configured: true, authenticated: true, local: true };
    else if (url.pathname === '/api/usage') body = { enabled: ['0','1','2'], providers };
    else if (url.pathname === '/api/services') body = { services, groups: [], padsets: [{ id:'default',name:'기본' }], scenes:[{id:'flow',name:'개발 환경',color:'#97f7da',pad_ids:['0','1']}], schedules:[], links: {} };
    else if (url.pathname === '/api/settings') body = { onboarding_done:true, recommend_roots:['C:/example'],recommend_hidden:[{key:'fixture',name:'개발 서버',command:'npm run dev',cwd:'C:/example'}],autostart:false,data_dir:'C:/example',notifications:{ crash:true,unhealthy:true,schedule:true } };
    else if (url.pathname === '/api/recommendations') body = {roots:['C:/example'],candidates:[{key:'fixture',name:'개발 서버',cwd:'C:/example',command:'npm run dev',ports:[5173],pid:12345}],hidden:[]};
    else if (url.pathname === '/api/events') { await route.fulfill({status:503,body:'fixture'}); return; }
    else if (url.pathname.endsWith('/history')) body = { interval:10,cpu:[],memory:[] };
    else if (url.pathname.endsWith('/logs')) body = { text:'서비스 실행 로그' };
    else if (/\/(start|stop)$/.test(url.pathname)) { const service=services.find(s=>s.id===url.pathname.split('/')[3]); service.active=url.pathname.endsWith('/start');service.status=service.active?'running':'stopped';actions++;body={ok:true}; }
    else throw new Error('Unexpected API: '+url.pathname);
    await route.fulfill({json:body});
  } else {
    const file=path.resolve('dist',url.pathname==='/'?'index.html':url.pathname.slice(1));
    if(!file.startsWith(path.resolve('dist')+path.sep)) throw new Error('Invalid asset');
    await route.fulfill({body:await fs.readFile(file),contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'});
  }
});
try {
  await page.goto('http://stackpad.test/');
  await expect(page.getByRole('heading',{name:'StackPad',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'StackPad',exact:true})).toHaveCSS('font-weight','700');
  await expect(page.locator('[data-window]')).toHaveCount(6);
  await expect(page.locator('[data-pad-status=running] [data-pad-state] i').first()).toHaveCSS('background-color','rgb(53, 217, 130)');
  expect(await page.locator('[data-pad-status=running] [data-pad-state] i').first().evaluate(el=>getComputedStyle(el).boxShadow)).toContain('9px');
  await expect(page.locator('[data-pad-status=stopped] [data-pad-state] i').first()).toHaveCSS('background-color','rgb(168, 174, 158)');
  await expect(page.locator('[data-window="five_hour"] [data-usage-segment]')).toHaveCount(15);
  await expect(page.locator('[data-window="weekly"] [data-usage-segment]')).toHaveCount(21);
  await expect(page.locator('[data-window]').first()).toHaveAttribute('aria-valuenow', '42');
  expect(await page.locator('[data-window]').first().evaluate(el=>el.querySelector('i').getBoundingClientRect().width/el.getBoundingClientRect().width)).toBeCloseTo(.42,2);
  const shadows=await page.locator('[data-pad-wrap]').evaluateAll(nodes=>nodes.map(el=>({running:!!el.querySelector('[data-pad-status=running]'),shadow:getComputedStyle(el).boxShadow})));
  expect(shadows.filter(item=>item.running).every(item=>item.shadow.includes('12px'))).toBe(true);
  expect(shadows.filter(item=>!item.running).every(item=>!item.shadow.includes('12px'))).toBe(true);
  await expect(page.locator('[data-pads]>[data-pad-wrap],[data-pads]>[data-empty-slot]')).toHaveCount(16);
  await expect(page.locator('[data-engine-offline],.connection,.pad-index,.bank-count')).toHaveCount(0);
  expect(await page.getByRole('tab',{name:'기본',exact:false}).evaluate(el=>getComputedStyle(el,'::before').width)).toBe('8px');
  expect(await page.locator('[data-pad-status=running]').first().evaluate(el=>getComputedStyle(el,'::after').content)).toBe('none');
  await page.getByRole('button',{name:'작업 워커 실행',exact:true}).click();
  await expect(page.getByRole('button',{name:'작업 워커 종료',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'작업 워커 종료',exact:true}).click();
  await expect(page.getByRole('button',{name:'작업 워커 실행',exact:true})).toBeVisible();
  expect(actions).toBe(2);
  // Usage strip heights measured before the Tailwind migration; the strip must keep them.
  const usageHeights={1440:51,1280:51,760:73,650:63,390:63,320:63,900:51};
  const sizes=[];
  for(const [width,height] of [[1440,1000],[1280,930],[760,1024],[650,700],[390,844],[320,740],[900,500]]) {
    await page.setViewportSize({width,height});
    await expect(page.locator('[data-toolbar-brand]')).toHaveCSS('font-weight',width<=650?'900':'700');
    const layout=await page.evaluate(()=>{const main=document.querySelector('[data-app-shell]>main');const grid=document.querySelector('[data-pads]');return{overflow:document.documentElement.scrollWidth>innerWidth||main.scrollHeight>main.clientHeight+1,columns:getComputedStyle(grid).gridTemplateColumns.split(' ').length,rows:getComputedStyle(grid).gridTemplateRows.split(' ').length,pads:[...document.querySelectorAll('.pad')].every(el=>{const a=el.getBoundingClientRect(),b=grid.getBoundingClientRect(),state=el.querySelector('.pad-state')?.getBoundingClientRect();return a.bottom<=b.bottom+1&&(!state||state.bottom<=a.bottom+1);})};});
    expect(layout,`${width}x${height}`).toEqual({overflow:false,columns:4,rows:4,pads:true});
    const usage=await page.locator('[data-usage-bar]').evaluate(el=>({html:el.outerHTML,width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height}));
    const inset=await page.locator('[data-usage-bar]').evaluate(el=>el.querySelector('strong').getBoundingClientRect().left-el.getBoundingClientRect().left);
    expect(inset).toBe(width<=650?10:12);
    expect(usage.height,`${width}x${height}`).toBe(usageHeights[width]);
    sizes.push({width,height,usageHeight:usage.height});
    if(width===1440||width===390)await page.screenshot({path:`.jobs/cream-production-${width}.png`});
    if(width===1440||width===390) {
      await page.getByRole('button',{name:'API 서버 메뉴',exact:true}).click();
      await page.getByRole('menuitem',{name:'상세',exact:true}).click();
      await expect(page.getByRole('dialog')).toHaveCSS('background-color','rgb(239, 238, 229)');
      await expect(page.getByRole('dialog').locator('.log-container')).toContainText('서비스 실행 로그');
      await page.keyboard.press('Escape');
      await page.getByRole('button',{name:'환경 설정',exact:true}).click();
      await expect(page.getByRole('dialog')).toHaveCSS('background-color','rgb(239, 238, 229)');
      await page.screenshot({path:`.jobs/cream-settings-${width}.png`});
      await page.getByRole('tab',{name:'흐름 및 예약',exact:true}).click();
      await expect(page.getByRole('heading',{name:'흐름 관리',exact:true})).toBeVisible();
      await expect(page.getByText('API 서버, 웹 프런트엔드').locator('xpath=ancestor::div[contains(@class,"rounded-lg")][1]')).toHaveCSS('border-color','rgb(212, 217, 204)');
      await page.screenshot({path:`.jobs/cream-flows-${width}.png`});
      await page.getByRole('tab',{name:'등록 추천',exact:true}).click();
      await expect(page.getByRole('heading',{name:/숨긴 추천/})).toHaveCSS('color','rgb(70, 82, 62)');
      await expect(page.locator('.component-row').first()).toHaveCSS('border-color','rgb(212, 217, 204)');
      await page.getByRole('tab',{name:'패드셋',exact:true}).click();
      await expect(page.locator('button[aria-label$="패드셋 순서 이동"]').first()).toHaveCSS('border-width','0px');
      await expect(page.locator('button[aria-label$="패드셋 순서 이동"]').first()).toHaveCSS('box-shadow','none');
      await page.keyboard.press('Escape');
      await page.getByRole('button',{name:'패드 7 서비스 등록',exact:true}).click();
      await expect(page.getByRole('dialog')).toHaveCSS('background-color','rgb(239, 238, 229)');
      await expect(page.locator('.color-field legend')).toHaveCSS('color','rgb(78, 89, 71)');
      await page.keyboard.press('Escape');
      await page.getByRole('button',{name:'등록 추천',exact:true}).click();
      await expect(page.getByText(/^스캔 폴더:/)).toHaveCSS('color','rgb(88, 102, 79)');
      await expect(page.getByRole('dialog').locator('code').first()).toHaveCSS('color','rgb(78, 99, 75)');
      await page.screenshot({path:`.jobs/cream-recommendations-${width}.png`});
      await page.keyboard.press('Escape');
    }
  }
  expect(errors).toEqual([]);
  console.log('CREAM UI PASS',JSON.stringify({sizes,actions,errors}));
} finally { await browser.close(); }
