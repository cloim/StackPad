import React, { cloneElement, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

const GAP = 6;
const EDGE = 8;

// Shows supplementary text on mouse hover and keyboard focus. The trigger keeps its own accessible name;
// the tooltip only describes it. It renders in a portal and flips or shifts to stay inside the window.
export function Tooltip({ content, children, side = 'bottom' }) {
  const id = useId();
  const anchor = useRef(null);
  const bubble = useRef(null);
  const [open, setOpen] = useState(false);
  const [style, setStyle] = useState(null);

  useLayoutEffect(() => {
    if (!open) { setStyle(null); return; }
    const place = () => {
      if (!anchor.current || !bubble.current) return;
      const a = anchor.current.getBoundingClientRect();
      const b = bubble.current.getBoundingClientRect();
      const below = a.bottom + GAP + b.height <= window.innerHeight - EDGE;
      const above = a.top - GAP - b.height >= EDGE;
      const useBelow = side === 'bottom' ? below || !above : !above && below;
      const top = useBelow ? a.bottom + GAP : a.top - GAP - b.height;
      const left = Math.min(window.innerWidth - EDGE - b.width, Math.max(EDGE, a.left + a.width / 2 - b.width / 2));
      setStyle({ top: Math.max(EDGE, top), left });
    };
    place();
    const close = event => { if (event.key === 'Escape') setOpen(false); };
    window.addEventListener('scroll', place, true);
    window.addEventListener('resize', place);
    document.addEventListener('keydown', close);
    return () => { window.removeEventListener('scroll', place, true); window.removeEventListener('resize', place); document.removeEventListener('keydown', close); };
  }, [open, side, content]);

  if (!content) return children;
  const props = children.props;
  const chain = (own, next) => event => { own?.(event); next(event); };
  return <>
    {cloneElement(children, {
      ref: node => {
        anchor.current = node;
        if (typeof props.ref === 'function') props.ref(node); else if (props.ref) props.ref.current = node;
      },
      'aria-describedby': open ? id : props['aria-describedby'],
      onPointerEnter: chain(props.onPointerEnter, event => { if (event.pointerType === 'mouse') setOpen(true); }),
      onPointerLeave: chain(props.onPointerLeave, () => setOpen(false)),
      onPointerDown: chain(props.onPointerDown, () => setOpen(false)),
      onFocus: chain(props.onFocus, event => { if (event.currentTarget.matches(':focus-visible')) setOpen(true); }),
      onBlur: chain(props.onBlur, () => setOpen(false)),
    })}
    {open && createPortal(<div ref={bubble} id={id} role="tooltip" className="pointer-events-none fixed z-[2400] max-w-[280px] whitespace-pre-wrap wrap-anywhere rounded-md bg-tooltip px-2.5 py-1.5 text-[12px] leading-[1.45] text-raised shadow-[0_6px_18px_#2b352533]" data-ui-audit-overlay style={style || { top: 0, left: 0, visibility: 'hidden' }}>{content}</div>, document.body)}
  </>;
}
