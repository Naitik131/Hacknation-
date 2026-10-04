import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { buildAtlas, egoGraph, parseJSONL } from './data.js';

const Ctx = createContext(null);
export const useAtlas = () => useContext(Ctx);

export function AtlasProvider({ nodesUrl = '/data/graph_nodes_unified.jsonl', edgesUrl = '/data/edges_unified.jsonl', children }) {
  const [A, setA] = useState(null);
  const [error, setError] = useState(null);
  const [focus, setFocus] = useState(null);       // root of the drawn graph
  const [expanded, setExpanded] = useState([]);   // nodes the person opened up
  const [selected, setSelectedId] = useState(null); // node shown in the side panel
  const [edgeId, setEdgeId] = useState(null);     // edge shown in the side panel
  const [cluster, setCluster] = useState(null);   // highlighted mechanism cluster
  const [persona, setPersona] = useState('maria');

  useEffect(() => {
    let live = true;
    Promise.all([nodesUrl, edgesUrl].map((u) => fetch(u).then((r) => { if (!r.ok) throw new Error(`${u} returned ${r.status}`); return r.text(); })))
      .then(([n, e]) => live && setA(buildAtlas(parseJSONL(n), parseJSONL(e))))
      .catch((x) => live && setError(x));
    return () => { live = false; };
  }, [nodesUrl, edgesUrl]);

  const select = useCallback((id) => { setSelectedId(id); setEdgeId(null); }, []);
  const goTo = useCallback((id) => { setFocus(id); setExpanded([]); setCluster(null); select(id); }, [select]);
  const expand = useCallback((id) => setExpanded((x) => (x.includes(id) ? x : [...x, id])), []);
  const graph = useMemo(() => (A && focus ? egoGraph(A, [focus, ...expanded]) : null), [A, focus, expanded]);

  const value = { A, error, focus, expanded, graph, selected, select, edgeId, setEdgeId, cluster, setCluster, persona, setPersona, goTo, expand };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
