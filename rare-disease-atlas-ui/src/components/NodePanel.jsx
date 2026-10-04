import { useMemo, useState } from 'react';
import { papersFor, sentence } from '../atlas/data.js';
import { useAtlas } from '../atlas/AtlasContext.jsx';
import { ActionView } from './ActionView.jsx';
import { EdgeCard } from './EdgeCard.jsx';
import { PathExplainer } from './PathExplainer.jsx';
import { EDGE_TITLE, Grade, Reveal, TYPE_NAME } from './ui.jsx';

export function NodePanel({ explain }) {
  const { A, selected, edgeId, setEdgeId, goTo, expand, expanded, focus, graph } = useAtlas();
  const [tab, setTab] = useState('overview');
  const [more, setMore] = useState({});
  const groups = useMemo(() => {
    const g = new Map();
    for (const e of A.adj.get(selected) || []) {
      const k = EDGE_TITLE[e.p]?.[e.s === selected ? 0 : 1] || e.p.replace(/_/g, ' ');
      (g.get(k) || g.set(k, []).get(k)).push(e);
    }
    return [...g];
  }, [A, selected]);
  const papers = useMemo(() => (selected ? papersFor(A, selected) : []), [A, selected]);

  if (edgeId) return <EdgeCard edge={A.edges.find((e) => e.id === edgeId)} />;
  if (!selected) return <p className="empty">Select a node on the map to see what is known about it.</p>;

  const n = A.nodes.get(selected), isDisease = n.type === 'disease', cl = A.clusterOf.get(selected);
  const tabs = [['overview', 'Overview'], ...(isDisease ? [['next', 'Next steps']] : []), ['route', 'Route']];
  const active = tabs.some(([k]) => k === tab) ? tab : 'overview';
  const deg = A.deg(selected), hidden = graph?.more.get(selected) ?? 0;
  const maxDeg = Math.max(1, ...[...A.anchored].map(A.deg));
  const aka = n.synonyms.filter((s) => s !== n.label).slice(0, 4);

  const EdgeRow = ({ e }) => {
    const o = A.nodes.get(e.s === selected ? e.o : e.s);
    return <li><button className="row-btn" onClick={() => setEdgeId(e.id)} title={sentence(A, e)}><span>{o.label}</span><Grade g={e.grade} /></button></li>;
  };

  return (
    <div className="panel">
      <h3>{n.label}</h3>
      <p className="meta"><span>{TYPE_NAME[n.type]}</span>{cl && <span><i className="dot" style={{ background: cl.color }} />Grouped under {cl.label}</span>}</p>
      {aka.length > 0 && <p className="hint">Also known as {aka.join(', ')}.</p>}
      <div className="tabs" role="tablist">
        {tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={active === k} onClick={() => setTab(k)}>{l}</button>)}
      </div>

      {active === 'overview' && (
        <>
          <div className="bar" aria-hidden="true"><span style={{ width: `${Math.min(100, (100 * deg) / maxDeg)}%` }} /></div>
          <p className="hint">{deg} recorded {deg === 1 ? 'connection' : 'connections'}.</p>
          {groups.map(([p, es]) => (
            <section key={p} className="sec">
              <h4>{p}</h4>
              <ul className="plain">{es.slice(0, 4).map((e) => <EdgeRow key={e.id} e={e} />)}</ul>
              {es.length > 4 && (
                <>
                  <Reveal open={!!more[p]}><ul className="plain">{es.slice(4).map((e) => <EdgeRow key={e.id} e={e} />)}</ul></Reveal>
                  <button className="link" onClick={() => setMore({ ...more, [p]: !more[p] })}>{more[p] ? 'Show fewer' : `Show ${es.length - 4} more`}</button>
                </>
              )}
            </section>
          ))}
          {papers.length > 0 && (
            <section className="sec">
              <h4>Papers behind these connections</h4>
              <ul className="plain">{papers.map(({ paper, count }) => (
                <li key={paper.id}><a href={`https://pubmed.ncbi.nlm.nih.gov/${paper.id.slice(5)}/`} target="_blank" rel="noreferrer">{paper.label}</a><small>{paper.attrs.year}</small><small>backs {count}</small></li>
              ))}</ul>
            </section>
          )}
          <div className="row">
            {selected !== focus && !expanded.includes(selected) && <button onClick={() => expand(selected)}>Show its connections</button>}
            {selected !== focus && <button onClick={() => goTo(selected)}>Center the map here</button>}
          </div>
          {hidden > 0 && <p className="hint">The map shows the strongest connections first. {hidden} more are not drawn.</p>}
        </>
      )}
      {active === 'next' && <ActionView id={selected} />}
      {active === 'route' && <PathExplainer key={selected} from={selected} explain={explain} />}
    </div>
  );
}
