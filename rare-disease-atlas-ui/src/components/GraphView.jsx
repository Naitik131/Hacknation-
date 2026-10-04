import { useEffect, useMemo, useRef, useState } from 'react';
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from 'd3-force';
import { useAtlas } from '../atlas/AtlasContext.jsx';

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Keeps simulation nodes between renders so expanding a node grows the map instead of redrawing it. */
function useForce(graph, size, anchor) {
  const store = useRef(new Map());
  const sim = useRef(null);
  const [, frame] = useState(0);
  useEffect(() => {
    if (!graph || !size.w) return;
    const nodes = graph.nodes.map((n) => {
      let s = store.current.get(n.id);
      if (!s) {
        const a = store.current.get(anchor) || { x: size.w / 2, y: size.h / 2 };
        s = { id: n.id, x: a.x + (Math.random() - 0.5) * 30, y: a.y + (Math.random() - 0.5) * 30 };
        store.current.set(n.id, s);
      }
      return s;
    });
    const links = graph.links.map((l) => ({ source: l.s, target: l.o }));
    sim.current?.stop();
    const s = forceSimulation(nodes)
      .force('link', forceLink(links).id((d) => d.id).distance(115).strength(0.3))
      .force('charge', forceManyBody().strength(-420))
      .force('center', forceCenter(size.w / 2, size.h / 2).strength(0.05))
      .force('collide', forceCollide(28))
      .alphaDecay(0.035);
    if (reduced()) { s.tick(300); s.stop(); frame((f) => f + 1); } else s.on('tick', () => frame((f) => f + 1));
    sim.current = s;
    return () => s.stop();
  }, [graph, size.w, size.h, anchor]);
  return { store: store.current, sim };
}

function usePanZoom(svgRef) {
  const [t, setT] = useState({ k: 1, x: 0, y: 0 });
  useEffect(() => {
    const el = svgRef.current;
    const wheel = (e) => {
      e.preventDefault();
      const r = el.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
      setT((p) => { const k = Math.min(3, Math.max(0.4, p.k * Math.exp(-e.deltaY * 0.0015))); return { k, x: px - ((px - p.x) / p.k) * k, y: py - ((py - p.y) / p.k) * k }; });
    };
    el.addEventListener('wheel', wheel, { passive: false });
    return () => el.removeEventListener('wheel', wheel);
  }, [svgRef]);
  return [t, setT];
}

function Glyph({ type, r, fill }) {
  if (type === 'mechanism' || type === 'pathway') return <rect x={-r * 0.8} y={-r * 0.8} width={r * 1.6} height={r * 1.6} transform="rotate(45)" fill="var(--tint)" stroke="var(--slate)" />;
  if (['study', 'asset', 'treatment', 'molecule', 'other'].includes(type)) return <rect x={-r * 0.8} y={-r * 0.8} width={r * 1.6} height={r * 1.6} rx="3" fill="var(--paper)" stroke="var(--ink)" strokeWidth="1.5" />;
  if (type === 'gene') return <circle r={r} fill="var(--paper)" stroke="var(--ink)" strokeWidth="2.5" />;
  if (type === 'patient_group') return <circle r={r} fill="var(--paper)" stroke="var(--signal)" strokeWidth="3" />;
  if (type === 'phenotype') return <circle r={r * 0.75} fill="var(--paper)" stroke="var(--slate)" strokeWidth="1.5" />;
  return <circle r={r} fill={fill} />;
}

export function GraphView() {
  const { A, graph, focus, expanded, selected, select, edgeId, setEdgeId, cluster, expand } = useAtlas();
  const wrap = useRef(null), svgRef = useRef(null), drag = useRef(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [hover, setHover] = useState(null);
  const [t, setT] = usePanZoom(svgRef);
  const { store, sim } = useForce(graph, size, expanded[expanded.length - 1] || focus);

  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  useEffect(() => setT({ k: 1, x: 0, y: 0 }), [focus, setT]);

  const maxDeg = useMemo(() => Math.max(1, ...(graph?.nodes || []).map((n) => A.deg(n.id))), [A, graph]);
  const members = useMemo(() => new Set(A.clusters.find((c) => c.id === cluster)?.members || []), [A, cluster]);
  if (!graph) return <div className="graph" ref={wrap} />;

  const radius = (id) => 7 + 15 * Math.sqrt(A.deg(id) / maxDeg);
  const toGraph = (e) => { const r = svgRef.current.getBoundingClientRect(); return [(e.clientX - r.left - t.x) / t.k, (e.clientY - r.top - t.y) / t.k]; };
  const down = (e, id) => { e.stopPropagation(); svgRef.current.setPointerCapture(e.pointerId); drag.current = { id, x: e.clientX, y: e.clientY, moved: false }; };
  const downBg = (e) => { svgRef.current.setPointerCapture(e.pointerId); drag.current = { pan: true, x: e.clientX, y: e.clientY, tx: t.x, ty: t.y, moved: false }; };
  const move = (e) => {
    const d = drag.current; if (!d) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (Math.hypot(dx, dy) > 3) d.moved = true;
    if (d.pan) setT((p) => ({ ...p, x: d.tx + dx, y: d.ty + dy }));
    else if (d.moved) { const n = store.get(d.id); [n.fx, n.fy] = toGraph(e); sim.current?.alphaTarget(0.25).restart(); }
  };
  const up = () => {
    const d = drag.current; drag.current = null;
    if (!d || d.pan) return;
    const n = store.get(d.id); n.fx = n.fy = null; sim.current?.alphaTarget(0);
    if (!d.moved) select(d.id);
  };
  const pos = (id) => store.get(id) || { x: size.w / 2, y: size.h / 2 };

  return (
    <div className="graph" ref={wrap}>
      <svg ref={svgRef} width={size.w} height={size.h} role="group" aria-label="Disease graph" onPointerDown={downBg} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
        <g style={{ transform: `translate(${t.x}px, ${t.y}px) scale(${t.k})` }}>
          {graph.links.map((e) => {
            const a = pos(e.s), b = pos(e.o), on = e.id === edgeId;
            return (
              <g key={e.id} className="link" data-on={on}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} strokeWidth={e.grade === 'A' ? 2.2 : 1.3}
                  strokeDasharray={e.evidence === 'hypothesis' ? '1.5 4' : e.evidence === 'inferred' ? '6 4' : undefined} />
                <line className="hit" x1={a.x} y1={a.y} x2={b.x} y2={b.y} onPointerDown={(ev) => ev.stopPropagation()} onClick={() => setEdgeId(e.id)} />
              </g>
            );
          })}
          {graph.nodes.map((n) => {
            const p = pos(n.id), r = radius(n.id);
            const fill = A.clusterOf.get(n.id)?.color || 'var(--slate)';
            const dim = cluster && !members.has(n.id);
            const showLabel = n.id === focus || n.id === selected || n.id === hover || r > 12 || t.k > 1.4;
            return (
              <g key={n.id} className="node" transform={`translate(${p.x},${p.y})`} opacity={dim ? 0.18 : 1} tabIndex={0} role="button" aria-label={n.label} aria-pressed={n.id === selected}
                onPointerDown={(e) => down(e, n.id)} onPointerEnter={() => setHover(n.id)} onPointerLeave={() => setHover(null)} onDoubleClick={() => expand(n.id)}
                onKeyDown={(e) => { if (e.key === 'Enter') select(n.id); if (e.key === ' ') { e.preventDefault(); expand(n.id); } }}>
                <circle r={r + 7} className="halo" data-on={n.id === selected} />
                <Glyph type={n.type} r={r} fill={fill} />
                {showLabel && <text y={r + 14} textAnchor="middle">{n.label.length > 26 ? n.label.slice(0, 25) + '…' : n.label}</text>}
              </g>
            );
          })}
        </g>
      </svg>
      <div className="legend" aria-label="How to read the lines">
        <svg width="34" height="8"><line x1="0" y1="4" x2="34" y2="4" stroke="currentColor" strokeWidth="2.2" /></svg>Observed
        <svg width="34" height="8"><line x1="0" y1="4" x2="34" y2="4" stroke="currentColor" strokeWidth="1.3" strokeDasharray="6 4" /></svg>Inferred
        <svg width="34" height="8"><line x1="0" y1="4" x2="34" y2="4" stroke="currentColor" strokeWidth="1.3" strokeDasharray="1.5 4" /></svg>Hypothesis
      </div>
      <p className="tip">Click to inspect, double-click to open up its connections, drag to move, scroll to zoom.</p>
    </div>
  );
}
