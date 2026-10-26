import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { CircleAlert, CircleCheck, X } from 'lucide-react';
import { t } from '../i18n.js';

// Success notices close on their own; failures stay longer and can offer a retry. Hovering or focusing pauses the timer.
function ToastItem({ toast, onClose }) {
  const timer = useRef(null);
  const start = () => { clearTimeout(timer.current); timer.current = setTimeout(onClose, toast.kind === 'error' ? 8000 : 4000); };
  const pause = () => clearTimeout(timer.current);
  useEffect(() => { start(); return pause; }, [toast.id]);
  const error = toast.kind === 'error';
  const Icon = error ? CircleAlert : CircleCheck;
  return <div data-toast={toast.kind} role={error ? 'alert' : 'status'} onPointerEnter={pause} onPointerLeave={start} onFocus={pause} onBlur={start}
    className={`pointer-events-auto flex w-[min(380px,calc(100vw-32px))] items-center gap-2.5 rounded-md border py-2.5 pr-2.5 pl-3.5 text-[13px] leading-normal text-ink-strong shadow-[0_10px_30px_#34442b2e] max-tablet:w-auto ${error ? 'border-danger-line bg-[#fbf1ef]' : 'border-line bg-raised'}`}>
    <Icon size={16} aria-hidden="true" className={error ? 'text-danger-ink' : 'text-ok'} />
    <p className="min-w-0 flex-1 whitespace-pre-wrap wrap-anywhere">{toast.message}</p>
    {toast.action && <button type="button" className="min-h-8 whitespace-nowrap rounded border border-[#bbc2ad] bg-[#f0eee4] px-2.5 text-[12px] font-semibold text-[#3f4d3b] hover:bg-hover" onClick={() => { onClose(); toast.action.run(); }}>{toast.action.label}</button>}
    <button type="button" className="size-8 rounded border-0 bg-transparent p-0 text-muted hover:bg-[#e4e8dc] hover:text-ink-strong" aria-label={t('알림 닫기')} onClick={onClose}><X size={14} /></button>
  </div>;
}

export function Toaster({ toasts, onClose }) {
  return createPortal(<div className="pointer-events-none fixed right-4 bottom-4 z-[2300] flex max-w-[calc(100vw-32px)] flex-col items-end gap-2 max-tablet:inset-x-3 max-tablet:bottom-3 max-tablet:items-stretch">
    {toasts.map(toast => <ToastItem key={toast.id} toast={toast} onClose={() => onClose(toast.id)} />)}
  </div>, document.body);
}
