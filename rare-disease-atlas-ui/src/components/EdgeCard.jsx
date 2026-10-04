import { sentence, sourceUrl } from '../atlas/data.js';
import { useAtlas } from '../atlas/AtlasContext.jsx';
import { Grade } from './ui.jsx';

/** "Explain every edge": source, relationship, grade, quote and any contradiction beside the connection. */
export function EdgeCard({ edge }) {
  const { A, setEdgeId, select } = useAtlas();
  const s = A.nodes.get(edge.s), o = A.nodes.get(edge.o);
  return (
    <article className="edge">
      <button className="back" onClick={() => setEdgeId(null)}>Back to {A.nodes.get(edge.s).label}</button>
      <h3 className="prose">{sentence(A, edge)}</h3>
      <dl>
        <dt>Evidence</dt><dd><Grade g={edge.grade} sources={edge.sources} /></dd>
        <dt>Relationship</dt><dd>{edge.p.replace(/_/g, ' ')}</dd>
        <dt>Kind of claim</dt><dd>{edge.evidence === 'observed' ? 'Stated by a source' : edge.evidence === 'inferred' ? 'Inferred from sources' : 'Hypothesis'}</dd>
        <dt>Confidence score</dt><dd>{edge.confidence ?? 'Not scored in this dataset'}</dd>
        <dt>Collected</dt><dd>{edge.date}</dd>
      </dl>
      <h4>What the sources say</h4>
      {edge.evidences.map((x, i) => {
        const paper = A.nodes.get(x.source), url = sourceUrl(x.source);
        return (
          <figure key={i}>
            {x.quote ? <blockquote className="prose">{x.quote}</blockquote> : <p className="hint">From a structured registry record, so there is no text excerpt.</p>}
            <figcaption>
              {url ? <a href={url} target="_blank" rel="noreferrer">{paper ? `${paper.label} (${paper.attrs.year})` : x.source}</a> : x.source}
              <small>{x.by === 'llm' ? 'Extracted by AI, needs review' : 'Structured record'}</small>
            </figcaption>
          </figure>
        );
      })}
      <h4>Contradicting evidence</h4>
      {edge.contradicted.length
        ? <ul>{edge.contradicted.map((c, i) => <li key={i}>{String(c)}</li>)}</ul>
        : <p className="hint">None recorded. That reflects the sources searched, not proof that none exists.</p>}
      <div className="row">
        <button onClick={() => select(edge.s)}>Open {s.label}</button>
        <button onClick={() => select(edge.o)}>Open {o.label}</button>
      </div>
    </article>
  );
}
