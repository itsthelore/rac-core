import type { ReactNode } from 'react';
import './Prompt.css';

export type PromptProps =
  | {
      /** MCP-tool style: teal `>` glyph, bold teal command, muted description. */
      variant?: 'tool';
      command: string;
      description?: string;
    }
  | {
      /** Numbered next-step style: amber `↳ N /` prefix, plain text. */
      variant: 'next';
      index: number;
      children: ReactNode;
    };

/**
 * The `>` list item from the mock's right rail, plus the `↳ N /`
 * numbered variant from "What would you like to do next".
 */
export function Prompt(props: PromptProps) {
  if (props.variant === 'next') {
    return (
      <p className="lore-prompt lore-prompt--next">
        <span className="lore-prompt__num" aria-hidden="true">
          {'↳'} {props.index} /
        </span>{' '}
        <span className="lore-prompt__text">{props.children}</span>
      </p>
    );
  }
  return (
    <p className="lore-prompt lore-prompt--tool">
      <span className="lore-prompt__glyph" aria-hidden="true">
        {'>'}
      </span>{' '}
      <span className="lore-prompt__command">{props.command}</span>
      {props.description ? (
        <>
          {' '}
          <span className="lore-prompt__desc">{props.description}</span>
        </>
      ) : null}
    </p>
  );
}
