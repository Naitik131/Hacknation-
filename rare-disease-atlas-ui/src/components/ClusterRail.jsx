import { useAtlas } from '../atlas/AtlasContext.jsx';
import { Reveal } from './ui.jsx';

export function ClusterRail() {
  const { A, cluster, setCluster, goTo, focus } = useAtlas();
  return (
    <nav className="rail" aria-label="Mechanism clusters">
      <h2>Mechanism clusters</h2>
      <p className="hint">Diseases grouped by the biology they share, not by their names.</p>
      <ul>
        {A.clusters.map((c) => (
          <li key={c.id}>
            <button className="cl" aria-expanded={cluster === c.id} onClick={() => setCluster(cluster === c.id ? null : c.id)}>
              <i style={{ background: c.color }} aria-hidden="true" />
              <span>{c.label}</span>
              <b>{c.members.length}</b>
            </button>
            <Reveal open={cluster === c.id}>
              <ul className="members">
                {c.members.map((m) => (
                  <li key={m}><button aria-current={m === focus} onClick={() => goTo(m)}>{A.nodes.get(m).label}</button></li>
                ))}
              </ul>
            </Reveal>
          </li>
        ))}
      </ul>
    </nav>
  );
}
