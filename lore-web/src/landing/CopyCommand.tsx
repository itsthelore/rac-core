import { useEffect, useRef, useState } from 'react';

export interface CopyCommandProps {
  command: string;
}

/**
 * A real, copyable command: a code element plus a keyboard-accessible
 * copy button. Uses navigator.clipboard, falling back to selecting the
 * text so the user can copy manually; either way the outcome is
 * announced to screen readers via a visually hidden live region.
 */
export function CopyCommand({ command }: CopyCommandProps) {
  const codeRef = useRef<HTMLElement>(null);
  const timerRef = useRef<number | undefined>(undefined);
  const [copied, setCopied] = useState(false);
  const [status, setStatus] = useState('');

  useEffect(() => () => window.clearTimeout(timerRef.current), []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setStatus('Command copied to clipboard.');
    } catch {
      // Clipboard unavailable (permissions, insecure context): select
      // the command text so a manual Ctrl+C still works.
      const node = codeRef.current;
      const selection = window.getSelection();
      if (node && selection) {
        const range = document.createRange();
        range.selectNodeContents(node);
        selection.removeAllRanges();
        selection.addRange(range);
        setStatus('Clipboard unavailable — command selected; press Ctrl+C to copy.');
      } else {
        setStatus('Copy failed.');
      }
    }
    window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      setCopied(false);
      setStatus('');
    }, 2000);
  }

  return (
    <span className="copy-cmd">
      <code ref={codeRef} className="copy-cmd__code">
        {command}
      </code>{' '}
      <button
        type="button"
        className="copy-cmd__button"
        onClick={copy}
        aria-label={`Copy command: ${command}`}
      >
        {copied ? 'copied' : 'copy'}
      </button>
      <span className="sr-only" role="status" aria-live="polite">
        {status}
      </span>
    </span>
  );
}
