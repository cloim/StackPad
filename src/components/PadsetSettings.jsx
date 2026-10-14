import React, { useRef, useState } from 'react';
import { GripVertical, Plus, Trash2 } from 'lucide-react';
import { t } from '../i18n.js';

export function PadsetSettings({ padsets, services, groups, api, refresh, onError }) {
  const [drafts, setDrafts] = useState({});
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [dragged, setDragged] = useState(null);
  const [target, setTarget] = useState(null);
  const pointerDrag = useRef(null);
  const grouped = new Set(groups.flatMap(g => g.member_ids));
  async function reorder(source, destination) {
    setDragged(null); setTarget(null);
    if (busy || !source || source === destination) return;
    const ids = padsets.map(s => s.id);
    const index = ids.indexOf(destination);
    if (index < 0 || !ids.includes(source)) return;
    ids.splice(ids.indexOf(source), 1);
    ids.splice(index, 0, source);
    setBusy(true);
    try { await api('/padsets/order', { method: 'PUT', body: JSON.stringify({ ids }) }); await refresh(); }
    catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  async function save(id, remove = false) {
    setBusy(true);
    try {
      await api(`/padsets${id ? `/${id}` : ''}`, { method: remove ? 'DELETE' : id ? 'PUT' : 'POST', ...(!remove ? { body: JSON.stringify({ name: id ? drafts[id] : name }) } : {}) });
      if (!id) setName('');
      setDrafts(current => { const next = { ...current }; delete next[id]; return next; });
      await refresh();
    } catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  return <section className="padset-settings"><p className="optional">{t('각 패드셋에는 16개의 패드가 있습니다. 빈 패드셋을 삭제할 수 있어요.')}</p>
    <div className="padset-list" aria-busy={busy}>{padsets.map((set, index) => {
      const count = services.filter(s => s.padset_id === set.id && !grouped.has(s.id)).length + groups.filter(g => g.padset_id === set.id).length;
      return <form className={`padset-row ${dragged === set.id ? 'dragging' : ''} ${target === set.id ? 'drop-target' : ''}`} data-padset-id={set.id} key={set.id} onSubmit={e => { e.preventDefault(); save(set.id); }}>
        <button className="tool-button padset-grip" type="button" draggable={false} disabled={busy || padsets.length < 2} aria-label={t('{0} 패드셋 순서 이동', set.name)} title={t('드래그하여 순서 변경, 키보드 위아래 화살표로 이동')} onKeyDown={e => {
          if (!['ArrowUp', 'ArrowDown'].includes(e.key)) return;
          e.preventDefault();
          const next = padsets[index + (e.key === 'ArrowUp' ? -1 : 1)];
          if (next) reorder(set.id, next.id);
        }} onPointerDown={e => {
          if (e.button !== 0 || busy || padsets.length < 2) return;
          e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId);
          pointerDrag.current = { id: set.id, pointerId: e.pointerId, target: set.id }; setDragged(set.id);
        }} onPointerMove={e => {
          if (pointerDrag.current?.pointerId !== e.pointerId) return;
          const row = document.elementFromPoint(e.clientX, e.clientY)?.closest('[data-padset-id]');
          pointerDrag.current.target = row?.dataset.padsetId; setTarget(row?.dataset.padsetId || null);
        }} onPointerUp={e => {
          if (pointerDrag.current?.pointerId !== e.pointerId) return;
          const current = pointerDrag.current; pointerDrag.current = null; reorder(current.id, current.target);
        }} onPointerCancel={() => { pointerDrag.current = null; setDragged(null); setTarget(null); }}><GripVertical size={16} /></button>
        <input aria-label={t('{0} 패드셋 이름', set.name)} required maxLength={40} value={drafts[set.id] ?? set.name} disabled={busy} onChange={e => setDrafts({ ...drafts, [set.id]: e.target.value })} />
        <span className="optional padset-count">{count}/16</span>
        <button className="secondary" disabled={busy || drafts[set.id] === undefined || drafts[set.id] === set.name}>{t('저장')}</button>
        <button className="delete-button" type="button" aria-label={t('{0} 패드셋 삭제', set.name)} title={count ? t('빈 패드셋을 삭제할 수 있어요.') : padsets.length === 1 ? t('패드셋을 하나 이상 유지해 주세요.') : t('패드셋 삭제')} disabled={busy || !!count || padsets.length === 1} onClick={() => save(set.id, true)}><Trash2 size={16} /></button>
      </form>;
    })}</div>
    <form className="compact-input-row" onSubmit={e => { e.preventDefault(); save(); }}><input aria-label={t('새 패드셋 이름')} placeholder={t('새 패드셋 이름')} required maxLength={40} value={name} disabled={busy} onChange={e => setName(e.target.value)} /><button className="primary" disabled={busy || !name.trim()}><Plus size={15} />{t('추가')}</button></form>
  </section>;
}
