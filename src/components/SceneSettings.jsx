import React, { useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Film, Plus, Trash2 } from 'lucide-react';
import { SelectControl } from './SelectControl.jsx';
import { Modal } from './Modal/Modal.jsx';
import { ConfirmModal } from './ConfirmModal.jsx';
import { useFieldError } from './FieldError.jsx';
import { t } from '../i18n.js';

const dayNames = [t('월'), t('화'), t('수'), t('목'), t('금'), t('토'), t('일')];

export function getNextRunTime(schedule) {
  if (!schedule?.enabled || !schedule?.time || !schedule?.days?.length) return null;
  const [hour, min] = schedule.time.split(':').map(Number);
  if (isNaN(hour) || isNaN(min)) return null;
  const now = new Date();
  for (let offset = 0; offset < 8; offset++) {
    const candidate = new Date(now.getFullYear(), now.getMonth(), now.getDate() + offset, hour, min, 0, 0);
    const jsDay = candidate.getDay(); // 0: Sun, 1: Mon, ...
    const padDay = (jsDay + 6) % 7; // 0: Mon, ..., 6: Sun
    if (schedule.days.includes(padDay) && candidate.getTime() > now.getTime()) {
      return candidate;
    }
  }
  return null;
}

export function formatNextRun(schedule) {
  const next = getNextRunTime(schedule);
  if (!next) return schedule?.enabled ? t('예정 없음') : t('비활성화됨');
  const now = new Date();
  const diffSec = Math.max(0, Math.round((next.getTime() - now.getTime()) / 1000));
  const diffHours = Math.floor(diffSec / 3600);
  const diffMins = Math.floor((diffSec % 3600) / 60);
  if (diffHours < 24 && next.getDate() === now.getDate()) {
    return t('오늘 {0}:{1} ({2}시간 {3}분 후)', String(next.getHours()).padStart(2, '0'), String(next.getMinutes()).padStart(2, '0'), diffHours, diffMins);
  }
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  if (next.getDate() === tomorrow.getDate() && next.getMonth() === tomorrow.getMonth()) {
    return t('내일 {0}:{1}', String(next.getHours()).padStart(2, '0'), String(next.getMinutes()).padStart(2, '0'));
  }
  return t('{0}월 {1}일({2}) {3}:{4}', next.getMonth() + 1, next.getDate(), dayNames[(next.getDay() + 6) % 7], String(next.getHours()).padStart(2, '0'), String(next.getMinutes()).padStart(2, '0'));
}

export function SceneSettings({ scenes = [], services = [], groups = [], colors = [], colorNames = [], api, refresh, onError, onNotice = () => {} }) {
  const [sceneModal, setSceneModal] = useState(null); // null | { isNew: true } | scene
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(null);

  // Grouped members are not standalone pads
  const groupedIds = new Set(groups.flatMap(g => g.member_ids));
  const allPads = [
    ...services.filter(s => !groupedIds.has(s.id)),
    ...groups.map(g => ({ ...g, isGroup: true }))
  ];
  const padMap = new Map(allPads.map(p => [p.id, p]));

  // Scene save / delete
  async function saveScene(sceneData) {
    setBusy(true);
    try {
      const { id, ...values } = sceneData;
      if (id) {
        await api(`/scenes/${sceneData.id}`, { method: 'PUT', body: JSON.stringify(values) });
      } else {
        await api('/scenes', { method: 'POST', body: JSON.stringify(values) });
      }
      await refresh();
      setSceneModal(null);
      onNotice(t('흐름을 저장했습니다.'));
    } catch (e) {
      onError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function deleteScene(scene) {
    setBusy(true);
    try {
      await api(`/scenes/${scene.id}`, { method: 'DELETE' });
      await refresh();
      onNotice(t('흐름을 삭제했습니다.'));
    } catch (e) {
      onError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-3.5">
      {/* 1. Scenes Section */}
      <section className="settings-card vertical">
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div className="section-heading mr-auto min-w-[220px] flex-1">
            <Film size={22} />
            <div>
              <h2>{t('흐름 관리')}</h2>
              <p>{t('여러 패드를 지정한 순서대로 실행하거나 역순으로 정지하는 흐름을 구성합니다.')}</p>
            </div>
          </div>
          <button type="button" className="secondary min-h-8 px-[11px] py-1.5 text-[12px]" disabled={busy} onClick={() => setSceneModal({ name: '', color: colors[0] || '#10b981', pad_ids: [] })}>
            <Plus size={15} />{t('흐름 추가')}
          </button>
        </div>

        <div className="mt-2.5 flex flex-col gap-2">
          {scenes.length === 0 ? (
            <p>{t('등록된 흐름이 없습니다. 새 흐름을 추가해 보세요.')}</p>
          ) : (
            scenes.map(scene => {
              const scenePadNames = (scene.pad_ids || []).map(id => padMap.get(id)?.name || id).join(', ');
              return (
                <div className="flex items-center justify-between gap-3 rounded-lg border border-[#d4d9cc] bg-[rgba(127,127,127,0.06)] px-3 py-2.5" key={scene.id}>
                  <div className="flex min-w-0 flex-1 items-center gap-2.5">
                    <span className="size-3 shrink-0 rounded-full" style={{ backgroundColor: scene.color }} />
                    <div className="flex min-w-0 flex-col gap-0.5">
                      <strong>{scene.name}</strong>
                      <p className="truncate">{scenePadNames || t('지정된 패드 없음')}</p>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button type="button" className="secondary small-btn" disabled={busy} aria-label={t('{0} 흐름 편집', scene.name)} onClick={() => setSceneModal({ ...scene, pad_ids: [...(scene.pad_ids || [])] })}>
                      {t('편집')}
                    </button>
                    <button type="button" className="delete-button size-8" disabled={busy} aria-label={t('{0} 흐름 삭제', scene.name)} onClick={() => setDeleting(scene)}>
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </section>

      <ConfirmModal isOpen={!!deleting} title={t('흐름 삭제')} confirmLabel={t('삭제')} message={t("'{0}' 흐름을 삭제할까요?", deleting?.name)} onCancel={() => setDeleting(null)} onConfirm={() => { const scene = deleting; setDeleting(null); deleteScene(scene); }} />

      {/* Scene Edit Modal */}
      {sceneModal && (
        <SceneEditModal
          scene={sceneModal}
          allPads={allPads}
          colors={colors}
          colorNames={colorNames}
          busy={busy}
          onClose={() => setSceneModal(null)}
          onSave={saveScene}
        />
      )}

    </div>
  );
}

export function SceneEditModal({ scene, allPads, colors, colorNames, busy, onClose, onSave }) {
  const [name, setName] = useState(scene.name || '');
  const [color, setColor] = useState(scene.color || colors[0] || '#10b981');
  const [selectedIds, setSelectedIds] = useState(scene.pad_ids || []);
  const [discarding, setDiscarding] = useState(false);
  const fieldError = useFieldError();
  const dirty = name !== (scene.name || '') || color !== (scene.color || colors[0] || '#10b981') || selectedIds.join() !== (scene.pad_ids || []).join();
  const close = () => { if (dirty) setDiscarding(true); else onClose(); };

  const padMap = new Map(allPads.map(p => [p.id, p]));

  function togglePad(id) {
    if (selectedIds.includes(id)) {
      setSelectedIds(selectedIds.filter(x => x !== id));
    } else {
      setSelectedIds([...selectedIds, id]);
    }
  }

  function moveUp(index) {
    if (index <= 0) return;
    const next = [...selectedIds];
    [next[index - 1], next[index]] = [next[index], next[index - 1]];
    setSelectedIds(next);
  }

  function moveDown(index) {
    if (index >= selectedIds.length - 1) return;
    const next = [...selectedIds];
    [next[index + 1], next[index]] = [next[index], next[index + 1]];
    setSelectedIds(next);
  }

  function handleSubmit(e) {
    e.preventDefault();
    e.stopPropagation();
    if (!fieldError.validate(e.currentTarget)) return;
    onSave({
      ...(scene.id ? { id: scene.id } : {}),
      name: name.trim(),
      color,
      pad_ids: selectedIds
    });
  }

  return (
    <Modal isOpen onClose={close} closeOnOverlayClick={false} title={scene.id ? t('흐름 편집') : t('흐름 추가')} size="md">
      <form onSubmit={handleSubmit} className="flex flex-col gap-3.5" noValidate>
        <label>
          <span>{t('흐름 이름')}</span>
          <input required pattern=".*\S.*" maxLength={40} value={name} onChange={e => setName(e.target.value)} placeholder={t('예: 아침 출근')} autoFocus />
        </label>

        <fieldset className="color-field">
          <legend>{t('흐름 색상')}</legend>
          <div className="colors">
            {colors.map((c, i) => (
              <button
                type="button"
                key={c}
                className={color === c ? 'selected' : ''}
                style={{ '--color': c }}
                onClick={() => setColor(c)}
                aria-label={colorNames[i] || c}
                aria-pressed={color === c}
              />
            ))}
          </div>
        </fieldset>

        <div className="mt-1.5 flex flex-col gap-2">
          <h3>{t('실행할 패드 및 순서')}</h3>
          <p className="optional">{t('위에서 아래 순서로 순차 실행되며, 정지 시에는 역순으로 정지합니다.')}</p>

          {/* Selected Pads with Order Controls */}
          {selectedIds.length > 0 && (
            <div className="flex max-h-[180px] flex-col gap-1.5 overflow-y-auto py-1">
              {selectedIds.map((id, index) => {
                const pad = padMap.get(id);
                return (
                  <div className="flex items-center gap-2 rounded-md bg-[#dfe5d5] px-2.5 py-1.5" key={id}>
                    <span className="w-[18px] text-center text-[11px] text-muted">{index + 1}</span>
                    <span className="min-w-0 flex-1 truncate text-[13px] font-medium tracking-[-.3px]">{pad?.name || id}</span>
                    <div className="flex items-center gap-1">
                      <button type="button" className="tool-button size-8" disabled={index === 0} aria-label={t('{0} 순서 앞으로', pad?.name || id)} onClick={() => moveUp(index)}>
                        <ArrowUp size={14} />
                      </button>
                      <button type="button" className="tool-button size-8" disabled={index === selectedIds.length - 1} aria-label={t('{0} 순서 뒤로', pad?.name || id)} onClick={() => moveDown(index)}>
                        <ArrowDown size={14} />
                      </button>
                      <button type="button" className="delete-button size-8" aria-label={t('{0} 흐름에서 빼기', pad?.name || id)} onClick={() => togglePad(id)}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Available Pads Checkboxes */}
          <div className="mt-2.5">
            <h4 className="mb-1.5 text-[12px]">{t('패드 선택')}</h4>
            <div className="grid max-h-[140px] grid-cols-[repeat(auto-fill,minmax(130px,1fr))] gap-1.5 overflow-y-auto">
              {allPads.map(pad => (
                <label key={pad.id} className="flex-row items-center gap-1.5 rounded-md bg-[rgba(255,255,255,0.03)] px-2 py-1.5 text-[12px] cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(pad.id)}
                    onChange={() => togglePad(pad.id)}
                  />
                  <span>{pad.name}</span>
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="form-actions">
          <button type="button" className="secondary" disabled={busy} onClick={close}>
            {t('취소')}
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {t('저장')}
          </button>
        </div>
      </form>
      {fieldError.popover}
      <ConfirmModal isOpen={discarding} title={t('저장하지 않은 변경 사항')} confirmLabel={t('버리고 닫기')} message={t('저장하지 않은 변경 사항이 있어요. 버리고 닫을까요?')} onCancel={() => setDiscarding(false)} onConfirm={() => { setDiscarding(false); onClose(); }} />
    </Modal>
  );
}

export function ScheduleEditModal({ schedule, scenes, allPads, busy, onClose, onSave, sceneOnly = false }) {
  const [targetType, setTargetType] = useState(schedule.target_type || (scenes.length > 0 ? 'scene' : 'pad'));
  const [targetId, setTargetId] = useState(schedule.target_id || (targetType === 'scene' ? scenes[0]?.id : allPads[0]?.id) || '');
  const [action, setAction] = useState(schedule.action || 'start');
  const [time, setTime] = useState(schedule.time || '09:00');
  const [days, setDays] = useState(schedule.days || [0, 1, 2, 3, 4]);
  const [discarding, setDiscarding] = useState(false);
  const fieldError = useFieldError();
  const initial = useRef({ targetType, targetId, action, time, days: days.join() });
  const dirty = targetType !== initial.current.targetType || targetId !== initial.current.targetId || action !== initial.current.action || time !== initial.current.time || days.join() !== initial.current.days;
  const close = () => { if (dirty) setDiscarding(true); else onClose(); };

  function toggleDay(dayIndex) {
    if (days.includes(dayIndex)) {
      if (days.length === 1) return; // 하나 이상 유지
      setDays(days.filter(d => d !== dayIndex).sort((a, b) => a - b));
    } else {
      setDays([...days, dayIndex].sort((a, b) => a - b));
    }
  }

  function setPresetDays(preset) {
    if (preset === 'all') setDays([0, 1, 2, 3, 4, 5, 6]);
    else if (preset === 'weekdays') setDays([0, 1, 2, 3, 4]);
    else if (preset === 'weekend') setDays([5, 6]);
  }

  function handleSubmit(e) {
    e.preventDefault();
    e.stopPropagation();
    if (!fieldError.validate(e.currentTarget)) return;
    onSave({
      ...(schedule.id ? { id: schedule.id } : {}),
      target_type: targetType,
      target_id: targetId,
      action,
      time,
      days,
      enabled: schedule.enabled !== false
    });
  }

  return (
    <Modal isOpen onClose={close} closeOnOverlayClick={false} title={schedule.id ? t('예약 편집') : t('예약 추가')} size="md">
      <form onSubmit={handleSubmit} className="flex flex-col gap-3.5" noValidate>
        <label>
          <span>{t('대상 종류')}</span>
          <SelectControl
            aria-label={t('대상 종류')}
            value={targetType}
            onChange={e => {
              const nextType = e.target.value;
              setTargetType(nextType);
              setTargetId(nextType === 'scene' ? scenes[0]?.id || '' : allPads[0]?.id || '');
            }}
          >
            {scenes.length > 0 && <option value="scene">{t('흐름')}</option>}
            {!sceneOnly && <option value="pad">{t('패드')}</option>}
          </SelectControl>
        </label>

        <label>
          <span>{t('실행 대상')}</span>
          <SelectControl aria-label={t('실행 대상')} required value={targetId} onChange={e => setTargetId(e.target.value)}>
            {targetType === 'scene'
              ? scenes.map(s => <option value={s.id} key={s.id}>{s.name}</option>)
              : allPads.map(p => <option value={p.id} key={p.id}>{p.name}</option>)}
          </SelectControl>
        </label>

        <label>
          <span>{t('동작')}</span>
          <SelectControl value={action} onChange={e => setAction(e.target.value)}>
            <option value="start">{t('시작')}</option>
            <option value="stop">{t('정지')}</option>
          </SelectControl>
        </label>

        <label>
          <span>{t('시각')}</span>
          <input
            type="time"
            required
            value={time}
            onChange={e => setTime(e.target.value)}
          />
        </label>

        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between text-[13px]">
            <span>{t('실행 요일')}</span>
            <div className="flex gap-1">
              <button type="button" className="secondary small-btn" onClick={() => setPresetDays('all')}>{t('매일')}</button>
              <button type="button" className="secondary small-btn" onClick={() => setPresetDays('weekdays')}>{t('평일')}</button>
              <button type="button" className="secondary small-btn" onClick={() => setPresetDays('weekend')}>{t('주말')}</button>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {dayNames.map((dName, idx) => (
              <label key={idx} className={`inline-flex h-8 w-9 cursor-pointer select-none items-center justify-center rounded-md border text-[12px] [&>input]:hidden ${days.includes(idx) ? 'border-[#829b73] bg-[#829b73] font-semibold text-[#fffdf3]' : 'border-[#b9c0ad] bg-transparent text-[#3f4d3b]'}`}>
                <input
                  type="checkbox"
                  checked={days.includes(idx)}
                  onChange={() => toggleDay(idx)}
                />
                <span>{dName}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="form-actions">
          <button type="button" className="secondary" disabled={busy} onClick={close}>
            {t('취소')}
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {t('저장')}
          </button>
        </div>
      </form>
      {fieldError.popover}
      <ConfirmModal isOpen={discarding} title={t('저장하지 않은 변경 사항')} confirmLabel={t('버리고 닫기')} message={t('저장하지 않은 변경 사항이 있어요. 버리고 닫을까요?')} onCancel={() => setDiscarding(false)} onConfirm={() => { setDiscarding(false); onClose(); }} />
    </Modal>
  );
}
