import React, { useState } from 'react';
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react';
import { DockerFields } from './DockerFields.jsx';
import { SelectControl } from './SelectControl.jsx';
import { Tabs } from './Tabs.jsx';
import { Modal } from './Modal/Modal.jsx';
import { emptyRemote, KindSwitch, RemoteFields } from './RemoteFields.jsx';
import { t } from '../i18n.js';

export function PadForm({ pad, preset, services, slot, padsetId = 'default', padsets = [], api, colors, colorNames, local, defaultCwd = '', tools, onClose, onSaved, onError }) {
  const initialComponents = pad?.isGroup ? pad.members : pad ? [pad] : preset ? [preset] : [{ name: '', command: '', cwd: defaultCwd, port: '', health_url: '' }];
  const [form, setForm] = useState({ name: pad?.name || preset?.name || '', color: pad?.color || colors.find(color => !services.some(s => s.color === color)) || colors[slot % colors.length], autostart: pad?.autostart || false, domain_url: pad?.domain_url || '', local_url: pad?.local_url || '', wait_ready: pad?.wait_ready || false, slot: pad?.slot ?? slot, padset_id: pad?.padset_id || padsetId, components: initialComponents.map(s => ({ ...(s.id ? { id: s.id } : {}), container: s.container || '', kind: s.kind || 'local', name: s.name, command: s.command || '', cwd: s.cwd || defaultCwd, port: s.port || '', health_url: s.health_url || '', remote: s.remote || emptyRemote })) });
  const [tab, setTab] = useState('general');
  const [pending, setPending] = useState(false);
  const running = pad?.isGroup ? pad.members.some(s => !!s.pid || (s.kind === 'docker' && s.active)) : !!pad?.pid || (pad?.kind === 'docker' && pad.active);
  // Remote commands run with this PC's SSH keys, so only this PC may change them.
  const remoteLocked = !local && initialComponents.some(s => s.kind === 'remote');
  const readOnly = running || remoteLocked;
  const common = readOnly && pad ? pad : form;
  const displayed = readOnly && pad ? pad.isGroup ? pad.members : [pad] : form.components;
  const set = (key, value) => { if (!readOnly && !pending) setForm(current => ({ ...current, [key]: value })); };
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
    if (readOnly || pending) return;
    const invalid = event.currentTarget.querySelector(':invalid');
    if (invalid) {
      setTab(invalid.closest('.pad-common') ? 'general' : 'services');
      requestAnimationFrame(() => { invalid.focus(); invalid.reportValidity(); });
      return;
    }
    setPending(true);
    try {
      const components = form.components.map(c => {
        const base = { ...(c.id ? { id: c.id } : {}), kind: c.kind, name: form.components.length === 1 ? form.name : c.name };
        return c.kind === 'docker' ? { ...base, container: c.container } : c.kind === 'remote' ? { ...base, remote: c.remote } : { ...base, command: c.command, cwd: c.cwd, port: c.port ? Number(c.port) : null, health_url: c.health_url };
      });
      const result = await api(`/pads${pad ? `/${pad.id}` : ''}`, { method: pad ? 'PUT' : 'POST', body: JSON.stringify({ ...form, autostart: allRemote ? false : form.autostart, components }) });
      await onSaved(result.id); onClose();
    } catch (error) { onError(error.message); }
    finally { setPending(false); }
  }
  return <Modal isOpen onClose={() => { if (!pending) onClose(); }} title={pad ? t('패드 설정') : t('서비스 등록')} storageKey="pad-editor" size="lg">
    <form className="service-form pad-form" onSubmit={save} noValidate>
      <Tabs label={t('패드 설정 카테고리')} tabs={[{ id: 'general', name: t('일반') }, { id: 'services', name: t('서비스') }]} value={tab} onChange={setTab} prefix="pad-editor" />
      <div role="tabpanel" id="pad-editor-panel" aria-labelledby={`pad-editor-tab-${tab}`}>
      <div className="pad-common" hidden={tab !== 'general'}>
        <div className="pad-location-row"><label>{t('패드셋')}<SelectControl aria-label={t('패드셋')} value={common.padset_id || padsetId} disabled={readOnly || pending} onChange={e => {
          const occupied = new Set(services.filter(s => s.padset_id === e.target.value && !(pad?.isGroup ? pad.member_ids : [pad?.id]).includes(s.id)).map(s => s.slot));
          const free = Array.from({ length: 16 }, (_, i) => i).find(i => !occupied.has(i));
          if (free === undefined) { onError(t('선택한 패드셋에 빈 패드를 확보해 주세요.')); return; }
          setForm(current => ({ ...current, padset_id: e.target.value, slot: free }));
        }}>{padsets.map(s => <option value={s.id} key={s.id}>{s.name}</option>)}</SelectControl></label>
        <label>{t('패드 이름')}<input required readOnly={readOnly || pending} maxLength={40} value={common.name} onChange={e => set('name', e.target.value)} placeholder={t('예: Shop')} autoFocus /></label></div>
        <div className="link-row">
          <label><span>{t('도메인 URL')} <span className="optional">{t('선택')}</span></span><input aria-label={t('도메인 URL')} type="url" readOnly={readOnly || pending} maxLength={1000} value={common.domain_url || ''} onChange={e => set('domain_url', e.target.value)} placeholder="https://app.example.com/" /></label>
          <label><span>{t('로컬 URL')} <span className="optional">{t('비우면 포트로 자동 결정')}</span></span><input aria-label={t('로컬 URL')} type="url" readOnly={readOnly || pending} maxLength={1000} value={common.local_url || ''} onChange={e => set('local_url', e.target.value)} placeholder="http://localhost:5173/" /></label>
        </div>
        <fieldset className="color-field" disabled={readOnly || pending}><legend>{t('패드 색상')}</legend><div className="colors">{colors.map((color, index) => <button type="button" key={color} className={common.color === color ? 'selected' : ''} style={{ '--color': color }} onClick={() => set('color', color)} aria-label={colorNames[index]} aria-pressed={common.color === color} />)}</div></fieldset>
        {allRemote ? <p className="optional">{t('원격 서버 서비스는 서버에서 관리하므로 자동 실행 대상에서 제외됩니다.')}</p> : <label className="check-row"><input type="checkbox" disabled={readOnly || pending} checked={common.autostart} onChange={e => set('autostart', e.target.checked)} /><span>{t('관리 엔진 시작 시 패드 자동 실행')}{someRemote ? t(' (원격 서버 서비스 제외)') : ''}</span></label>}
        {displayed.length > 1 && <label className="check-row"><input type="checkbox" disabled={readOnly || pending} checked={common.wait_ready} onChange={e => set('wait_ready', e.target.checked)} /><span>{t('앞 서비스가 정상 응답한 뒤 다음 서비스 실행')}</span></label>}
      </div>
      <div hidden={tab !== 'services'}><div className="registration-services">{displayed.map((component, index) => {
        const current = readOnly && component.id ? services.find(s => s.id === component.id) || component : component;
        return <section className="registration-service" key={component.id || `new-${index}`} aria-label={t('서비스 {0}', index + 1)}>
          <div className="registration-service-head"><h3>{t('서비스')} {index + 1}</h3>{displayed.length > 1 && <div>
            <button className="tool-button" type="button" disabled={readOnly || pending || index === 0} aria-label={t('서비스 {0} 순서 앞으로', index + 1)} onClick={() => { const list = [...form.components]; [list[index - 1], list[index]] = [list[index], list[index - 1]]; set('components', list); }}><ArrowUp size={15} /></button>
            <button className="tool-button" type="button" disabled={readOnly || pending || index === form.components.length - 1} aria-label={t('서비스 {0} 순서 뒤로', index + 1)} onClick={() => { const list = [...form.components]; [list[index + 1], list[index]] = [list[index], list[index + 1]]; set('components', list); }}><ArrowDown size={15} /></button>
            <button className="delete-button" type="button" disabled={readOnly || pending} aria-label={t('서비스 {0} 제거', index + 1)} onClick={() => set('components', form.components.filter((_, i) => i !== index))}><Trash2 size={15} /></button>
          </div>}</div>
          {displayed.length > 1 && <label>{t('서비스 이름')}<input required readOnly={readOnly || pending} maxLength={40} value={current.name} onChange={e => set('components', form.components.map((c, i) => i === index ? { ...c, name: e.target.value } : c))} placeholder={index === 0 ? t('예: 백엔드') : t('예: 프론트엔드')} /></label>}
          <KindSwitch kind={current.kind} local={local} docker={tools?.docker !== false} disabled={readOnly || pending} onChange={kind => patch(index, { kind })} />
          {current.kind === 'docker' ? <DockerFields value={current.container || ''} containerName={current.container_name || current.name} readOnly={readOnly || pending} api={api} onChange={(containerId, containerObj) => onDockerChange(index, containerId, containerObj)} /> : current.kind === 'remote' ? <RemoteFields value={current.remote || emptyRemote} readOnly={readOnly || pending} api={api} onChange={remote => patch(index, { remote })} /> : <>
          <label>{t('실행 명령')}<textarea required readOnly={readOnly || pending} rows={2} maxLength={2000} value={current.command} onChange={e => set('components', form.components.map((c, i) => i === index ? { ...c, command: e.target.value } : c))} placeholder={t('예: uv run uvicorn main:app --port 8000')} /></label>
          <label>{t('작업 폴더')}<input required readOnly={readOnly || pending} value={current.cwd} onChange={e => set('components', form.components.map((c, i) => i === index ? { ...c, cwd: e.target.value } : c))} placeholder="C:\Users\me\my-app" /></label>
          <div className="form-row"><label>{t('포트')} <span className="optional">{t('선택')}</span><input type="number" readOnly={readOnly || pending} min={1} max={65535} value={current.port || ''} onChange={e => set('components', form.components.map((c, i) => i === index ? { ...c, port: e.target.value } : c))} /></label><label>{t('상태 확인 URL')} <span className="optional">{t('선택')}</span><input type="url" readOnly={readOnly || pending} value={current.health_url} onChange={e => set('components', form.components.map((c, i) => i === index ? { ...c, health_url: e.target.value } : c))} placeholder="http://127.0.0.1:8000/health" /></label></div>
          </>}
        </section>;
      })}</div>
      {!readOnly && <button className="secondary add-service" type="button" disabled={pending || form.components.length >= 16} onClick={() => set('components', [...form.components.map((c, i) => i === 0 && form.components.length === 1 && !c.name ? { ...c, name: form.name } : c), { kind: 'local', name: '', command: '', cwd: form.components.find(c => c.kind !== 'remote')?.cwd || defaultCwd, port: '', health_url: '', remote: emptyRemote }])}><Plus size={16} />{t('서비스 추가')}</button>}
      </div></div>
      <div className="form-actions"><button type="button" className="secondary" disabled={pending} onClick={onClose}>{readOnly ? t('닫기') : t('취소')}</button>{!readOnly && <button className="primary" disabled={pending}>{t('저장')}</button>}</div>
    </form>
  </Modal>;
}
