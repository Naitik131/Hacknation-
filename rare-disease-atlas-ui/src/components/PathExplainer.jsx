import { useMemo, useState } from 'react';
import { findPath, sentence, sourceUrl } from '../atlas/data.js';
import { useAtlas } from '../atlas/AtlasContext.jsx';
import { Grade } from './ui.jsx';
import { SearchBox } from './SearchBox.jsx';

/** Optional: send the cited steps to your own server that calls OpenAI and returns { text }. Keep the API key on the server. */
export async function remoteExplain(A, steps, endpoint = '/api/explain') {
  const payload = steps.map((e) => ({ claim: sentence(A, e), grade: e.grade, quotes: e.evidences.map((x) => x.quote).filter(Boolean).slice(0, 2), sources: e.evidences.map((x) => x.source) }));
  const r = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ steps: payload }) });
  if (!r.ok) throw new Error(`Explain failed: ${r.status}`);
  return (await r.json()).text;
}

export function PathExplainer({ from, explain }) {
  const { A, setEdgeId } = useAtlas();
  const [to, setTo] = useState(null);
  const [text, setText] = useState(null);
  const [busy, setBusy] = useState(false);
  const steps = useMemo(() => (to ? findPath(A, from, to) : undefined), [A, from, to]);
  const run = async () => { setBusy(true); try { setText(await explain(A, steps)); } catch (e) { setText(e.message); } setBusy(false); };

  return (
    <div className="route">
      <p className="hint">Pick a second node to see how it connects to {A.nodes.get(from).label}, one cited step at a time.</p>
      <SearchBox label="Connect to" onPick={(id) => { setTo(id); setText(null); }} placeholder="Another disease, gene or symptom" />
      {to && steps === null && (
        <div className="gap">
          <h4>No supported route</h4>
          <p>We searched {A.nodes.size.toLocaleString()} nodes and {A.edges.length.toLocaleString()} relationships for a path of up to 6 steps and found none. That means nothing is recorded here, not that no connection exists.</p>
          <p>To test next: look for papers that mention both, or compare their mechanism lists on the Next steps tab.</p>
        </div>
      )}
      {steps && (
        <>
          <ol className="steps">
            {steps.map((e) => (
              <li key={e.id}>
                <button className="link prose" onClick={() => setEdgeId(e.id)}>{sentence(A, e)}</button>
                <Grade g={e.grade} sources={e.sources} />
                {e.evidences[0].quote && <q className="prose">{e.evidences[0].quote}</q>}
                {sourceUrl(e.evidences[0].source) && <a href={sourceUrl(e.evidences[0].source)} target="_blank" rel="noreferrer">Source</a>}
              </li>
            ))}
          </ol>
          {explain && <button onClick={run} disabled={busy}>{busy ? 'Writing…' : 'Explain in plain language'}</button>}
          {text && <p className="prose summary">{text}</p>}
        </>
      )}
    </div>
  );
}
