import React, { useId, useRef, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { SceneEditModal, ScheduleEditModal, formatNextRun } from './SceneSettings.jsx';
import { t } from '../i18n.js';

// Edits remain in the pad draft until its Save action succeeds.
export function PadAutomation({ tab, value, onChange, pad, allPads, colors, colorNames, pending }) {
  const draftPrefix = useId();
  const nextSchedule = useRef(0);
  const [editingScene, setEditingScene] = useState(null);
  const [editingSchedule, setEditingSchedule] = useState(null);
  const relatedScenes = value.scenes.filter(s => s.pad_ids.includes(pad.id));
  const visibleSchedules = value.schedules.filter(s => s.target_type === 'pad' || relatedScenes.some(scene => scene.id === s.target_id));
  const updateScene = scene => onChange({ ...value, scenes: value.scenes.map(s => s.id === scene.id ? scene : s) });
  return <>
    <div hidden={tab !== 'schedules'} className="flex flex-col gap-3">
      <button type="button" className="secondary self-start" disabled={pending} onClick={() => setEditingSchedule({ target_type: 'pad', target_id: pad.id, action: 'start', time: '09:00', days: [0, 1, 2, 3, 4], enabled: true })}><Plus size={15} />{t('예약 추가')}</button>
      {visibleSchedules.map(schedule => <div key={schedule.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line p-3">
        <div className="min-w-0 flex-1 text-[12px]">
          <strong>{schedule.action === 'start' ? t('시작') : t('정지')} {schedule.time}</strong>
          {schedule.target_type === 'scene' && <p>{t('흐름')}: {relatedScenes.find(s => s.id === schedule.target_id)?.name}</p>}
          <p>{formatNextRun(schedule)}</p>
          {schedule.target_type === 'scene' && <p>{t('흐름 예약은 포함된 모든 패드에 적용됩니다.')}</p>}
        </div>
        <button type="button" role="switch" aria-checked={schedule.enabled} aria-label={t('{0} 예약 활성화', `${pad.name} ${schedule.time}`)} className={`switch ${schedule.enabled ? 'on' : ''}`} disabled={pending} onClick={() => onChange({ ...value, schedules: value.schedules.map(s => s.id === schedule.id ? { ...s, enabled: !s.enabled } : s) })}><span /></button>
        <button type="button" className="secondary small-btn" disabled={pending} aria-label={t('{0} 예약 편집', schedule.time)} onClick={() => setEditingSchedule(schedule)}>{t('편집')}</button>
        <button type="button" className="delete-button size-8" disabled={pending} aria-label={t('{0} 예약 삭제', schedule.time)} onClick={() => onChange({ ...value, schedules: value.schedules.filter(s => s.id !== schedule.id) })}><Trash2 size={15} /></button>
      </div>)}
    </div>
    <div hidden={tab !== 'scenes'} className="flex flex-col gap-3">
      {value.scenes.map(scene => <div key={scene.id} className="flex items-center gap-2 rounded-lg border border-line p-3">
        <label className="min-w-0 flex-1 flex-row items-center gap-2">
          <input type="checkbox" disabled={pending || (!scene.pad_ids.includes(pad.id) && scene.pad_ids.length >= 16)} checked={scene.pad_ids.includes(pad.id)} onChange={e => updateScene({ ...scene, pad_ids: e.target.checked ? [...scene.pad_ids, pad.id] : scene.pad_ids.filter(id => id !== pad.id) })} />
          <span className="truncate">{scene.name}</span>
        </label>
        {scene.pad_ids.includes(pad.id) && <button type="button" className="secondary small-btn" disabled={pending} aria-label={t('{0} 흐름 편집', scene.name)} onClick={() => setEditingScene(scene)}>{t('편집')}</button>}
      </div>)}
    </div>
    {editingScene && <SceneEditModal scene={editingScene} allPads={allPads} colors={colors} colorNames={colorNames} busy={pending} onClose={() => setEditingScene(null)} onSave={scene => { updateScene(scene); setEditingScene(null); }} />}
    {editingSchedule && <ScheduleEditModal schedule={editingSchedule} scenes={relatedScenes} sceneOnly={editingSchedule.target_type === 'scene'} allPads={[pad]} busy={pending} onClose={() => setEditingSchedule(null)} onSave={schedule => {
      const id = schedule.id || `${draftPrefix}-${nextSchedule.current++}`;
      onChange({ ...value, schedules: editingSchedule.id ? value.schedules.map(s => s.id === id ? { ...schedule, id } : s) : [...value.schedules, { ...schedule, id }] });
      setEditingSchedule(null);
    }} />}
  </>;
}
