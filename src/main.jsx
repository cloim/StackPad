import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import Ansi from 'ansi-to-react';
import { createRoot } from 'react-dom/client';
import { Code, Folder, Gauge, Globe, Languages, History, Monitor, Info, LoaderCircle, Plus, Power, RefreshCw, ScanSearch, Settings as Gear, Settings2, SlidersHorizontal, Terminal, Trash2 } from 'lucide-react';
import { Modal } from './components/Modal/Modal.jsx';
import { PadForm } from './components/PadForm.jsx';
import { SelectControl } from './components/SelectControl.jsx';
import { Tabs } from './components/Tabs.jsx';
import { PadsetSettings } from './components/PadsetSettings.jsx';
import { UsageBar } from './components/UsageBar.jsx';
import { AccountSettings } from './components/AccountSettings.jsx';
import { SignIn } from './components/SignIn.jsx';
import { connectWidget, disconnectWidget, isNative, loadServer, nativeHeaders, serverOrigin } from './native.js';
import { PairPhone } from './components/PairPhone.jsx';
import './components/Modal/modal.css';
import './styles.css';
import { LOCALES, locale, setLocale, t } from './i18n.js';
import { connectEvents } from './events.js';

if (import.meta.env.PROD && window.isSecureContext && 'serviceWorker' in navigator && !window.__TAURI_INTERNALS__ && !isNative) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(error => console.warn(t('PWA 등록을 다시 확인해 주세요.'), error));
  });
}

const labels = { stopped: t('중지됨'), starting: t('시작 중'), running: t('실행 중'), partial: t('일부 실행'), unhealthy: t('응답 이상'), error: t('실행 오류'), external: t('외부 실행'), conflict: t('포트 충돌'), unreachable: t('연결 실패'), checking: t('확인 중') };
const actionLabels = { start: t('시작'), stop: t('종료') };

function lastCommand(last) {
  if (!last) return t('없음');
  const result = last.code === 0 ? t('성공') : last.code === null ? t('응답 없음') : t('실패 (코드 {0})', last.code);
  return t('{0} {1} | {2} 전', actionLabels[last.action], result, timeLabel(Math.max(0, Math.round(Date.now() / 1000 - last.at))));
}
const colors = ['#ef4444', '#da9281', '#f97316', '#be9537', '#e6d3a8', '#facc15', '#daf797', '#22c55e', '#97f7da', '#25bfd0', '#3b82f6', '#a8bbe6', '#a855f7', '#ef3994', '#eea0c7', '#f5f5f4'];
const colorNames = [t('레드'), t('살몬'), t('오렌지'), t('머스터드'), t('베이지'), t('옐로'), t('라임'), t('그린'), t('민트'), t('청록'), t('블루'), t('하늘'), t('퍼플'), t('마젠타'), t('핑크'), t('화이트')];

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`${serverOrigin()}/api${path}`, { credentials: 'same-origin', ...options, headers: { 'Content-Type': 'application/json', 'X-StackPad-Lang': locale, ...await nativeHeaders(), ...options.headers } });
  } catch {
    throw new Error(navigator.onLine ? t('관리 엔진과 연결을 확인해 주세요.') : t('네트워크 연결 후 다시 시도해 주세요.'));
  }
  let data;
  try { data = await response.json(); } catch { throw new Error(t('엔진 연결을 확인해 주세요.')); }
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(e => e.msg.replace('Value error, ', '')).join('\n') : data.detail;
    const error = new Error(detail || t('요청을 처리하지 못했습니다. 다시 시도해 주세요.'));
    error.status = response.status;
    throw error;
  }
  return data;
}

function isNewer(candidate, current) {
  const [a, b] = [candidate, current].map(version => version.split('.').map(part => Number(part) || 0));
  for (let i = 0; i < Math.max(a.length, b.length); i++) if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) > (b[i] || 0);
  return false;
}

function timeLabel(seconds) {
  if (seconds < 60) return t('{0}초', seconds);
  if (seconds < 3600) return t('{0}분', Math.floor(seconds / 60));
  return t('{0}시간 {1}분', Math.floor(seconds / 3600), Math.floor(seconds % 3600 / 60));
}

function Logo({ small = false }) {
  return <div className={`logo ${small ? 'small' : ''}`} aria-hidden="true">{[0, 1, 2, 3].map(i => <span key={i} />)}</div>;
}

function Deck({ services, groups, padsets, padsetId, onPadsetChange, links, loading, settings, refresh, onError, connected, local }) {
  const [selected, setSelected] = useState(null);
  const [padEditor, setPadEditor] = useState(null);
  const [busy, setBusy] = useState(new Set());
  const [logs, setLogs] = useState('');
  const [logsLoading, setLogsLoading] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [takeover, setTakeover] = useState(null);
  const [componentId, setComponentId] = useState(null);
  const [dragged, setDragged] = useState(null);
  const [dropSlot, setDropSlot] = useState(null);
  const [padMenu, setPadMenu] = useState(null);
  const dragging = useRef(null);
  const menuRef = useRef(null);
  const suppressClick = useRef(0);
  const logPane = useRef(null);
  const follow = useRef(true);
  const groupedIds = new Set(groups.flatMap(g => g.member_ids));
  const pads = [...services.filter(s => !groupedIds.has(s.id)), ...groups.map(group => {
    const members = group.member_ids.map(id => services.find(s => s.id === id)).filter(Boolean);
    const active = members.filter(s => s.active);
    const idle = active.length === 0 && (members.some(s => s.status === 'conflict') ? 'conflict' : members.some(s => s.status === 'external') ? 'external' : null);
    const failed = members.some(s => s.status === 'error') ? 'error' : 'unreachable';
    const status = idle ? idle : members.some(s => ['unhealthy', 'error', 'unreachable'].includes(s.status)) ? (active.length ? 'unhealthy' : failed) : active.length === 0 ? (members.some(s => s.status === 'checking') ? 'checking' : 'stopped') : active.length < members.length ? 'partial' : members.some(s => s.status === 'starting') ? 'starting' : 'running';
    return { ...group, isGroup: true, members, status, active: active.length > 0, busy: members.some(s => s.busy), pid: active.find(s => s.pid)?.pid };
  })];
  const remoteOnly = pad => (pad.isGroup ? pad.members : [pad]).every(s => s.kind === 'remote');
  const current = pads.find(s => s.id === selected);
  useEffect(() => { setSelected(null); setPadMenu(null); setPadEditor(null); }, [padsetId]);
  const menuPad = padMenu && pads.find(s => s.id === padMenu.id);
  const editingPad = padEditor?.id ? pads.find(s => s.id === padEditor.id) : null;
  const logService = current?.isGroup ? current.members.find(s => s.id === componentId) || current.members[0] : current;
  const logId = logService?.id;
  const remoteLog = logService?.kind === 'remote';
  useEffect(() => {
    if (!logId) { setLogs(''); return; }
    let disposed = false;
    let timer = null;
    follow.current = true; setLogs(''); setLogsLoading(true);
    let logFile = null;
    let logOffset = null;
    let currentText = '';

    async function load() {
      if (disposed || document.visibilityState === 'hidden') return;
      try {
        const query = logFile && logOffset !== null ? `?file=${encodeURIComponent(logFile)}&offset=${logOffset}` : '';
        const data = await api(`/services/${logId}/logs${query}`);
        if (disposed) return;
        if (data.unchanged) {
          setLogsLoading(false);
          return;
        }
        if (data.reset) {
          currentText = data.text || '';
        } else {
          currentText += (data.text || '');
        }
        logFile = data.file;
        logOffset = data.offset;
        // Limit buffer size to 400KB and trim to line boundary
        if (currentText.length > 400_000) {
          currentText = currentText.slice(-400_000);
          const firstNewline = currentText.indexOf('\n');
          if (firstNewline !== -1) currentText = currentText.slice(firstNewline + 1);
        }
        setLogs(currentText);
        setLogsLoading(false);
      } catch (error) {
        if (!disposed) { setLogs(error.message); setLogsLoading(false); }
      }
    }

    function schedule() {
      clearInterval(timer);
      if (document.visibilityState !== 'hidden') {
        timer = setInterval(load, remoteLog ? 5000 : 2000);
      }
    }

    function onVisibilityChange() {
      if (document.visibilityState === 'visible') {
        load();
        schedule();
      } else {
        clearInterval(timer);
      }
    }

    load();
    schedule();
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      disposed = true;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [logId, remoteLog]);
  useEffect(() => {
    if (!padMenu) return;
    const close = () => setPadMenu(null);
    window.addEventListener('resize', close);
    return () => window.removeEventListener('resize', close);
  }, [padMenu]);
  useEffect(() => { if (logPane.current && follow.current) logPane.current.scrollTop = logPane.current.scrollHeight; }, [logs]);
  async function toggle(service, confirmed = false) {
    if (Date.now() < suppressClick.current) return;
    if (busy.has(service.id) || !connected) return;
    if (!service.active && service.status === 'external' && !confirmed) { setTakeover(service); return; }
    setBusy(value => new Set([...value, service.id]));
    try { await api(`/${service.isGroup ? 'groups' : 'services'}/${service.id}/${service.active ? 'stop' : 'start'}${confirmed ? '?takeover=true' : ''}`, { method: 'POST' }); await refresh(); }
    catch (e) { onError(e.message); } finally { setBusy(value => { const next = new Set(value); next.delete(service.id); return next; }); }
  }
  async function restart(service) {
    setBusy(value => new Set([...value, service.id]));
    try { await api(`/services/${service.id}/restart`, { method: 'POST' }); }
    catch (error) { onError(error.message); }
    finally { await refresh(); setBusy(value => { const next = new Set(value); next.delete(service.id); return next; }); }
  }
  async function remove() {
    const service = deleting;
    setDeleting(null);
    try { await api(`/pads/${service.id}`, { method: 'DELETE' }); if (selected === service.id) setSelected(null); refresh(); }
    catch (e) { onError(e.message); }
  }
  async function move(padId, slot) {
    if (!connected || !Number.isInteger(slot) || slot < 0 || slot > 15) return;
    if (pads.some(pad => pad.padset_id === padsetId && pad.slot === slot)) { onError(t('빈 패드로 이동해 주세요.')); return; }
    setBusy(value => new Set([...value, padId]));
    try { await api(`/pads/${padId}/position`, { method: 'PUT', body: JSON.stringify({ slot }) }); await refresh(); }
    catch (error) { onError(error.message); }
    finally { setBusy(value => { const next = new Set(value); next.delete(padId); return next; }); }
  }
  function openPadMenu(event, pad) {
    if (padMenu?.id === pad.id) { setPadMenu(null); return; }
    // Fixed positioning keeps the menu out of the pad grid's clipping; it opens upward near the bottom edge.
    const rect = event.currentTarget.getBoundingClientRect();
    const right = Math.max(8, window.innerWidth - rect.right);
    const style = rect.bottom + 210 > window.innerHeight ? { right, bottom: window.innerHeight - rect.top + 4 } : { right, top: rect.bottom + 4 };
    setPadMenu({ id: pad.id, style, anchor: rect.left });
  }
  // The menu hangs left from its button; on edge pads it starts at the button instead so it stays inside the window.
  useLayoutEffect(() => {
    const menu = menuRef.current;
    if (!menu || !padMenu) return;
    const box = menu.getBoundingClientRect();
    if (box.left < 8) Object.assign(menu.style, { right: 'auto', left: `${Math.max(8, Math.min(padMenu.anchor, window.innerWidth - box.width - 8))}px` });
    if (box.top < 8) Object.assign(menu.style, { bottom: 'auto', top: '8px' });
  }, [padMenu]);
  function menuKeys(event) {
    if (event.key === 'Escape') { setPadMenu(null); return; }
    if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return;
    event.preventDefault();
    const items = [...event.currentTarget.querySelectorAll('button:not(:disabled)')];
    const index = items.indexOf(document.activeElement);
    items[(index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus();
  }
  async function openLink(pad, target) {
    setPadMenu(null);
    // The desktop window cannot open browser windows, so the engine opens this PC's default browser instead.
    if (window.__TAURI_INTERNALS__) {
      try { await api(`/pads/${pad.id}/open`, { method: 'POST', body: JSON.stringify({ target }) }); }
      catch (error) { onError(error.message); }
      return;
    }
    window.open(links[pad.id][target], '_blank', 'noopener,noreferrer');
  }
  async function openInCode(pad) {
    setPadMenu(null);
    try { await api(`/pads/${pad.id}/code`, { method: 'POST' }); }
    catch (error) { onError(error.message); }
  }
  function touchDrag(event, pad) {
    if (event.button !== 0 || !connected || busy.has(pad.id)) return;
    event.preventDefault(); event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragging.current = { id: pad.id, slot: null, pointerId: event.pointerId };
    setDragged(pad.id);
  }
  function touchMove(event) {
    if (dragging.current?.pointerId !== event.pointerId) return;
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-empty-slot]');
    const slot = target ? Number(target.dataset.emptySlot) : null;
    dragging.current.slot = slot; setDropSlot(slot);
  }
  function endTouch(event, cancelled = false) {
    if (dragging.current?.pointerId !== event.pointerId) return;
    const { id, slot } = dragging.current;
    dragging.current = null; setDragged(null); setDropSlot(null); suppressClick.current = Date.now() + 400;
    if (!cancelled && slot !== null) move(id, slot);
  }
  return <>
    <section className="pad-deck" aria-label={t('서비스 컨트롤 패드')}>
      <UsageBar api={api} />
      <Tabs label={t('패드셋')} tabs={padsets.map(set => ({ ...set, badge: pads.filter(p => p.padset_id === set.id).length }))} value={padsetId} onChange={onPadsetChange} prefix="padsets" />
      <div className="pads" role="tabpanel" id="padsets-panel" aria-labelledby={`padsets-tab-${padsetId}`}>{Array.from({ length: 16 }, (_, slot) => {
        const service = pads.find(s => s.padset_id === padsetId && s.slot === slot);
        if (loading) return <div key={slot} className="pad skeleton" />;
        if (!service) return <button key={slot} data-empty-slot={slot} className={`pad empty ${dropSlot === slot ? 'drop-target' : ''}`} aria-label={t('패드 {0} 서비스 등록', slot + 1)} onClick={() => { if (Date.now() >= suppressClick.current) setPadEditor({ slot }); }} onDragOver={event => { if (dragging.current && connected) { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; setDropSlot(slot); } }} onDragLeave={() => setDropSlot(null)} onDrop={event => { event.preventDefault(); const source = dragging.current; dragging.current = null; setDragged(null); setDropSlot(null); suppressClick.current = Date.now() + 400; if (source) move(source.id, slot); }}><Plus size={20} /></button>;
        const pending = busy.has(service.id) || service.busy || service.members?.some(s => busy.has(s.id));
        const tags = (service.isGroup ? service.members : [service]).filter(s => s.kind === 'remote' || s.kind === 'docker' || s.port);
        return <div key={slot} className={`pad-wrap ${selected === service.id ? 'chosen' : ''} ${dragged === service.id ? 'dragging' : ''}`} style={{ '--pad-color': service.color }}>
          <button className={`pad assigned ${service.status}`} disabled={pending || !connected} onClick={() => toggle(service)} aria-label={`${service.name} ${service.active ? t('종료') : t('실행')}`} aria-pressed={!!service.active}>
            <span className="pad-top">{pending ? <LoaderCircle className="spin" size={14} /> : <Power size={14} />}</span>
            <span className="pad-port">{tags.length ? tags.map(s => <span key={s.id} title={s.kind === 'remote' ? s.remote.host : undefined}>{s.name}{s.kind === 'remote' ? ` @${s.remote.host}` : s.kind === 'docker' ? ` ${s.container_ports?.length ? s.container_ports.map(port => `:${port}`).join(', ') : t(':포트 없음')}` : s.port ? ` :${s.port}` : t(' :포트 없음')}</span>) : t('명령 실행')}</span>
            <span className="pad-state"><i />{pending ? t('처리 중') : labels[service.status]}</span>
          </button><button className="pad-move" disabled={!connected || pending} title={t('드래그하여 빈 패드로 이동')} aria-label={t('{0} 자리 이동', service.name)} onPointerDown={event => touchDrag(event, service)} onPointerMove={touchMove} onPointerUp={event => endTouch(event)} onPointerCancel={event => endTouch(event, true)}>{service.name}</button><button className="pad-detail" onClick={event => openPadMenu(event, service)} aria-label={t('{0} 메뉴', service.name)} aria-haspopup="menu" aria-expanded={padMenu?.id === service.id}><SlidersHorizontal size={13} /></button>
        </div>;
      })}</div>
    </section>
    {menuPad && <div className="pad-menu-layer" onPointerDown={() => setPadMenu(null)} onContextMenu={event => { event.preventDefault(); setPadMenu(null); }}>
      <div ref={menuRef} className="pad-menu" role="menu" aria-label={t('{0} 메뉴', menuPad.name)} style={padMenu.style} onPointerDown={event => event.stopPropagation()} onKeyDown={menuKeys}>
        <button role="menuitem" autoFocus onClick={() => { setPadMenu(null); setSelected(menuPad.id); setComponentId(null); }}><Info size={14} />{t('상세')}</button>
        <button role="menuitem" disabled={busy.has(menuPad.id)} onClick={() => { setPadMenu(null); setPadEditor({ id: menuPad.id, slot: menuPad.slot }); }}><Settings2 size={14} />{t('설정')}</button>
        <button role="menuitem" className="menu-delete" disabled={!connected || busy.has(menuPad.id) || menuPad.busy || (menuPad.isGroup ? menuPad.members : [menuPad]).some(s => s.kind !== 'remote' && (s.active || s.pid || busy.has(s.id) || s.busy))} onClick={() => { setPadMenu(null); setDeleting(menuPad); }}><Trash2 size={14} />{t('삭제')}</button>
        {links[menuPad.id]?.domain && <button role="menuitem" onClick={() => openLink(menuPad, 'domain')}><Globe size={14} />{t('도메인으로 열기')}</button>}
        {local && links[menuPad.id]?.local && <button role="menuitem" onClick={() => openLink(menuPad, 'local')}><Monitor size={14} />{t('로컬로 열기')}</button>}
        {settings?.tools?.vscode !== false && (menuPad.isGroup ? menuPad.members : [menuPad]).some(s => !s.kind || s.kind === 'local') && <button role="menuitem" disabled={!connected} onClick={() => openInCode(menuPad)}><Code size={14} />{t('VSCode로 열기')}</button>}
      </div>
    </div>}
    <Modal isOpen={!!current} onClose={() => setSelected(null)} title={current?.name || t('서비스 상세')} storageKey="service-detail" size="lg">{current && <>
      <Tabs label={t('등록된 서비스')} tabs={(current.isGroup ? current.members : [current]).map(service => ({ id: service.id, name: service.name }))} value={logId} onChange={setComponentId} prefix="service-detail" />
      {logService && <div role="tabpanel" id="service-detail-panel" aria-labelledby={`service-detail-tab-${logId}`}>
        <dl>
          <div><dt>{t('타입')}</dt><dd>{logService.kind === 'docker' ? t('도커') : logService.kind === 'remote' ? t('원격 서버') : t('로컬 프로세스')}</dd></div>
          <div><dt>{t('러닝타임')}</dt><dd>{logService.active ? timeLabel(logService.uptime || 0) : labels[logService.status]}</dd></div>
          <div><dt>{t('메모리')}</dt><dd>{logService.memory == null ? t('확인 정보 없음') : `${logService.memory} MB`}</dd></div>
          <div><dt>PID</dt><dd>{logService.pid || logService.external_pid || t('없음')}</dd></div>
          <div><dt>{t('포트')}</dt><dd>{logService.kind === 'docker' ? logService.container_ports?.join(', ') || t('없음') : logService.port || t('없음')}</dd></div>
          {logService.kind === 'docker' && <div><dt>{t('컨테이너 ID')}</dt><dd><code>{logService.container?.slice(0, 12)}</code></dd></div>}
          {logService.kind === 'remote' && <><div><dt>{t('호스트')}</dt><dd>{logService.remote.host}</dd></div><div><dt>{t('마지막 확인')}</dt><dd>{logService.checked_ago == null ? t('확인 중') : t('{0} 전', timeLabel(logService.checked_ago))}</dd></div><div><dt>{t('마지막 명령')}</dt><dd>{lastCommand(logService.last)}</dd></div></>}
        </dl>
        {(logService.error || logService.message) && <p className="detail-message">{logService.error || logService.message}</p>}
        {logService.last?.output && <pre className="command-output" aria-label={t('마지막 명령 출력')}>{logService.last.output}</pre>}
        <div className="detail-buttons"><button className="secondary" disabled={!connected || busy.has(current.id) || busy.has(logId) || current.busy || logService.busy} onClick={() => restart(logService)} aria-label={t('{0} 재시작', logService.name)}><RefreshCw size={13} />{t('재시작')}</button></div>
    <section className="log-panel"><div className="log-head"><div className="panel-title"><Terminal size={16} /><h2>{t('실행 로그')}</h2>{logService && <span>{logService.name}</span>}</div></div>
      <pre ref={logPane} onScroll={e => { follow.current = e.currentTarget.scrollHeight - e.currentTarget.scrollTop - e.currentTarget.clientHeight < 30; }}><Ansi linkify={false}>{logsLoading ? t('로그를 불러오는 중…') : selected ? (logs || t('아직 기록된 로그가 없습니다. 서비스를 실행하면 여기에 표시됩니다.')) : t('서비스를 선택하면 실행 로그가 여기에 표시됩니다.')}</Ansi></pre>
    </section></div>}
    </>}</Modal>
    {padEditor && <PadForm pad={editingPad} slot={padEditor.slot} defaultCwd={settings?.recommend_roots?.[0] || ''} tools={settings?.tools} {...{ padsets, padsetId, services, api, colors, colorNames, local, onError }} onClose={() => setPadEditor(null)} onSaved={async id => { await refresh(); if (padEditor.id) setSelected(id); }} />}
    <Modal isOpen={!!takeover} onClose={() => setTakeover(null)} title={t('외부 실행 넘겨받기')} size="sm" draggable={false} footer={<><button className="secondary" onClick={() => setTakeover(null)}>{t('취소')}</button><button className="primary" onClick={() => { const pad = takeover; setTakeover(null); toggle(pad, true); }}>{t('종료 후 다시 실행')}</button></>}><p className="notice-text">{t('{0} 서버가 StackPad 밖에서 실행 중입니다. 외부에서 실행한 서버를 종료하고 StackPad에서 다시 실행할까요?', takeover?.name)}</p></Modal>
    <Modal isOpen={!!deleting} onClose={() => setDeleting(null)} title={t('패드 삭제')} size="sm" draggable={false} footer={<><button className="secondary" onClick={() => setDeleting(null)}>{t('취소')}</button><button className="danger" onClick={remove}>{t('삭제')}</button></>}><p>{t('{0} 패드 등록을 삭제할까요? 실행 로그 파일은 보관됩니다.', deleting?.name)}{deleting && (deleting.isGroup ? deleting.members : [deleting]).some(s => s.kind === 'docker') ? t(' 도커 컨테이너는 그대로 유지됩니다.') : ''}{deleting && (deleting.isGroup ? deleting.members : [deleting]).some(s => s.kind === 'remote') ? t(' 원격 서버에서 실행 중인 서비스는 그대로 유지됩니다.') : ''}</p></Modal>
  </>;
}

function Recommendations({ onRegister, onError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hiding, setHiding] = useState(null);
  const errorRef = useRef(onError);
  errorRef.current = onError;
  // Scan once on open and on request; the parent recreates onError on every poll.
  const scan = useCallback(async () => {
    setLoading(true);
    try { setData(await api('/recommendations')); }
    catch (e) { errorRef.current(e.message); } finally { setLoading(false); }
  }, []);
  useEffect(() => { scan(); }, [scan]);
  async function hide(candidate) {
    setHiding(candidate.key);
    try { await api('/recommendations/hidden', { method: 'POST', body: JSON.stringify({ key: candidate.key, name: candidate.name, cwd: candidate.cwd, command: candidate.command }) }); await scan(); }
    catch (e) { onError(e.message); } finally { setHiding(null); }
  }
  return <div className="recommendations">
    <div className="recommend-head"><p>{data ? t('스캔 폴더: {0}', data.roots.join(', ') || t('없음')) : t('스캔 폴더를 확인하는 중…')}</p><button className="secondary" disabled={loading} onClick={scan}><RefreshCw size={14} />{t('다시 스캔')}</button></div>
    {data && !data.roots.length ? <p className="detail-empty">{t('환경 설정의 등록 추천 탭에서 프로젝트 폴더를 지정하면 그 아래에서 실행 중인 서버를 찾아 드려요.')}</p> : loading && !data ? <p className="detail-empty">{t('실행 중인 프로세스를 스캔하는 중…')}</p> : data?.candidates.length ? <div className="component-list">{data.candidates.map(candidate => <div className="component-row" key={candidate.key}>
      <div><strong>{candidate.name}</strong><p>{candidate.ports.map(port => `:${port}`).join(' ')} | PID {candidate.pid}</p><p><code>{candidate.command}</code></p><p>{candidate.cwd}</p></div>
      <div className="component-actions"><button className="primary" onClick={() => onRegister(candidate)} aria-label={t('{0} 등록', candidate.name)}>{t('등록')}</button><button className="secondary" disabled={hiding === candidate.key} onClick={() => hide(candidate)} aria-label={t('{0} 숨기기', candidate.name)}>{t('숨기기')}</button></div>
    </div>)}</div> : <p className="detail-empty">{t('추천할 서비스가 없습니다.')}</p>}
  </div>;
}

// New installs pick their project folder once; it becomes the default working folder and the registration scan folder.
function FolderOnboarding({ onDone, onError }) {
  const [folder, setFolder] = useState('');
  const [busy, setBusy] = useState(false);
  async function pick() {
    setBusy(true);
    try { const { folder: chosen } = await api('/settings/pick-folder', { method: 'POST' }); if (chosen) setFolder(chosen); }
    catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  async function finish(roots) {
    setBusy(true);
    try { await api('/settings/onboarding', { method: 'PUT', body: JSON.stringify({ roots }) }); await onDone(); }
    catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  return <Modal isOpen onClose={() => finish([])} title={t('프로젝트 폴더 지정')} size="sm" draggable={false} footer={<><button className="secondary" disabled={busy} onClick={() => finish([])}>{t('나중에')}</button><button className="primary" disabled={busy || !folder.trim()} onClick={() => finish([folder])}>{t('저장')}</button></>}>
    <div className="service-form"><p className="notice-text">{t('서버 프로젝트를 모아 두는 폴더를 알려 주세요. 서비스를 등록할 때 기본 작업 폴더로 쓰고, 등록 추천이 이 폴더 아래에서 실행 중인 서버를 찾아 드려요.')}</p>
      <div className="settings-actions"><input aria-label={t('프로젝트 폴더')} value={folder} onChange={e => setFolder(e.target.value)} placeholder="C:\Users\me\projects" /><button type="button" className="secondary" disabled={busy} onClick={pick}><Folder size={14} />{t('폴더 선택')}</button></div>
      <p className="optional">{t('환경 설정의 등록 추천 탭에서 언제든 바꿀 수 있어요.')}</p></div>
  </Modal>;
}

function Settings({ auth, settings, padsets, services, groups, refresh, onError, onNotice, onLogout }) {
  const [category, setCategory] = useState('general');
  const [busy, setBusy] = useState(false);
  const [roots, setRoots] = useState(null);
    async function selectDataDirectory() {
      setBusy(true);
      try {
        const result = await api('/settings/data-directory', { method: 'POST' });
        if (!result.cancelled) { await refresh(); onNotice(t('설정과 로그 저장 위치를 변경했습니다.')); }
      } catch (e) { onError(e.message); } finally { setBusy(false); }
    }
  async function saveRoots() {
    setBusy(true);
    try { await api('/settings/recommend', { method: 'PUT', body: JSON.stringify({ roots: roots.split('\n').map(r => r.trim()).filter(Boolean) }) }); setRoots(null); await refresh(); onNotice(t('등록 추천 스캔 폴더를 저장했습니다.')); }
    catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  async function unhide(entry) {
    setBusy(true);
    try { await api('/recommendations/unhide', { method: 'POST', body: JSON.stringify({ key: entry.key }) }); await refresh(); }
    catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  async function resetHidden() {
    setBusy(true);
    try { await api('/recommendations/hidden', { method: 'DELETE' }); await refresh(); onNotice(t('숨긴 추천을 모두 다시 표시합니다.')); }
    catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  async function change(enabled) {
    setBusy(true);
    try { await api('/settings/autostart', { method: 'PUT', body: JSON.stringify({ enabled }) }); await refresh(); onNotice(enabled ? t('Windows 로그인 시 StackPad가 자동으로 실행됩니다.') : t('자동 실행 설정을 해제했습니다.')); }
    catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  async function changeUsage(name, enabled) {
    setBusy(true);
    const providers = (settings?.usage_providers || []).filter(item => item !== name).concat(enabled ? [name] : []);
    try { await api('/settings/usage', { method: 'PUT', body: JSON.stringify({ providers }) }); await refresh(); }
    catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  async function changeRetention(days) {
    setBusy(true);
    try {
      await api('/settings/log-retention', { method: 'PUT', body: JSON.stringify({ days: Number(days) }) });
      await refresh();
      onNotice(t('로그 보관 기간을 설정했습니다.'));
    } catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  return <>
    <Tabs label={t('환경 설정 카테고리')} tabs={[{ id: 'general', name: t('일반') }, { id: 'recommend', name: t('등록 추천') }, { id: 'padsets', name: t('패드셋') }, { id: 'account', name: t('계정') }]} value={category} onChange={setCategory} prefix="settings" />
    <div className="settings-stack compact-settings" role="tabpanel" id="settings-panel" aria-labelledby={`settings-tab-${category}`}>
    {category === 'general' && <><section className="settings-card"><div className="settings-icon"><Power size={22} /></div><div><h2>{t('Windows 로그인 시 자동 실행')}</h2></div><button className={`switch ${settings?.autostart ? 'on' : ''}`} role="switch" aria-checked={!!settings?.autostart} aria-label={t('Windows 로그인 시 자동 실행')} disabled={busy || !settings} onClick={() => change(!settings.autostart)}><span /></button></section>
    <section className="settings-card"><div className="settings-icon"><Languages size={22} /></div><div><h2>{t('언어')}</h2></div><div className="retention-control"><SelectControl aria-label={t('언어')} value={locale} onChange={e => setLocale(e.target.value)}>
      {LOCALES.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </SelectControl></div></section>
    <section className="settings-card"><div className="settings-icon"><History size={22} /></div><div><h2>{t('로그 보관 기간')}</h2><p className="optional">{t('지정된 기간이 지난 서비스 및 엔진 로그를 자동 삭제합니다.')}</p></div><div className="retention-control"><SelectControl aria-label={t('로그 보관 기간')} value={settings?.log_retention_days ?? 14} disabled={busy || !settings} onChange={e => changeRetention(e.target.value)}>
      <option value={7}>{t('7일')}</option>
      <option value={14}>{t('14일')}</option>
      <option value={30}>{t('30일')}</option>
      <option value={90}>{t('90일')}</option>
      <option value={0}>{t('무제한')}</option>
    </SelectControl></div></section>
    <section className="settings-card vertical"><div className="section-heading"><Gauge size={22} /><div><h2>{t('AI 사용량')}</h2><p>{t('이 PC에 로그인된 AI CLI의 사용 한도를 패드 위와 휴대폰 위젯에 표시합니다. 각 CLI의 비공개 API를 읽기만 하므로 응답 형식이 바뀌면 표시되지 않을 수 있어요.')}</p></div></div>
      <div className="usage-switches">{[['claude', 'Claude Code'], ['codex', 'Codex'], ['antigravity', 'Antigravity']].map(([id, name]) => <label key={id} className="usage-switch"><span>{name}</span><button type="button" className={`switch ${settings?.usage_providers?.includes(id) ? 'on' : ''}`} role="switch" aria-checked={!!settings?.usage_providers?.includes(id)} aria-label={t('{0} 사용량 표시', name)} disabled={busy || !settings} onClick={() => changeUsage(id, !settings.usage_providers.includes(id))}><span /></button></label>)}</div>
      <p className="optional">{t('Antigravity는 상태줄이 저장한 스냅샷 파일을 읽습니다:')} <code>~/.gemini/antigravity-cli/usage-snapshot.json</code></p></section>
    <section className="settings-card vertical"><div className="settings-actions storage-heading"><div className="section-heading"><Folder size={18} /><div><h2>{t('설정과 로그 저장 위치')}</h2></div></div><button className="secondary" disabled={busy || !settings?.can_select_data_dir} onClick={selectDataDirectory} title={settings?.can_select_data_dir ? t('빈 폴더를 선택하면 바로 적용됩니다.') : t('StackPad가 실행 중인 PC에서 선택해 주세요.')}>{busy ? t('처리 중…') : t('폴더 선택')}</button></div><code className="path-code">{settings?.data_dir || t('불러오는 중…')}</code></section></>}
    {category === 'recommend' && <section className="settings-card vertical"><div className="section-heading"><ScanSearch size={22} /><div><h2>{t('등록 추천 스캔 폴더')}</h2><p>{t('이 폴더 아래에서 실행 중인 Python, Node 서버를 등록 추천 대상으로 찾습니다. 한 줄에 폴더 하나씩 입력하세요.')}</p></div></div><textarea aria-label={t('등록 추천 스캔 폴더')} rows={3} value={roots ?? settings?.recommend_roots?.join('\n') ?? ''} onChange={e => setRoots(e.target.value)} /><div className="settings-actions"><button className="primary" disabled={busy || roots === null} onClick={saveRoots}>{t('저장')}</button></div>
      {!!settings?.recommend_hidden?.length && <div className="hidden-recommendations"><div className="settings-actions"><h3>{t('숨긴 추천 {0}개', settings.recommend_hidden.length)}</h3><button className="secondary" disabled={busy} onClick={resetHidden}>{t('모두 다시 표시')}</button></div><div className="component-list">{settings.recommend_hidden.map(entry => <div className="component-row" key={entry.key}>
        <div><strong>{entry.name}</strong><p><code>{entry.command}</code></p><p>{entry.cwd}</p></div>
        <div className="component-actions"><button className="secondary" disabled={busy} onClick={() => unhide(entry)} aria-label={t('{0} 다시 표시', entry.name)}>{t('다시 표시')}</button></div>
      </div>)}</div></div>}</section>}
    {category === 'padsets' && <PadsetSettings {...{ padsets, services, groups, api, refresh, onError }} />}
    {category === 'account' && <AccountSettings {...{ auth, api, onError }} onLogout={onLogout} />}</div>
  </>;
}

function App() {
  const [auth, setAuth] = useState(null);
  const [authError, setAuthError] = useState('');
  const [services, setServices] = useState([]);
  const [groups, setGroups] = useState([]);
  const [padsets, setPadsets] = useState([]);
  const [activePadset, setActivePadset] = useState(() => { try { return localStorage.getItem('stackpad-padset') || 'default'; } catch { return 'default'; } });
  const padsetId = padsets.some(s => s.id === activePadset) ? activePadset : padsets[0]?.id || 'default';
  function onPadsetChange(id) { setActivePadset(id); try { localStorage.setItem('stackpad-padset', id); } catch { /* 세션 내 선택 유지 */ } }
  const [links, setLinks] = useState({});
  const [registrationSlot, setRegistrationSlot] = useState(null);
  const [preset, setPreset] = useState(null);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const [notice, setNotice] = useState(null);
  const [panel, setPanel] = useState(window.location.pathname === '/settings' ? 'settings' : null);
  const inFlight = useRef(false);
  const checkAuth = useCallback(async () => {
    // A phone that has not scanned a PC's QR code yet has no engine to ask.
    if (isNative && !serverOrigin()) { setAuth({ configured: true, owner: true, authenticated: false, email: null, local: false }); return; }
    try { setAuth(await api('/auth')); setAuthError(''); } catch (e) { setAuthError(e.message); }
  }, []);
  useEffect(() => {
    const onVisible = () => { if (document.visibilityState === 'visible') checkAuth(); };
    checkAuth();
    window.addEventListener('focus', checkAuth);
    window.addEventListener('online', checkAuth);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('focus', checkAuth);
      window.removeEventListener('online', checkAuth);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [checkAuth]);
  useEffect(() => {
    if (auth?.authenticated) return;
    const timer = setInterval(() => { if (document.visibilityState === 'visible') checkAuth(); }, 2000);
    return () => clearInterval(timer);
  }, [auth?.authenticated, checkAuth]);
  const [fallback, setFallback] = useState(false);
  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const [data, info] = await Promise.all([api('/services'), api('/settings')]);
      setServices(data.services); setPadsets(data.padsets || []); setGroups(data.groups || []); setLinks(data.links || {}); setSettings(info); setConnected(true); setLoading(false);
    } catch (e) { setConnected(false); if (e.status === 401) { checkAuth(); } }
    finally { inFlight.current = false; }
  }, [checkAuth]);
  useEffect(() => {
    if (!auth?.authenticated) return;
    refresh();
    const disconnect = connectEvents({
      topics: ['services', 'settings', 'alert', 'progress'],
      onEvent: (topic, data) => {
        if (topic === 'services') {
          setServices(data.services || []);
          setPadsets(data.padsets || []);
          setGroups(data.groups || []);
          setLinks(data.links || {});
          setConnected(true);
          setLoading(false);
        } else if (topic === 'settings') {
          setSettings(data);
        }
      },
      onConnectedChange: val => setConnected(val),
      onFallbackChange: val => setFallback(val),
    });
    return () => disconnect();
  }, [auth?.authenticated, refresh]);
  useEffect(() => {
    if (!auth?.authenticated || !fallback) return;
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') refresh();
    }, 2000);
    return () => clearInterval(timer);
  }, [auth?.authenticated, fallback, refresh]);
  useEffect(() => {
    // The Android app is installed from GitHub Releases, so it checks there for a newer version once per launch.
    if (!auth?.authenticated || !isNative) return;
    fetch('https://api.github.com/repos/cloim/StackPad/releases/latest').then(response => response.json()).then(release => {
      const latest = String(release.tag_name || '').replace(/^v/, '');
      if (isNewer(latest, APP_VERSION)) setNotice({ title: t('새 버전이 있어요'), message: t('StackPad {0}을 내려받을 수 있어요. 설치하면 지금 앱 위에 업데이트됩니다.', latest), link: release.html_url });
    }).catch(() => {});
  }, [auth?.authenticated]);
  useEffect(() => {
    if (auth?.authenticated) connectWidget(api).catch(e => console.warn(t('위젯 연결을 다시 확인해 주세요.'), e));
  }, [auth?.authenticated]);
  const onError = message => setNotice({ title: t('확인이 필요해요'), message });
  const onNotice = message => setNotice({ title: t('설정을 반영했습니다'), message });
  async function logout() { try { await disconnectWidget(api); await api('/logout', { method: 'POST' }); setServices([]); setSettings(null); setLoading(true); checkAuth(); } catch (e) { onError(e.message); } }
  if (!auth) return <div className="connecting"><Logo /><p>{authError || t('관리 엔진과 연결하고 있어요.')}</p>{authError && <button className="secondary" onClick={checkAuth}><RefreshCw size={16} />{t('다시 연결')}</button>}</div>;
  if (!auth.authenticated) return isNative ? <PairPhone api={api} logo={<Logo />} onPaired={checkAuth} /> : <SignIn auth={auth} api={api} logo={<Logo />} onLogin={checkAuth} />;
  return <div className="app-shell">
    <header className="toolbar" aria-label={t('공통 도구')}>
      <div className="toolbar-actions">
        <button className="tool-button" disabled={!connected} onClick={() => setPanel('recommend')} title={t('등록 추천')} aria-label={t('등록 추천')}><ScanSearch size={17} /></button>
        <button className="tool-button" disabled={!connected} onClick={() => { const slot = Array.from({ length: 16 }, (_, i) => i).find(i => !services.some(s => s.padset_id === padsetId && s.slot === i)); if (slot === undefined) onError(t('빈 패드를 확보해 주세요.')); else setRegistrationSlot(slot); }} title={t('서비스 등록')} aria-label={t('서비스 등록')}><Plus size={17} /></button>
        <button className="tool-button" onClick={() => setPanel('settings')} title={t('환경 설정')} aria-label={t('환경 설정')}><Gear size={17} /></button>
      </div>
    </header>
    <main aria-label={t('서비스 패드')}><Deck {...{ padsets, padsetId, onPadsetChange, services, groups, links, loading, settings, refresh, onError, connected }} local={auth.local} /></main>
    {registrationSlot !== null && <PadForm {...{ padsets, padsetId }} defaultCwd={settings?.recommend_roots?.[0] || ''} tools={settings?.tools} slot={registrationSlot} preset={preset} local={auth.local} {...{ services, api, colors, colorNames, onError }} onClose={() => { setRegistrationSlot(null); setPreset(null); }} onSaved={refresh} />}
    <Modal isOpen={!!panel} onClose={() => setPanel(null)} title={panel === 'settings' ? t('환경 설정') : t('등록 추천')} size="lg" storageKey="common-settings">
      {panel === 'settings' ? <Settings {...{ auth, settings, padsets, services, groups, refresh, onError, onNotice }} onLogout={() => { setPanel(null); logout(); }} /> : panel === 'recommend' ? <Recommendations onError={onError} onRegister={candidate => { const slot = Array.from({ length: 16 }, (_, i) => i).find(i => !services.some(s => s.padset_id === padsetId && s.slot === i)); if (slot === undefined) { onError(t('빈 패드를 확보해 주세요.')); return; } setPanel(null); setPreset(candidate); setRegistrationSlot(slot); }} /> : null}
    </Modal>
    {settings && !settings.onboarding_done && auth.local && <FolderOnboarding onDone={refresh} onError={onError} />}
    <Modal isOpen={!!notice} onClose={() => setNotice(null)} title={notice?.title || ''} size="sm" draggable={false} footer={<>{notice?.link && <button className="secondary" onClick={() => { window.open(notice.link, '_blank'); setNotice(null); }}>{t('내려받기')}</button>}<button className="primary" onClick={() => setNotice(null)}>{t('확인')}</button></>}><p className="notice-text">{notice?.message}</p></Modal>
  </div>;
}

loadServer().catch(error => console.warn(error)).finally(() => createRoot(document.getElementById('root')).render(<App />));
