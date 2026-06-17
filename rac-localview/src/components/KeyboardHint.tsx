import './KeyboardHint.css';

export interface KeyboardHintProps {
  /** Keys in press order, e.g. ['Ctrl', 'K']. */
  keys: string[];
  className?: string;
}

/**
 * Small bordered key caps. Solid border — the interactive-affordance
 * style — as opposed to the dashed container chrome.
 */
export function KeyboardHint({ keys, className }: KeyboardHintProps) {
  return (
    <span className={`lore-kbd${className ? ` ${className}` : ''}`}>
      {keys.map((key, i) => (
        <kbd className="lore-kbd__key" key={`${key}-${i}`}>
          {key}
        </kbd>
      ))}
    </span>
  );
}
