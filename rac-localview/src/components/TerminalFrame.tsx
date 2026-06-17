import type { ReactNode } from 'react';
import './TerminalFrame.css';

export interface TerminalFrameProps {
  /** Title bar text, e.g. "Lore — CLOSED BETA". */
  title: string;
  children: ReactNode;
  className?: string;
}

/**
 * Terminal-window chrome: dashed outer border, a title bar with
 * macOS-style traffic lights (small semantic-coloured dots) and amber
 * title text, then the framed content.
 */
export function TerminalFrame({ title, children, className }: TerminalFrameProps) {
  return (
    <section className={`lore-terminal${className ? ` ${className}` : ''}`}>
      <header className="lore-terminal__bar">
        <span className="lore-terminal__lights" aria-hidden="true">
          <i className="lore-terminal__light lore-terminal__light--close" />
          <i className="lore-terminal__light lore-terminal__light--min" />
          <i className="lore-terminal__light lore-terminal__light--max" />
        </span>
        <span className="lore-terminal__title">{title}</span>
      </header>
      <div className="lore-terminal__body">{children}</div>
    </section>
  );
}
