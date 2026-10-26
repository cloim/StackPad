import React, { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { CircleAlert } from 'lucide-react';

// Field-anchored validation: the first invalid field gets aria-invalid and a popover that floats under it
// without pushing the form. The popover updates as the user types and closes once the field is valid.
export function useFieldError() {
  const [error, setError] = useState(null);
  const id = useId();

  const validate = useCallback(form => {
    const field = form.querySelector(':invalid:not(fieldset)');
    if (!field) { setError(null); return true; }
    setError({ field, message: field.validationMessage });
    // A field on a hidden tab becomes focusable after the caller switches tabs in the same event.
    requestAnimationFrame(() => field.focus());
    return false;
  }, []);

  useEffect(() => {
    if (!error) return;
    const { field } = error;
    field.setAttribute('aria-invalid', 'true');
    field.setAttribute('aria-describedby', id);
    // Re-check after React handles the same input event; rendering first would reset the controlled value.
    const update = () => requestAnimationFrame(() => setError(field.checkValidity() ? null : { field, message: field.validationMessage }));
    field.addEventListener('input', update);
    field.addEventListener('change', update);
    return () => {
      field.removeEventListener('input', update);
      field.removeEventListener('change', update);
      field.removeAttribute('aria-invalid');
      field.removeAttribute('aria-describedby');
    };
  }, [error?.field, id]);

  const popover = error ? <FieldErrorPopover id={id} field={error.field} message={error.message} /> : null;
  return { validate, popover };
}

function FieldErrorPopover({ id, field, message }) {
  const ref = useRef(null);
  const [style, setStyle] = useState({ visibility: 'hidden', top: 0, left: 0 });
  useLayoutEffect(() => {
    const place = () => {
      const a = field.getBoundingClientRect();
      const b = ref.current?.getBoundingClientRect();
      if (!b) return;
      const hidden = !a.width && !a.height;
      const top = a.bottom + 6 + b.height > window.innerHeight - 8 ? a.top - 6 - b.height : a.bottom + 6;
      setStyle({ top, left: Math.max(8, Math.min(a.left, window.innerWidth - 8 - b.width)), visibility: hidden ? 'hidden' : 'visible' });
    };
    place();
    window.addEventListener('scroll', place, true);
    window.addEventListener('resize', place);
    const observer = new ResizeObserver(place);
    observer.observe(field);
    return () => { window.removeEventListener('scroll', place, true); window.removeEventListener('resize', place); observer.disconnect(); };
  }, [field, message]);
  return createPortal(<div ref={ref} id={id} role="alert" data-field-error className="fixed z-[2200] flex max-w-[min(360px,calc(100vw-16px))] items-start gap-1.5 rounded-md border border-danger-line bg-danger-soft px-2.5 py-[7px] text-[12px] leading-[1.45] text-[#8f3540] shadow-[0_6px_18px_#34442b24]" data-ui-audit-overlay style={style}><CircleAlert size={14} aria-hidden="true" className="mt-0.5" />{message}</div>, document.body);
}
