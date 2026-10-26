import React, { useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Calendar, Clock, Film, GripVertical, Play, Plus, Power, Square, Trash2 } from 'lucide-react';
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

export function SceneSettings({ scenes = [], schedules = [], services = [], groups = [], colors = [], colorNames = [], api, refresh, onError, onNotice }) {
  const [sceneModal, setSceneModal] = useState(null); // null | { isNew: true } | scene
  const [scheduleModal, setScheduleModal] = useState(null); // null | { isNew: true } | schedule
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(null); // null | { scene } | { schedule, name }

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
      if (sceneData.id) {
        await api(`/scenes/${sceneData.id}`, { method: 'PUT', body: JSON.stringify(sceneData) });
      } else {
        await api('/scenes', { method: 'POST', body: JSON.stringify(sceneData) });
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

  // Schedule save / delete / toggle
  async function saveSchedule(scheduleData) {
    setBusy(true);
    try {
      if (scheduleData.id) {
        await api(`/schedules/${scheduleData.id}`, { method: 'PUT', body: JSON.stringify(scheduleData) });
      } else {
        await api('/schedules', { method: 'POST', body: JSON.stringify(scheduleData) });
      }
      await refresh();
      setScheduleModal(null);
      onNotice(t('예약을 저장했습니다.'));
    } catch (e) {
      onError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function deleteSchedule(schedule) {
    setBusy(true);
    try {
      await api(`/schedules/${schedule.id}`, { method: 'DELETE' });
      await refresh();
      onNotice(t('예약을 삭제했습니다.'));
    } catch (e) {
      onError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleSchedule(schedule, enabled) {
    setBusy(true);
    try {
      await api(`/schedules/${schedule.id}`, { method: 'PUT', body: JSON.stringify({ ...schedule, enabled }) });
      await refresh();
    } catch (e) {
      onError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="scene-settings-container">
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
          <button className="secondary min-h-8 px-[11px] py-1.5 text-[12px]" disabled={busy} onClick={() => setSceneModal({ name: '', color: colors[0] || '#10b981', pad_ids: [] })}>
            <Plus size={15} />{t('흐름 추가')}
          </button>
        </div>

        <div className="scene-list">
          {scenes.length === 0 ? (
            <p className="optional empty-hint">{t('등록된 흐름이 없습니다. 새 흐름을 추가해 보세요.')}</p>
          ) : (
            scenes.map(scene => {
              const scenePadNames = (scene.pad_ids || []).map(id => padMap.get(id)?.name || id).join(', ');
              return (
                <div className="scene-item" key={scene.id}>
                  <div className="scene-info">
                    <span className="scene-color-dot" style={{ backgroundColor: scene.color }} />
                    <div className="scene-details">
                      <strong>{scene.name}</strong>
                      <p className="scene-pads optional">{scenePadNames || t('지정된 패드 없음')}</p>
                    </div>
                  </div>
                  <div className="scene-item-actions">
                    <button className="secondary small-btn" disabled={busy} aria-label={t('{0} 흐름 편집', scene.name)} onClick={() => setSceneModal({ ...scene, pad_ids: [...(scene.pad_ids || [])] })}>
                      {t('편집')}
                    </button>
                    <button className="delete-button size-8" disabled={busy} aria-label={t('{0} 흐름 삭제', scene.name)} onClick={() => setDeleting({ scene })}>
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </section>

      {/* 2. Schedules Section */}
      <section className="settings-card vertical">
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div className="section-heading mr-auto min-w-[220px] flex-1">
            <Calendar size={22} />
            <div>
              <h2>{t('예약 관리')}</h2>
              <p>{t('지정한 시각과 요일에 흐름이나 패드를 자동으로 시작하거나 정지합니다.')}</p>
            </div>
          </div>
          <button className="secondary min-h-8 px-[11px] py-1.5 text-[12px]" disabled={busy || (scenes.length === 0 && allPads.length === 0)} onClick={() => setScheduleModal({
            target_type: scenes.length > 0 ? 'scene' : 'pad',
            target_id: scenes[0]?.id || allPads[0]?.id || '',
            action: 'start',
            time: '09:00',
            days: [0, 1, 2, 3, 4],
            enabled: true
          })}>
            <Plus size={15} />{t('예약 추가')}
          </button>
        </div>

        <div className="schedule-list">
          {schedules.length === 0 ? (
            <p className="optional empty-hint">{t('등록된 예약이 없습니다. 새 일정을 추가해 보세요.')}</p>
          ) : (
            schedules.map(sch => {
              const targetName = sch.target_type === 'scene'
                ? scenes.find(s => s.id === sch.target_id)?.name || sch.target_id
                : padMap.get(sch.target_id)?.name || sch.target_id;
              const daysText = (sch.days || []).length === 7
                ? t('매일')
                : (sch.days || []).length === 5 && [0, 1, 2, 3, 4].every(d => sch.days.includes(d))
                ? t('평일')
                : (sch.days || []).map(d => dayNames[d]).join(', ');
              const nextRun = formatNextRun(sch);

              return (
                <div className={`schedule-item ${!sch.enabled ? 'disabled' : ''}`} key={sch.id}>
                  <div className="schedule-info">
                    <div className="schedule-target">
                      <span className={`schedule-badge ${sch.target_type}`}>
                        {sch.target_type === 'scene' ? t('흐름') : t('패드')}
                      </span>
                      <strong>{targetName}</strong>
                      <span className={`schedule-action ${sch.action}`}>
                        {sch.action === 'start' ? t('시작') : t('정지')}
                      </span>
                    </div>
                    <div className="schedule-timing optional">
                      <Clock size={13} />
                      <span>{sch.time}</span>
                      <span className="dot-sep">|</span>
                      <span>{daysText}</span>
                      <span className="dot-sep">|</span>
                      <span className="next-run">{nextRun}</span>
                    </div>
                  </div>
                  <div className="schedule-item-actions">
                    <button
                      type="button"
                      className={`switch ${sch.enabled ? 'on' : ''}`}
                      role="switch"
                      aria-checked={sch.enabled}
                      aria-label={t('{0} 예약 활성화', targetName)}
                      disabled={busy}
                      onClick={() => toggleSchedule(sch, !sch.enabled)}
                    >
                      <span />
                    </button>
                    <button className="secondary small-btn" disabled={busy} aria-label={t('{0} 예약 편집', targetName)} onClick={() => setScheduleModal({ ...sch, days: [...(sch.days || [])] })}>
                      {t('편집')}
                    </button>
                    <button className="delete-button size-8" disabled={busy} aria-label={t('{0} 예약 삭제', targetName)} onClick={() => setDeleting({ schedule: sch, name: targetName })}>
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </section>

      <ConfirmModal isOpen={!!deleting} title={deleting?.scene ? t('흐름 삭제') : t('예약 삭제')} confirmLabel={t('삭제')} message={deleting?.scene ? t("'{0}' 흐름을 삭제할까요?", deleting.scene.name) : t("'{0}' 예약을 삭제할까요?", deleting?.name)} onCancel={() => setDeleting(null)} onConfirm={() => { const target = deleting; setDeleting(null); if (target.scene) deleteScene(target.scene); else deleteSchedule(target.schedule); }} />

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

      {/* Schedule Edit Modal */}
      {scheduleModal && (
        <ScheduleEditModal
          schedule={scheduleModal}
          scenes={scenes}
          allPads={allPads}
          busy={busy}
          onClose={() => setScheduleModal(null)}
          onSave={saveSchedule}
        />
      )}
    </div>
  );
}

function SceneEditModal({ scene, allPads, colors, colorNames, busy, onClose, onSave }) {
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
      <form onSubmit={handleSubmit} className="scene-form" noValidate>
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

        <div className="scene-pad-selection">
          <h3>{t('실행할 패드 및 순서')}</h3>
          <p className="optional">{t('위에서 아래 순서로 순차 실행되며, 정지 시에는 역순으로 정지합니다.')}</p>

          {/* Selected Pads with Order Controls */}
          {selectedIds.length > 0 && (
            <div className="selected-pads-list">
              {selectedIds.map((id, index) => {
                const pad = padMap.get(id);
                return (
                  <div className="ordered-pad-row" key={id}>
                    <span className="order-num">{index + 1}</span>
                    <span className="pad-name">{pad?.name || id}</span>
                    <div className="order-actions">
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
          <div className="available-pads-section">
            <h4>{t('패드 선택')}</h4>
            <div className="available-pads-grid">
              {allPads.map(pad => (
                <label key={pad.id} className="pad-checkbox-label">
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

function ScheduleEditModal({ schedule, scenes, allPads, busy, onClose, onSave }) {
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
      <form onSubmit={handleSubmit} className="schedule-form" noValidate>
        <label>
          <span>{t('대상 종류')}</span>
          <SelectControl
            value={targetType}
            onChange={e => {
              const nextType = e.target.value;
              setTargetType(nextType);
              setTargetId(nextType === 'scene' ? scenes[0]?.id || '' : allPads[0]?.id || '');
            }}
          >
            {scenes.length > 0 && <option value="scene">{t('흐름')}</option>}
            <option value="pad">{t('패드')}</option>
          </SelectControl>
        </label>

        <label>
          <span>{t('실행 대상')}</span>
          <SelectControl required value={targetId} onChange={e => setTargetId(e.target.value)}>
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

        <div className="days-selection">
          <div className="days-head">
            <span>{t('실행 요일')}</span>
            <div className="days-presets">
              <button type="button" className="secondary small-btn" onClick={() => setPresetDays('all')}>{t('매일')}</button>
              <button type="button" className="secondary small-btn" onClick={() => setPresetDays('weekdays')}>{t('평일')}</button>
              <button type="button" className="secondary small-btn" onClick={() => setPresetDays('weekend')}>{t('주말')}</button>
            </div>
          </div>
          <div className="days-checkboxes">
            {dayNames.map((dName, idx) => (
              <label key={idx} className={`day-chip ${days.includes(idx) ? 'active' : ''}`}>
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
