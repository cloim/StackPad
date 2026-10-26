import React, { useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react';
import { DockerFields } from './DockerFields.jsx';
import { SelectControl } from './SelectControl.jsx';
import { Tabs } from './Tabs.jsx';
import { Modal } from './Modal/Modal.jsx';
import { ConfirmModal } from './ConfirmModal.jsx';
import { useFieldError } from './FieldError.jsx';
import { emptyRemote, KindSwitch, RemoteFields } from './RemoteFields.jsx';
import { formatNextRun } from './SceneSettings.jsx';
import { t } from '../i18n.js';

export function PadForm({ pad, preset, services, slot, padsetId = 'default', padsets = [], schedules = [], api, colors, colorNames, local, defaultCwd = '', tools, onClose, onSaved, onError }) {
  const initialComponents = pad?.isGroup ? pad.members : pad ? [pad] : preset ? [preset] : [{ name: '', command: '', cwd: defaultCwd, port: '', health_url: '', restart_policy: 'never', restart_max: 3 }];
  const [form, setForm] = useState({ environment: pad?.environment || 'development', name: pad?.name || preset?.name || '', color: pad?.color || colors.find(color => !services.some(s => s.color === color)) || colors[slot % colors.length], autostart: pad?.autostart || false, domain_url: pad?.domain_url || '', local_url: pad?.local_url || '', wait_ready: pad?.wait_ready || false, slot: pad?.slot ?? slot, padset_id: pad?.padset_id || padsetId, components: initialComponents.map(s => ({ ...(s.id ? { id: s.id } : {}), container: s.container || '', kind: s.kind || 'local', name: s.name, command: s.command || '', cwd: s.cwd || defaultCwd, port: s.port || '', health_url: s.health_url || '', restart_policy: s.restart_policy || 'never', restart_max: s.restart_max ?? 3, remote: s.remote || emptyRemote })) });
  const [tab, setTab] = useState('general');
  const [pending, setPending] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const initialForm = useRef(form);
  const fieldError = useFieldError();
  const close = () => { if (pending) return; if (form !== initialForm.current) setDiscarding(true); else onClose(); };
  const running = (pad?.isGroup ? pad.members : pad ? [pad] : []).some(s => s.active || s.pid || s.external_pid || s.status === 'restarting');
  // Remote commands run with this PC's SSH keys, so only this PC may change them.
  const remoteLocked = !local && initialComponents.some(s => s.kind === 'remote');
  const readOnly = running || remoteLocked;
  const common = form;
  const displayed = form.components;
  const set = (key, value) => { if (!pending) setForm(current => ({ ...current, [key]: value })); };
  const patch = (index, values) => set('components', form.components.map((c, i) => i === index ? { ...c, ...values } : c));
  const onDockerChange = (index, containerId, containerObj) => {
    if (readOnly || pending) return;
    const containerName = containerObj?.name || '';
    setForm(current => {
      const target = current.components[index];
      const nextName = target?.name ? target.name : containerName;
      const nextComponents = current.components.map((c, i) => i === index ? { ...c, container: containerId, name: nextName } : c);
      const shouldFillPadName = !current.name.trim();
      return {
        ...current,
        name: shouldFillPadName && containerName ? containerName : current.name,
        components: nextComponents
      };
    });
  };
  const allRemote = displayed.every(c => c.kind === 'remote');
  const someRemote = displayed.some(c => c.kind === 'remote');
  async function save(event) {
    event.preventDefault();
    if (pending) return;
    const invalid = event.currentTarget.querySelector(':invalid:not(fieldset)');
    if (invalid) setTab(invalid.closest('.pad-common') ? 'general' : 'services');
    if (!fieldError.validate(event.currentTarget)) return;
    setPending(true);
    try {
      const components = form.components.map(c => {
        const base = { ...(c.id ? { id: c.id } : {}), kind: c.kind, name: form.components.length === 1 ? form.name : c.name };
        return c.kind === 'docker' ? { ...base, container: c.container } : c.kind === 'remote' ? { ...base, remote: c.remote } : { ...base, command: c.command, cwd: c.cwd, port: c.port ? Number(c.port) : null, health_url: c.health_url, restart_policy: c.restart_policy || 'never', restart_max: Number(c.restart_max ?? 3) };
      });
      const result = await api(`/pads${pad ? `/${pad.id}` : ''}`, { method: pad ? 'PUT' : 'POST', body: JSON.stringify({ ...form, autostart: allRemote ? false : form.autostart, components }) });
      await onSaved(result.id, form.padset_id); onClose();
    } catch (error) { onError(error.message); }
    finally { setPending(false); }
  }
  return <Modal isOpen onClose={close} closeOnOverlayClick={false} title={pad ? t('패드 설정') : t('서비스 등록')} storageKey="pad-editor" size="lg">
    <form className="service-form pad-form" onSubmit={save} noValidate>
      {readOnly && <p className="form-notice" role="note">{remoteLocked ? t('원격 서버 서비스는 StackPad가 실행 중인 PC에서만 바꿀 수 있어요.') : t('실행 중인 패드는 실행 방식과 명령을 바꿀 수 없어요. 패드를 종료한 뒤 다시 열어 주세요.')}</p>}
      <Tabs label={t('패드 설정 카테고리')} tabs={[{ id: 'general', name: t('일반') }, { id: 'services', name: t('서비스') }]} value={tab} onChange={setTab} prefix="pad-editor" />
      <div role="tabpanel" id="pad-editor-panel" aria-labelledby={`pad-editor-tab-${tab}`}>
      <div className="pad-common" hidden={tab !== 'general'}>
        <div className="pad-location-row"><label>{t('패드셋')}<SelectControl aria-label={t('패드셋')} value={form.padset_id} disabled={pending} onChange={e => {
          const occupied = new Set(services.filter(s => s.padset_id === e.target.value && !(pad?.isGroup ? pad.member_ids : [pad?.id]).includes(s.id)).map(s => s.slot));
          const free = Array.from({ length: 16 }, (_, i) => i).find(i => !occupied.has(i));
          if (free === undefined) { onError(t('선택한 패드셋에 빈 패드를 확보해 주세요.')); return; }
          setForm(current => ({ ...current, padset_id: e.target.value, slot: free }));
        }}>{padsets.map(s => <option value={s.id} key={s.id}>{s.name}</option>)}</SelectControl></label>
        <label>{t('패드 이름')}<input required readOnly={pending} maxLength={40} value={common.name} onChange={e => set('name', e.target.value)} placeholder={t('예: Shop')} autoFocus /></label></div>
        <label>{t('서비스 용도')}<SelectControl aria-label={t('서비스 용도')} value={common.environment || 'development'} disabled={pending} onChange={e => set('environment', e.target.value)}><option value="development">{t('개발용')}</option><option value="production">{t('운영용')}</option></SelectControl></label>
        <div className="link-row">
          <label><span>{t('도메인 URL')} <span className="optional">{t('선택')}</span></span><input aria-label={t('도메인 URL')} type="url" readOnly={pending} maxLength={1000} value={common.domain_url || ''} onChange={e => set('domain_url', e.target.value)} placeholder="https://app.example.com/" /></label>
          <label><span>{t('로컬 URL')} <span className="optional">{t('비우면 포트로 자동 결정')}</span></span><input aria-label={t('로컬 URL')} type="url" readOnly={pending} maxLength={1000} value={common.local_url || ''} onChange={e => set('local_url', e.target.value)} placeholder="http://localhost:5173/" /></label>
        </div>
        <fieldset className="color-field" disabled={pending}><legend>{t('패드 색상')}</legend><div className="colors">{colors.map((color, index) => <button type="button" key={color} className={form.color === color ? 'selected' : ''} style={{ '--color': color }} onClick={() => set('color', color)} aria-label={colorNames[index]} aria-pressed={form.color === color} />)}</div></fieldset>
        {allRemote ? <p className="optional">{t('원격 서버 서비스는 서버에서 관리하므로 자동 실행 대상에서 제외됩니다.')}</p> : <label className="check-row"><input type="checkbox" disabled={pending} checked={common.autostart} onChange={e => set('autostart', e.target.checked)} /><span>{t('관리 엔진 시작 시 패드 자동 실행')}{someRemote ? t(' (원격 서버 서비스 제외)') : ''}</span></label>}
        {displayed.length > 1 && <label className="check-row"><input type="checkbox" disabled={pending} checked={common.wait_ready} onChange={e => set('wait_ready', e.target.checked)} /><span>{t('앞 서비스가 정상 응답한 뒤 다음 서비스 실행')}</span></label>}
        {pad?.id && (() => {
          const padSchedules = schedules.filter(s => s.target_type === 'pad' && s.target_id === pad.id);
          if (!padSchedules.length) return null;
          return <div className="pad-schedules-summary">
            <span className="summary-title">{t('예약 실행')}</span>
            <ul className="summary-list">
              {padSchedules.map(s => <li key={s.id}>
                <span>{s.action === 'start' ? t('시작') : t('정지')}</span> {s.time} ({formatNextRun(s)})
              </li>)}
            </ul>
          </div>;
        })()}
      </div>
      <div hidden={tab !== 'services'}><div className="registration-services">{displayed.map((component, index) => {
        const current = component;
        return <section className="registration-service" key={component.id || `new-${index}`} aria-label={t('서비스 {0}', index + 1)}>
          <div className="registration-service-head"><h3>{t('서비스')} {index + 1}</h3>{displayed.length > 1 && <div>
            <button className="tool-button max-tablet:w-[30px]" type="button" disabled={readOnly || pending || index === 0} aria-label={t('서비스 {0} 순서 앞으로', index + 1)} onClick={() => { const list = [...form.components]; [list[index - 1], list[index]] = [list[index], list[index - 1]]; set('components', list); }}><ArrowUp size={15} /></button>
            <button className="tool-button max-tablet:w-[30px]" type="button" disabled={readOnly || pending || index === form.components.length - 1} aria-label={t('서비스 {0} 순서 뒤로', index + 1)} onClick={() => { const list = [...form.components]; [list[index + 1], list[index]] = [list[index], list[index + 1]]; set('components', list); }}><ArrowDown size={15} /></button>
            <button className="delete-button h-[38px] w-9 rounded-md text-[#ee8e9c] hover:bg-[#ee8e9c15] max-tablet:w-[30px]" type="button" disabled={readOnly || pending} aria-label={t('서비스 {0} 제거', index + 1)} onClick={() => set('components', form.components.filter((_, i) => i !== index))}><Trash2 size={15} /></button>
          </div>}</div>
          {displayed.length > 1 && <label>{t('서비스 이름')}<input required readOnly={pending} maxLength={40} value={current.name} onChange={e => set('components', form.components.map((c, i) => i === index ? { ...c, name: e.target.value } : c))} placeholder={index === 0 ? t('예: 백엔드') : t('예: 프론트엔드')} /></label>}
          <KindSwitch kind={current.kind} local={local} docker={tools?.docker !== false} disabled={readOnly || pending} onChange={kind => patch(index, { kind })} />
          {current.kind === 'docker' ? <DockerFields value={current.container || ''} containerName={current.container_name || current.name} readOnly={readOnly || pending} api={api} onChange={(containerId, containerObj) => onDockerChange(index, containerId, containerObj)} /> : current.kind === 'remote' ? <RemoteFields value={current.remote || emptyRemote} readOnly={readOnly || pending} api={api} onChange={remote => patch(index, { remote })} /> : <>
          <label>{t('실행 명령')}<textarea required readOnly={readOnly || pending} rows={2} maxLength={2000} value={current.command} onChange={e => set('components', form.components.map((c, i) => i === index ? { ...c, command: e.target.value } : c))} placeholder={t('예: uv run uvicorn main:app --port 8000')} /></label>
          <label>{t('작업 폴더')}<input required readOnly={readOnly || pending} value={current.cwd} onChange={e => set('components', form.components.map((c, i) => i === index ? { ...c, cwd: e.target.value } : c))} placeholder="C:\Users\me\my-app" /></label>
          <div className="form-row"><label><span>{t('포트')} <span className="optional">{t('선택')}</span></span><input type="number" readOnly={readOnly || pending} min={1} max={65535} value={current.port || ''} onChange={e => set('components', form.components.map((c, i) => i === index ? { ...c, port: e.target.value } : c))} /></label><label><span>{t('상태 확인 URL')} <span className="optional">{t('선택')}</span></span><input type="url" readOnly={pending} value={current.health_url} onChange={e => set('components', form.components.map((c, i) => i === index ? { ...c, health_url: e.target.value } : c))} placeholder="http://127.0.0.1:8000/health" /></label></div>
          <div className="form-row"><label className="check-row"><input type="checkbox" disabled={pending} checked={current.restart_policy === 'on-failure'} onChange={e => patch(index, { restart_policy: e.target.checked ? 'on-failure' : 'never' })} /><span>{t('비정상 종료 시 자동 재시작')}</span></label>{current.restart_policy === 'on-failure' && <label>{t('최대 재시작 횟수')}<input type="number" min={1} max={10} disabled={pending} value={current.restart_max ?? 3} onChange={e => patch(index, { restart_max: Math.max(1, Math.min(10, Number(e.target.value) || 1)) })} /></label>}</div>
          </>}
        </section>;
      })}</div>
      {!readOnly && <button className="secondary add-service" type="button" disabled={pending || form.components.length >= 16} onClick={() => set('components', [...form.components.map((c, i) => i === 0 && form.components.length === 1 && !c.name ? { ...c, name: form.name } : c), { kind: 'local', name: '', command: '', cwd: form.components.find(c => c.kind !== 'remote')?.cwd || defaultCwd, port: '', health_url: '', restart_policy: 'never', restart_max: 3, remote: emptyRemote }])}><Plus size={16} />{t('서비스 추가')}</button>}
      </div></div>
      <div className="form-actions"><button type="button" className="secondary" disabled={pending} onClick={close}>{t('취소')}</button><button className="primary" disabled={pending}>{t('저장')}</button></div>
    </form>
    {fieldError.popover}
    <ConfirmModal isOpen={discarding} title={t('저장하지 않은 변경 사항')} confirmLabel={t('버리고 닫기')} message={t('저장하지 않은 변경 사항이 있어요. 버리고 닫을까요?')} onCancel={() => setDiscarding(false)} onConfirm={() => { setDiscarding(false); onClose(); }} />
  </Modal>;
}
