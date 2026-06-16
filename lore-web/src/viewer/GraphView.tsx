import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import type { CorpusIndex } from './data';
import {
  bounds,
  buildGraph,
  GRAPH_TYPES,
  isRetired,
  layout,
  neighbourhood,
  nodeRadius,
  typeColorVar,
} from './graph';
import type { GraphNode } from './graph';

export interface GraphViewProps {
  index: CorpusIndex;
  /** The host/editor's active artifact (roots the local graph, highlighted). */
  activeId: string | null;
  /** Single click on a node — select it (open its file in a host). */
  onSelect: (id: string) => void;
  /** Double click on a node — open its detail page. */
  onOpenDetail: (id: string) => void;
}

const LOGICAL_W = 1000;
const LOGICAL_H = 720;
const LABEL_ZOOM = 0.85; // show all labels at/above this zoom
const LABEL_DEGREE = 7; // always label hubs, regardless of zoom

export function GraphView({ index, activeId, onSelect, onOpenDetail }: GraphViewProps) {
  const [mode, setMode] = useState<'global' | 'local'>('global');
  const [depth, setDepth] = useState(2);
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showOrphans, setShowOrphans] = useState(true);
  const [showUnresolved, setShowUnresolved] = useState(true);
  const [hoverId, setHoverId] = useState<string | null>(null);

  // Full graph + global layout: computed once per corpus.
  const full = useMemo(() => {
    const graph = buildGraph(index.data);
    layout(graph.nodes, graph.edges, { width: LOGICAL_W, height: LOGICAL_H });
    return graph;
  }, [index]);

  const rootId = mode === 'local' && activeId && full.byId.has(activeId) ? activeId : null;

  // Visible sub-graph after mode (local depth) and filters, with a compact
  // re-layout for the local neighbourhood.
  const view = useMemo(() => {
    let ids: Set<string>;
    if (mode === 'local') {
      ids = rootId ? neighbourhood(full.adjacency, rootId, depth) : new Set<string>();
    } else {
      ids = new Set(full.byId.keys());
    }
    const q = query.trim().toLowerCase();
    const sKey = statusFilter.toLowerCase();
    const visible = new Set<string>();
    for (const id of ids) {
      const node = full.byId.get(id)!;
      if (!showUnresolved && node.unresolved) continue;
      if (!showOrphans && node.degree === 0) continue;
      if (typeFilter && node.type !== typeFilter) continue;
      if (sKey && node.status.toLowerCase() !== sKey) continue;
      if (q && !node.haystack.includes(q)) continue;
      visible.add(id);
    }
    const edges = full.edges.filter((e) => visible.has(e.from) && visible.has(e.to));
    let nodes = full.nodes.filter((n) => visible.has(n.id));
    if (mode === 'local') {
      nodes = nodes.map((n) => ({ ...n }));
      layout(nodes, edges, { width: LOGICAL_W, height: LOGICAL_H });
    }
    return { nodes, edges, byId: new Map(nodes.map((n) => [n.id, n])) };
  }, [full, mode, rootId, depth, query, typeFilter, statusFilter, showOrphans, showUnresolved]);

  // --- viewport: size, pan/zoom, drag ---------------------------------------
  const svgRef = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      if (r.width && r.height) setSize({ w: r.width, h: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const [transform, setTransform] = useState({ k: 1, x: 0, y: 0 });
  const transformRef = useRef(transform);
  transformRef.current = transform;

  // Per-node position overrides from dragging; reset when the view changes.
  const [overrides, setOverrides] = useState<Map<string, { x: number; y: number }>>(new Map());
  const overridesRef = useRef(overrides);
  overridesRef.current = overrides;
  useEffect(() => setOverrides(new Map()), [view]);

  const pos = useCallback(
    (node: GraphNode) => overridesRef.current.get(node.id) ?? { x: node.x, y: node.y },
    [],
  );

  // Fit the visible graph when it (or the viewport) changes.
  useEffect(() => {
    const positioned = view.nodes.map((n) => overridesRef.current.get(n.id) ?? n);
    const b = bounds(positioned);
    const pad = 70;
    const gw = b.maxX - b.minX || 1;
    const gh = b.maxY - b.minY || 1;
    const k = Math.max(Math.min((size.w - pad * 2) / gw, (size.h - pad * 2) / gh, 2.4), 0.15);
    setTransform({
      k,
      x: size.w / 2 - k * ((b.minX + b.maxX) / 2),
      y: size.h / 2 - k * ((b.minY + b.maxY) / 2),
    });
  }, [view, size]);

  // Non-passive wheel zoom (so we can preventDefault the page scroll).
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      const t = transformRef.current;
      const lx = (sx - t.x) / t.k;
      const ly = (sy - t.y) / t.k;
      const k = Math.min(Math.max(t.k * (e.deltaY < 0 ? 1.12 : 0.89), 0.1), 4);
      setTransform({ k, x: sx - lx * k, y: sy - ly * k });
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  const drag = useRef<
    | null
    | { kind: 'node' | 'pan'; id?: string; sx: number; sy: number; ox: number; oy: number; moved: boolean }
  >(null);

  const onBackgroundDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    const t = transformRef.current;
    drag.current = { kind: 'pan', sx: e.clientX, sy: e.clientY, ox: t.x, oy: t.y, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onNodeDown = (e: ReactPointerEvent, node: GraphNode) => {
    e.stopPropagation();
    const p = pos(node);
    drag.current = { kind: 'node', id: node.id, sx: e.clientX, sy: e.clientY, ox: p.x, oy: p.y, moved: false };
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  };
  const onMove = (e: ReactPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.sx;
    const dy = e.clientY - d.sy;
    if (!d.moved && Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
    if (d.kind === 'pan') {
      setTransform((t) => ({ ...t, x: d.ox + dx, y: d.oy + dy }));
    } else if (d.id) {
      const k = transformRef.current.k;
      const id = d.id;
      const nx = d.ox + dx / k;
      const ny = d.oy + dy / k;
      setOverrides((m) => new Map(m).set(id, { x: nx, y: ny }));
    }
  };
  const onUp = (e: ReactPointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (d && d.kind === 'node' && d.id && !d.moved) onSelect(d.id);
    try {
      (e.currentTarget as Element).releasePointerCapture(e.pointerId);
    } catch {
      // capture may already be gone
    }
  };

  // --- highlight / dim ------------------------------------------------------
  const focus = hoverId ?? null;
  const focusSet = useMemo(() => {
    if (!focus) return null;
    const set = new Set<string>([focus]);
    for (const nb of full.adjacency.get(focus) ?? []) set.add(nb);
    return set;
  }, [focus, full]);
  const dimmed = (id: string) => (focusSet ? !focusSet.has(id) : false);
  const showLabel = (node: GraphNode) =>
    transform.k >= LABEL_ZOOM ||
    node.degree >= LABEL_DEGREE ||
    node.id === hoverId ||
    node.id === activeId;

  return (
    <div className="graph">
      <div className="graph-toolbar">
        <div className="graph-modes" role="group" aria-label="Graph scope">
          <button
            type="button"
            className="graph-mode"
            aria-pressed={mode === 'global'}
            onClick={() => setMode('global')}
          >
            Global
          </button>
          <button
            type="button"
            className="graph-mode"
            aria-pressed={mode === 'local'}
            onClick={() => setMode('local')}
          >
            Local
          </button>
        </div>
        <div className="graph-depth" data-disabled={mode !== 'local'}>
          <span className="graph-depth__label">depth</span>
          <button
            type="button"
            className="graph-step"
            aria-label="Decrease depth"
            disabled={mode !== 'local' || depth <= 1}
            onClick={() => setDepth((d) => Math.max(1, d - 1))}
          >
            −
          </button>
          <span className="graph-depth__value">{depth}</span>
          <button
            type="button"
            className="graph-step"
            aria-label="Increase depth"
            disabled={mode !== 'local' || depth >= 5}
            onClick={() => setDepth((d) => Math.min(5, d + 1))}
          >
            +
          </button>
        </div>
        <input
          className="graph-search"
          type="search"
          placeholder="filter nodes…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          spellCheck={false}
        />
        <select className="graph-select" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} aria-label="Filter by type">
          <option value="">all types</option>
          {index.types.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select className="graph-select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter by status">
          <option value="">all statuses</option>
          {index.statuses.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <label className="graph-toggle">
          <input type="checkbox" checked={showOrphans} onChange={(e) => setShowOrphans(e.target.checked)} />
          orphans
        </label>
        <label className="graph-toggle">
          <input type="checkbox" checked={showUnresolved} onChange={(e) => setShowUnresolved(e.target.checked)} />
          unresolved
        </label>
        <a className="graph-exit" href="#/">
          ← list
        </a>
      </div>

      <svg
        ref={svgRef}
        className="graph-canvas"
        onPointerDown={onBackgroundDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
      >
        <defs>
          <marker id="rac-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--border)" />
          </marker>
        </defs>
        <g transform={`translate(${transform.x},${transform.y}) scale(${transform.k})`}>
          {view.edges.map((e, i) => {
            const a = view.byId.get(e.from);
            const b = view.byId.get(e.to);
            if (!a || !b) return null;
            const pa = pos(a);
            const pb = pos(b);
            const dim = focusSet ? !(e.from === focus || e.to === focus) : false;
            return (
              <line
                key={`${e.from} ${e.to} ${i}`}
                className={`graph-edge${e.unresolved ? ' graph-edge--unresolved' : ''}${dim ? ' is-dim' : ''}`}
                x1={pa.x}
                y1={pa.y}
                x2={pb.x}
                y2={pb.y}
                markerEnd={e.unresolved ? undefined : 'url(#rac-arrow)'}
              />
            );
          })}
          {view.nodes.map((node) => {
            const p = pos(node);
            const r = nodeRadius(node.degree);
            const isActive = node.id === activeId;
            const cls =
              'graph-node' +
              (node.unresolved ? ' graph-node--unresolved' : '') +
              (isRetired(node.status) ? ' graph-node--retired' : '') +
              (isActive ? ' is-active' : '') +
              (dimmed(node.id) ? ' is-dim' : '');
            return (
              <g
                key={node.id}
                className={cls}
                transform={`translate(${p.x},${p.y})`}
                onPointerDown={(e) => onNodeDown(e, node)}
                onDoubleClick={() => onOpenDetail(node.id)}
                onMouseEnter={() => setHoverId(node.id)}
                onMouseLeave={() => setHoverId((h) => (h === node.id ? null : h))}
              >
                {isActive ? <circle className="graph-node__focus" r={r + 5} /> : null}
                <circle
                  className="graph-node__dot"
                  r={r}
                  style={node.unresolved ? undefined : { fill: typeColorVar(node.type) }}
                />
                {showLabel(node) ? (
                  <text className="graph-node__label" x={0} y={r + 12} textAnchor="middle">
                    {node.label}
                  </text>
                ) : null}
              </g>
            );
          })}
        </g>

        {mode === 'local' && !rootId ? (
          <text className="graph-hint" x="50%" y="50%" textAnchor="middle">
            local graph follows the active artifact — open or select one, or switch to Global
          </text>
        ) : null}
        {view.nodes.length === 0 && !(mode === 'local' && !rootId) ? (
          <text className="graph-hint" x="50%" y="50%" textAnchor="middle">
            no artifacts match the current filters
          </text>
        ) : null}
      </svg>

      <div className="graph-legend">
        {GRAPH_TYPES.map((t) => (
          <span key={t} className="graph-legend__item">
            <span className="graph-legend__dot" style={{ background: typeColorVar(t) }} />
            {t}
          </span>
        ))}
        <span className="graph-legend__note">
          {view.nodes.length} shown · node size = links · drag to move · scroll to zoom
        </span>
      </div>
    </div>
  );
}
