import React from 'react';
import { ChevronDown } from 'lucide-react';

export function SelectControl({ children, ...props }) {
  return <span className="select-control"><select {...props}>{children}</select><ChevronDown size={15} aria-hidden="true" /></span>;
}
