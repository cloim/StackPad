import React from 'react';
import { ChevronDown } from 'lucide-react';

export function SelectControl({ children, ...props }) {
  return <span className="relative inline-flex h-10 w-full min-w-0 items-center"><select {...props} className="h-10 min-h-10 w-full min-w-0 appearance-none rounded-[7px] border border-[#c1c7b5] bg-field py-0 pr-[34px] pl-3 text-[#444e40] focus-visible:border-[#7c9a83] focus-visible:outline-2 focus-visible:outline-[#8caa8a66]">{children}</select><ChevronDown size={15} aria-hidden="true" className="pointer-events-none absolute right-[11px] text-muted" /></span>;
}
