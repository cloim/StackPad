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
  const Icon = toast.kind === 'error' ? CircleAlert : CircleCheck;
  return <div className={`toast ${toast.kind}`} role={toast.kind === 'error' ? 'alert' : 'status'} onPointerEnter={pause} onPointerLeave={start} onFocus={pause} onBlur={start}>
    <Icon size={16} aria-hidden="true" />
    <p>{toast.message}</p>
    {toast.action && <button type="button" className="toast-action" onClick={() => { onClose(); toast.action.run(); }}>{toast.action.label}</button>}
    <button type="button" className="toast-close" aria-label={t('알림 닫기')} onClick={onClose}><X size={14} /></button>
  </div>;
}

export function Toaster({ toasts, onClose }) {
  return createPortal(<div className="toast-stack">{toasts.map(toast => <ToastItem key={toast.id} toast={toast} onClose={() => onClose(toast.id)} />)}</div>, document.body);
}
