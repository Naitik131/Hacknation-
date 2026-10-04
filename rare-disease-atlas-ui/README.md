# Rare Disease Atlas UI

React front-end for the Hack-Nation Challenge 05 brief. Reads your two JSONL files directly in the browser.

    npm install
    npm run dev      # http://localhost:5173
    npm test         # logic smoke test against the real data (Node, no browser)

Data lives in `public/data/` (graph_nodes_unified.jsonl, edges_unified.jsonl). Swap in new exports there.

## Layout
- `src/atlas/data.js`: pure logic. Index, merged edges, evidence grade, search with synonyms, mechanism clusters, related diseases, communities, action plan, path finding, ego graph.
- `src/atlas/AtlasContext.jsx`: loads files, holds focus / selection / persona state.
- `src/components/`: SearchBox, PersonaSwitch, ClusterRail, GraphView, NodePanel, EdgeCard, ActionView, PathExplainer, ui.

## Plain-language explanations with OpenAI
PathExplainer works without a key. To add the LLM step, expose `POST /api/explain` on your own server
(takes `{steps}`, returns `{text}`, calls OpenAI there so the key stays server-side) and pass
`explain={remoteExplain}` to `<NodePanel />` in App.jsx.
