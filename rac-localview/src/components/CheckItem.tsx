import type { ReactNode } from 'react';
import './CheckItem.css';

export interface CheckItemProps {
  children: ReactNode;
  className?: string;
}

/**
 * Green `[✓]` checklist line, as in the "Why agents do better with
 * Lore" panel. Green is semantic (pass/check) — never decorative.
 */
export function CheckItem({ children, className }: CheckItemProps) {
  return (
    <p className={`lore-check${className ? ` ${className}` : ''}`}>
      <span className="lore-check__glyph" aria-hidden="true">
        [{'✓'}]
      </span>{' '}
      <span className="lore-check__text">{children}</span>
    </p>
  );
}
