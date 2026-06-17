import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import './CommandPalette.css';

export interface CommandPaletteItem {
  /** Visible name, e.g. a section, document or command. */
  label: string;
  /** Muted annotation shown after the label. */
  hint?: string;
  /** Invoked on Enter or click. Navigation/callback only — not a chat. */
  action: () => void;
}

export interface CommandPaletteProps {
  items: CommandPaletteItem[];
  /** Prompt prefix shown before the input. Default: "lore-$". */
  prompt?: string;
  placeholder?: string;
  /** Pin the bar to the bottom of the viewport. Default: false (inline). */
  fixed?: boolean;
  /** Accessible name for the combobox. */
  ariaLabel?: string;
}

const DEFAULT_PLACEHOLDER = '# type to navigate — sections, docs, commands';

/**
 * The `lore-$` footer prompt bar from the mock, as a working command
 * palette: a filterable listbox over {label, hint, action} items with
 * full keyboard support and the WAI-ARIA combobox pattern. It navigates
 * and invokes callbacks; it is not a chatbot.
 */
export function CommandPalette({
  items,
  prompt = 'lore-$',
  placeholder = DEFAULT_PLACEHOLDER,
  fixed = false,
  ariaLabel = 'Navigate',
}: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const baseId = useId();
  const listboxId = `${baseId}-listbox`;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (item) =>
        item.label.toLowerCase().includes(q) ||
        (item.hint ?? '').toLowerCase().includes(q),
    );
  }, [items, query]);

  // Clamp the active option when the result set changes.
  useEffect(() => {
    setActiveIndex((i) => Math.min(i, Math.max(filtered.length - 1, 0)));
  }, [filtered.length]);

  // Keep the active option in view.
  useEffect(() => {
    if (!open) return;
    const option = listRef.current?.children[activeIndex] as
      | HTMLElement
      | undefined;
    option?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex, open]);

  const activeId =
    open && filtered.length > 0 ? `${baseId}-option-${activeIndex}` : undefined;

  function invoke(index: number) {
    const item = filtered[index];
    if (!item) return;
    setOpen(false);
    setQuery('');
    setActiveIndex(0);
    item.action();
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        if (!open) {
          setOpen(true);
          setActiveIndex(0);
        } else if (filtered.length > 0) {
          setActiveIndex((i) => (i + 1) % filtered.length);
        }
        break;
      case 'ArrowUp':
        event.preventDefault();
        if (!open) {
          setOpen(true);
          setActiveIndex(Math.max(filtered.length - 1, 0));
        } else if (filtered.length > 0) {
          setActiveIndex((i) => (i - 1 + filtered.length) % filtered.length);
        }
        break;
      case 'Home':
        if (open) {
          event.preventDefault();
          setActiveIndex(0);
        }
        break;
      case 'End':
        if (open) {
          event.preventDefault();
          setActiveIndex(Math.max(filtered.length - 1, 0));
        }
        break;
      case 'Enter':
        if (open && filtered.length > 0) {
          event.preventDefault();
          invoke(activeIndex);
        }
        break;
      case 'Escape':
        event.preventDefault();
        if (open) {
          setOpen(false);
        } else {
          setQuery('');
        }
        break;
      default:
        break;
    }
  }

  return (
    <div
      className={`lore-palette${fixed ? ' lore-palette--fixed' : ''}`}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setOpen(false);
        }
      }}
    >
      {open ? (
        <ul
          className="lore-palette__list"
          role="listbox"
          id={listboxId}
          aria-label={ariaLabel}
          ref={listRef}
        >
          {filtered.length === 0 ? (
            <li className="lore-palette__empty" aria-disabled="true">
              no matches
            </li>
          ) : (
            filtered.map((item, index) => (
              <li
                key={`${item.label}-${index}`}
                id={`${baseId}-option-${index}`}
                role="option"
                aria-selected={index === activeIndex}
                className={`lore-palette__option${
                  index === activeIndex ? ' lore-palette__option--active' : ''
                }`}
                onMouseEnter={() => setActiveIndex(index)}
                onMouseDown={(event) => {
                  // run before blur closes the list
                  event.preventDefault();
                  invoke(index);
                }}
              >
                <span className="lore-palette__option-label">{item.label}</span>
                {item.hint ? (
                  <span className="lore-palette__option-hint">{item.hint}</span>
                ) : null}
              </li>
            ))
          )}
        </ul>
      ) : null}
      <div className="lore-palette__bar">
        <span className="lore-palette__prompt" aria-hidden="true">
          {prompt}
        </span>
        <input
          ref={inputRef}
          className="lore-palette__input"
          type="text"
          role="combobox"
          aria-label={ariaLabel}
          aria-expanded={open}
          aria-controls={listboxId}
          aria-activedescendant={activeId}
          aria-autocomplete="list"
          autoComplete="off"
          spellCheck={false}
          placeholder={placeholder}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
            setActiveIndex(0);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
      </div>
      <div className="sr-only" role="status" aria-live="polite">
        {open
          ? filtered.length === 1
            ? '1 result'
            : `${filtered.length} results`
          : ''}
      </div>
    </div>
  );
}
