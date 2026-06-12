import type { ReactNode } from 'react';
import './Panel.css';

export interface PanelProps {
  /** Title rendered in a gap in the top dashed border, in amber. */
  title?: string;
  children: ReactNode;
  className?: string;
}

/**
 * Dashed-chrome container with a title-in-border treatment, as in the
 * mock's "Why agents do better with Lore" box. Implemented with
 * fieldset/legend so the border gap is real and works on any surface.
 */
export function Panel({ title, children, className }: PanelProps) {
  return (
    <fieldset className={`lore-panel${className ? ` ${className}` : ''}`}>
      {title ? <legend className="lore-panel__title">{title}</legend> : null}
      <div className="lore-panel__body">{children}</div>
    </fieldset>
  );
}
