import React, { useState } from 'react';
import { Modal } from './Modal/Modal.jsx';
import { SelectControl } from './SelectControl.jsx';
import { t } from '../i18n.js';

// Every src/widgets/<id>.jsx is a widget; see src/widgets/README.md. Files starting with _ are shared helpers.
const modules = import.meta.glob('../widgets/[a-z0-9]*.jsx', { eager: true });
export const widgetPlugins = Object.entries(modules)
  .map(([path, module]) => ({ id: path.split('/').pop().replace(/\.jsx$/, ''), ...module.default }))
  .filter(plugin => /^[a-z0-9][a-z0-9-]{0,39}$/.test(plugin.id) && plugin.View)
  .sort((a, b) => (a.order ?? Infinity) - (b.order ?? Infinity) || a.id.localeCompare(b.id));
export const defaultWidget = 'ai-usage';
const plugin = id => widgetPlugins.find(item => item.id === id);
const pluginName = item => typeof item.name === 'function' ? item.name() : item.name || item.id;

/** The widget a padset shows: absent means the default, null means none. */
export const padsetWidget = padset => padset && 'widget' in padset ? padset.widget : defaultWidget;

export function WidgetArea({ widget, api, settings }) {
  const current = plugin(widget);
  if (!current) return null;
  const { View } = current;
  return <div data-widget-area={current.id} className="min-w-0 shrink-0 empty:hidden"><View api={api} settings={settings} /></div>;
}

export function WidgetEditor({ padset, widget, api, onSaved, onClose, onError }) {
  const initial = plugin(widget) ? widget : '';
  const [draft, setDraft] = useState(initial);
  const [busy, setBusy] = useState(false);
  const close = () => { if (!busy) onClose(); };

  async function save() {
    setBusy(true);
    try {
      const data = await api(`/padsets/${padset.id}/widget`, { method: 'PUT', body: JSON.stringify({ widget: draft || null }) });
      onSaved(padset.id, data.widget);
      onClose();
    } catch (error) { onError(error.message); }
    finally { setBusy(false); }
  }

  return <Modal isOpen title={t('{0} 위젯 영역 설정', padset.name)} onClose={close} footer={<>
    <button type="button" className="secondary" onClick={close} disabled={busy}>{t('취소')}</button>
    <button type="button" className="primary" onClick={save} disabled={busy || draft === initial}>{t('저장')}</button>
  </>}>
    <label className="flex flex-col gap-1.5">{t('표시할 위젯')}
      <SelectControl aria-label={t('표시할 위젯')} value={draft} disabled={busy} onChange={event => setDraft(event.target.value)}>
        <option value="">{t('표시 안 함')}</option>
        {widgetPlugins.map(item => <option key={item.id} value={item.id}>{pluginName(item)}</option>)}
      </SelectControl>
    </label>
  </Modal>;
}
