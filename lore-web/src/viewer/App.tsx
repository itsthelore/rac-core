import { useEffect, useMemo, useRef, useState } from 'react';
import { KeyboardHint, TerminalFrame } from '../components';
import { buildIndex, loadExport } from './data';
import type { CorpusIndex } from './data';
import type { LoreExport } from './types';
import { ListView } from './ListView';
import type { ListFilters } from './ListView';
import { DetailView } from './DetailView';
import './viewer.css';

/** Hash-based routing so links work from file:// — no router dep. */
type Route = { view: 'list' } | { view: 'detail'; id: string };

function parseHash(hash: string): Route {
  const match = /^#\/artifact\/(.+)$/.exec(hash);
  if (match) return { view: 'detail', id: decodeURIComponent(match[1]) };
  return { view: 'list' };
}

function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() =>
    parseHash(window.location.hash),
  );
  useEffect(() => {
    const onHashChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);
  return route;
}

export function App() {
  const route = useRoute();
  const [data, setData] = useState<LoreExport | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Filters live here so they survive list -> detail -> list.
  const [filters, setFilters] = useState<ListFilters>({
    query: '',
    type: '',
    status: '',
  });
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadExport().then(setData, (err: unknown) => {
      setError(err instanceof Error ? err.message : String(err));
    });
  }, []);

  const index: CorpusIndex | null = useMemo(
    () => (data ? buildIndex(data) : null),
    [data],
  );

  // Keyboard: "/" focuses search on the list view; Escape returns from
  // detail to list. Both ignored while typing in a form control.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement;
      if (event.key === '/' && !typing && route.view === 'list') {
        event.preventDefault();
        searchRef.current?.focus();
      } else if (event.key === 'Escape' && route.view === 'detail') {
        window.location.hash = '#/';
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [route]);

  const corpus = data?.corpus;

  return (
    <main className="viewer">
      <TerminalFrame title="Lore — export viewer">
        {corpus ? (
          <header className="viewer-meta">
            <p className="viewer-meta__name">
              {corpus.name}
              {corpus.sample ? (
                <span className="viewer-chip viewer-chip--sample">
                  SAMPLE DATA
                </span>
              ) : null}
            </p>
            <p className="viewer-meta__line">
              {corpus.rac_version ? (
                <>
                  rac {corpus.rac_version} {'·'}{' '}
                </>
              ) : null}
              {corpus.artifact_count ?? data?.artifacts.length ?? 0} artifacts{' '}
              {'·'} read-only
            </p>
          </header>
        ) : null}

        {error ? (
          <p className="viewer-error" role="alert">
            could not load the export: {error}
          </p>
        ) : null}

        {!error && !index ? <p className="viewer-empty">loading corpus…</p> : null}

        {index && route.view === 'list' ? (
          <ListView
            index={index}
            filters={filters}
            onFilters={setFilters}
            searchRef={searchRef}
          />
        ) : null}

        {index && route.view === 'detail' ? (
          <DetailView index={index} id={route.id} />
        ) : null}
      </TerminalFrame>

      <footer className="viewer-foot">
        <span>
          <KeyboardHint keys={['/']} /> search {'·'}{' '}
          <KeyboardHint keys={['Tab']} /> move through rows {'·'}{' '}
          <KeyboardHint keys={['Esc']} /> back to list
        </span>
        {corpus?.sample ? (
          <span className="viewer-foot__sample">
            sample data — fictional corpus for demonstration
          </span>
        ) : null}
      </footer>
    </main>
  );
}
