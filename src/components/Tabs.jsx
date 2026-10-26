import React from 'react';

// "keys" draws each tab as a raised key for the pad set row above the deck; the default is a segmented control.
const styles = {
  default: {
    list: 'flex max-w-full shrink-0 gap-1 overflow-x-auto rounded-[10px] border border-[rgba(127,127,127,.14)] bg-[rgba(127,127,127,.07)] p-1',
    tab: 'group inline-flex shrink-0 cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap rounded-[7px] border-0 bg-transparent px-[13px] py-2 text-[12px] text-[#717b68] focus-visible:outline-focus focus-visible:-outline-offset-2 aria-selected:bg-raised aria-selected:font-bold aria-selected:text-[#33452f] aria-selected:shadow-[0_1px_3px_#4a553f38,inset_0_0_0_1px_#b2bda7] max-[480px]:px-2.5',
  },
  keys: {
    list: 'flex max-w-full shrink-0 gap-2.5 overflow-x-auto p-1 max-tablet:gap-[7px] max-tablet:p-0.5',
    tab: "group inline-flex min-w-[88px] shrink-0 cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap rounded border border-line-strong bg-[linear-gradient(#efeee4,#e9e7dc)] px-4 py-2.5 text-[12px] text-[#555c51] shadow-[inset_0_1px_0_#fffdf0,0_1px_1px_#59604b19,0_1px_0_#bfc1b4] before:h-[3px] before:w-2 before:shrink-0 before:rounded-[1px] before:bg-[#bbbeb1] before:content-[''] focus-visible:outline-focus focus-visible:-outline-offset-2 aria-selected:border-[#a9b59f] aria-selected:bg-[#cfd8c5] aria-selected:bg-none aria-selected:font-bold aria-selected:text-[#33452f] aria-selected:shadow-[inset_0_1px_3px_#4f5c4433,0_1px_0_#fffdf2] aria-selected:before:bg-live aria-selected:before:shadow-[0_0_4px_#35d982cc,0_0_9px_#35d98266] max-tablet:min-w-[66px] max-tablet:px-2.5 max-tablet:py-2 max-tablet:text-[11px]",
  },
};

export function Tabs({ label, tabs, value, onChange, prefix, variant = 'default' }) {
  const style = styles[variant];
  return <div className={style.list} role="tablist" aria-label={label} onKeyDown={event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const index = tabs.findIndex(tab => tab.id === value);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    onChange(tabs[next].id);
    event.currentTarget.querySelectorAll('[role="tab"]')[next]?.focus();
  }}>{tabs.map(tab => <button key={tab.id} type="button" role="tab" className={style.tab} id={`${prefix}-tab-${tab.id}`} aria-controls={`${prefix}-panel`} aria-selected={value === tab.id} tabIndex={value === tab.id ? 0 : -1} onClick={() => onChange(tab.id)}>{tab.name}{tab.badge !== undefined && tab.badge !== null && <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-[rgba(127,127,127,.2)] px-[5px] text-[10px] leading-none font-semibold tabular-nums group-aria-selected:bg-[#becdb7] group-aria-selected:text-[#445c46]" aria-hidden="true">{tab.badge}</span>}</button>)}</div>;
}
