import React from 'react';

export function Tabs({ label, tabs, value, onChange, prefix }) {
  return <div className="category-tabs" role="tablist" aria-label={label} onKeyDown={event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const index = tabs.findIndex(tab => tab.id === value);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    onChange(tabs[next].id);
    event.currentTarget.querySelectorAll('[role="tab"]')[next]?.focus();
  }}>{tabs.map(tab => <button key={tab.id} type="button" role="tab" id={`${prefix}-tab-${tab.id}`} aria-controls={`${prefix}-panel`} aria-selected={value === tab.id} tabIndex={value === tab.id ? 0 : -1} onClick={() => onChange(tab.id)}>{tab.name}{tab.badge !== undefined && tab.badge !== null && <span className="tab-badge" aria-hidden="true">{tab.badge}</span>}</button>)}</div>;
}
