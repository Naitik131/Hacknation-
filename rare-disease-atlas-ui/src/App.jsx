import { useMemo } from 'react';
import { AtlasProvider, useAtlas } from './atlas/AtlasContext.jsx';
import { ClusterRail } from './components/ClusterRail.jsx';
import { GraphView } from './components/GraphView.jsx';
import { NodePanel } from './components/NodePanel.jsx';
import { PersonaSwitch } from './components/PersonaSwitch.jsx';
import { SearchBox } from './components/SearchBox.jsx';
// import { remoteExplain } from './components/PathExplainer.jsx'; // pass as <NodePanel explain={remoteExplain} /> once /api/explain exists

function Shell() {
  const { A, error, focus, goTo } = useAtlas();
  const starters = useMemo(() => (A ? [...A.anchored].sort((a, b) => A.deg(b) - A.deg(a)).slice(0, 6) : []), [A]);
  if (error) return <p className="boot">Could not load the graph files: {error.message}. Check that both .jsonl files are in public/data.</p>;
  if (!A) return <p className="boot">Loading the atlas…</p>;
  return (
    <div className="app" data-mode={focus ? 'map' : 'start'}>
      <header>
        <h1>Rare Disease Atlas</h1>
        <SearchBox onPick={goTo} />
        <PersonaSwitch />
      </header>
      {!focus ? (
        <main className="start">
          <h2>Start with a disease.</h2>
          <p className="prose">Type a disease, gene or symptom above. The atlas follows it to the biology it shares with other diseases, the patient groups working on it, and what has already been built.</p>
          <p className="hint">Or open one of the best-connected diseases:</p>
          <ul className="chips">{starters.map((id) => <li key={id}><button onClick={() => goTo(id)}>{A.nodes.get(id).label}</button></li>)}</ul>
        </main>
      ) : (
        <main className="stage">
          <ClusterRail />
          <section className="map"><GraphView /></section>
          <aside className="side"><NodePanel /></aside>
        </main>
      )}
    </div>
  );
}

export default function App() {
  return <AtlasProvider><Shell /></AtlasProvider>;
}
