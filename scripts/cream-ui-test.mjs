import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ locale: 'ko-KR', viewport: { width: 1440, height: 1000 } });
const reference = await browser.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const base = { kind: 'local', padset_id: 'default', command: 'echo fixture', cwd: 'C:/example', health_url: '', color: '#75d9a5', active: true, status: 'running', uptime: 120, memory: 128, cpu: 45, autostart: false };
const services = ['API 서버','웹 프런트엔드','작업 워커','문서 서버','개발 프록시','테스트 서버'].map((name, slot) => ({ ...base, id: String(slot), name, slot, port: [8000,5173,8001,3000,8080,9000][slot], color: ['#75d9a5','#c8a0ee','#75d9a5','#e5a2aa','#f2ad62','#75d9a5'][slot], active: ![2,5].includes(slot), status: [2,5].includes(slot) ? 'stopped' : 'running' }));
const providers = ['Claude Code','Codex','Antigravity'].map((name, index) => ({ id: String(index), name, status: 'ok', windows: [{ key: 'session', label: '5h', used_percent: [42,23,76][index], resets_at: new Date(Date.now()+7200000).toISOString() }, { key:'weekly',label:'w',used_percent:[68,51,34][index],resets_at:new Date(Date.now()+345600000).toISOString() }] }));
let actions = 0;
await page.route('http://stackpad.test/**', async route => {
  const url = new URL(route.request().url());
  if (url.pathname.startsWith('/api/')) {
    let body;
    if (url.pathname === '/api/auth') body = { configured: true, authenticated: true, local: true };
    else if (url.pathname === '/api/usage') body = { enabled: ['0','1','2'], providers };
    else if (url.pathname === '/api/services') body = { services, groups: [], padsets: [{ id:'default',name:'기본' }], links: {} };
    else if (url.pathname === '/api/settings') body = { onboarding_done:true, recommend_roots:['C:/example'],autostart:false,data_dir:'C:/example',notifications:{ crash:true,unhealthy:true,schedule:true } };
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
  await expect(page.locator('.usage-track')).toHaveCount(6);
  await expect(page.locator('.pads>.pad-wrap,.pads>.pad.empty')).toHaveCount(16);
  await expect(page.locator('.engine-status,.connection,.pad-index,.bank-count')).toHaveCount(0);
  expect(await page.getByRole('tab',{name:'기본',exact:false}).evaluate(el=>getComputedStyle(el,'::before').width)).toBe('8px');
  expect(await page.locator('.pad.running').first().evaluate(el=>getComputedStyle(el,'::after').display)).toBe('none');
  await page.getByRole('button',{name:'작업 워커 실행',exact:true}).click();
  await expect(page.getByRole('button',{name:'작업 워커 종료',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'작업 워커 종료',exact:true}).click();
  await expect(page.getByRole('button',{name:'작업 워커 실행',exact:true})).toBeVisible();
  expect(actions).toBe(2);
  const baseline=await fs.readFile('src/styles.css','utf8');
  const sizes=[];
  for(const [width,height] of [[1440,1000],[1280,930],[760,1024],[650,700],[390,844],[320,740],[900,500]]) {
    await page.setViewportSize({width,height});
    const layout=await page.evaluate(()=>{const main=document.querySelector('.app-shell>main');const grid=document.querySelector('.pads');return{overflow:document.documentElement.scrollWidth>innerWidth||main.scrollHeight>main.clientHeight+1,columns:getComputedStyle(grid).gridTemplateColumns.split(' ').length,rows:getComputedStyle(grid).gridTemplateRows.split(' ').length,pads:[...document.querySelectorAll('.pad')].every(el=>{const a=el.getBoundingClientRect(),b=grid.getBoundingClientRect(),state=el.querySelector('.pad-state')?.getBoundingClientRect();return a.bottom<=b.bottom+1&&(!state||state.bottom<=a.bottom+1);})};});
    expect(layout,`${width}x${height}`).toEqual({overflow:false,columns:4,rows:4,pads:true});
    const usage=await page.locator('.usage-bar').evaluate(el=>({html:el.outerHTML,width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height}));
    await reference.setViewportSize({width,height});
    await reference.setContent('<style>'+baseline+'</style><div style="width:'+usage.width+'px">'+usage.html+'</div>');
    expect(await reference.locator('.usage-bar').evaluate(el=>el.getBoundingClientRect().height)).toBe(usage.height);
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
      await page.keyboard.press('Escape');
      await page.getByRole('button',{name:'패드 7 서비스 등록',exact:true}).click();
      await expect(page.getByRole('dialog')).toHaveCSS('background-color','rgb(239, 238, 229)');
      await page.keyboard.press('Escape');
    }
  }
  expect(errors).toEqual([]);
  console.log('CREAM UI PASS',JSON.stringify({sizes,actions,errors}));
} finally { await browser.close(); }
