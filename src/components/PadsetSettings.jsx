import React, { useEffect, useState } from 'react';
import { GripVertical, Plus, Trash2 } from 'lucide-react';
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useFieldError } from './FieldError.jsx';
import { t } from '../i18n.js';

function PadsetRow({ set, count, only, busy, draft, onDraft, onSave, onDelete, sortable }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id: set.id, data: { name: set.name }, disabled: !sortable });
  const deleteHint = count ? t('패드가 있는 패드셋은 삭제할 수 없어요. 패드를 옮기거나 삭제해 주세요.') : only ? t('패드셋을 하나 이상 유지해 주세요.') : null;
  return <form ref={setNodeRef} className={`padset-row ${isDragging ? 'dragging' : ''}`} style={{ transform: CSS.Transform.toString(transform), transition }} onSubmit={event => { event.preventDefault(); onSave(event.currentTarget); }} noValidate>
    <button ref={setActivatorNodeRef} {...attributes} {...listeners} className="tool-button padset-grip" type="button" disabled={!sortable} aria-label={t('{0} 패드셋 순서 이동', set.name)}><GripVertical size={16} /></button>
    <input aria-label={t('{0} 패드셋 이름', set.name)} required pattern=".*\S.*" maxLength={40} value={draft ?? set.name} disabled={busy} onChange={event => onDraft(event.target.value)} />
    <span className="optional padset-count">{count}/16</span>
    <button className="secondary" disabled={busy || draft === undefined || draft === set.name}>{t('저장')}</button>
    <button className="delete-button w-8" type="button" aria-label={t('{0} 패드셋 삭제', set.name)} aria-describedby={deleteHint ? `padset-delete-hint-${set.id}` : undefined} disabled={busy || !!deleteHint} onClick={onDelete}><Trash2 size={16} /></button>
    {deleteHint && <span id={`padset-delete-hint-${set.id}`} hidden>{deleteHint}</span>}
  </form>;
}

export function PadsetSettings({ padsets, services, groups, api, refresh, onError }) {
  const [drafts, setDrafts] = useState({});
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  // The dropped order shows right away and stays until the engine sends the saved one back.
  const [order, setOrder] = useState(null);
  useEffect(() => { setOrder(null); }, [padsets]);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const fieldError = useFieldError();
  const grouped = new Set(groups.flatMap(g => g.member_ids));
  const ordered = order ? order.map(id => padsets.find(set => set.id === id)).filter(Boolean) : padsets;
  const counts = Object.fromEntries(padsets.map(set => [set.id, services.filter(s => s.padset_id === set.id && !grouped.has(s.id)).length + groups.filter(g => g.padset_id === set.id).length]));

  async function reorder({ active, over }) {
    if (!over || active.id === over.id) return;
    const ids = ordered.map(set => set.id);
    const next = arrayMove(ids, ids.indexOf(active.id), ids.indexOf(over.id));
    setOrder(next);
    setBusy(true);
    try { await api('/padsets/order', { method: 'PUT', body: JSON.stringify({ ids: next }) }); await refresh(); }
    catch (e) { setOrder(null); onError(e.message); } finally { setBusy(false); }
  }
  async function save(id, form, remove = false) {
    if (form && !fieldError.validate(form)) return;
    setBusy(true);
    try {
      await api(`/padsets${id ? `/${id}` : ''}`, { method: remove ? 'DELETE' : id ? 'PUT' : 'POST', ...(!remove ? { body: JSON.stringify({ name: (id ? drafts[id] : name).trim() }) } : {}) });
      if (!id) setName('');
      setDrafts(current => { const next = { ...current }; delete next[id]; return next; });
      await refresh();
    } catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  const sortable = !busy && padsets.length > 1;
  const announcements = {
    onDragStart: ({ active }) => t('{0} 패드셋을 들었습니다. 위아래 방향키로 옮기세요.', active.data.current.name),
    onDragOver: ({ over }) => over ? t('{0}번째 위치입니다.', ordered.findIndex(set => set.id === over.id) + 1) : '',
    onDragEnd: ({ active, over }) => over ? t('{0} 패드셋을 {1}번째로 옮겼습니다.', active.data.current.name, ordered.findIndex(set => set.id === over.id) + 1) : t('이동을 취소했습니다.'),
    onDragCancel: () => t('이동을 취소했습니다.'),
  };
  return <section className="padset-settings"><p className="optional">{t('각 패드셋에는 16개의 패드가 있습니다. 빈 패드셋을 삭제할 수 있어요. 손잡이를 끌거나 스페이스 키와 방향키로 순서를 바꿀 수 있어요.')}</p>
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={reorder} accessibility={{ announcements, screenReaderInstructions: { draggable: t('스페이스 키로 패드셋을 들고 위아래 방향키로 옮긴 뒤 스페이스 키로 놓습니다. ESC 키로 취소합니다.') } }}>
      <SortableContext items={ordered.map(set => set.id)} strategy={verticalListSortingStrategy}>
        <div className="padset-list" aria-busy={busy}>{ordered.map(set => <PadsetRow key={set.id} set={set} count={counts[set.id]} only={padsets.length === 1} busy={busy} sortable={sortable} draft={drafts[set.id]} onDraft={value => setDrafts(current => ({ ...current, [set.id]: value }))} onSave={form => save(set.id, form)} onDelete={() => save(set.id, null, true)} />)}</div>
      </SortableContext>
    </DndContext>
    <form className="compact-input-row" onSubmit={e => { e.preventDefault(); save(null, e.currentTarget); }} noValidate><input aria-label={t('새 패드셋 이름')} placeholder={t('새 패드셋 이름')} required pattern=".*\S.*" maxLength={40} value={name} disabled={busy} onChange={e => setName(e.target.value)} /><button className="primary" disabled={busy}><Plus size={15} />{t('추가')}</button></form>
    {fieldError.popover}
  </section>;
}
