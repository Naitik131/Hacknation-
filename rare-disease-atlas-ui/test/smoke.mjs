import fs from 'node:fs';
import { buildAtlas, parseJSONL, search, related, communitiesFor, actionPlan, findPath, egoGraph, sentence, papersFor } from '../src/atlas/data.js';
const rd = (f) => parseJSONL(fs.readFileSync(new URL('../public/data/' + f, import.meta.url), 'utf8'));
const A = buildAtlas(rd('graph_nodes_unified.jsonl'), rd('edges_unified.jsonl'));
const id = (q) => search(A, q)[0].node.id;
console.log('nodes', A.nodes.size, 'merged edges', A.edges.length, 'anchored diseases', A.anchored.size);
console.log('clusters:', A.clusters.map((c) => `${c.label} (${c.members.length})`).join(' | '));
console.log('search "batten":', search(A, 'batten').slice(0, 3).map((r) => r.node.label + (r.via ? ` via ${r.via}` : '')));
console.log('search "CLN3":', search(A, 'CLN3').slice(0, 3).map((r) => r.node.type + ':' + r.node.label));
for (const q of ['CLN7 Disease', 'CLN5 Disease', 'Kufor-Rakeb']) {
  const d = id(q), c = communitiesFor(A, d), r = related(A, d);
  console.log(`\n[${A.nodes.get(d).label}] communities=${c.level}/${c.groups.length}  related=${r.length}  cluster=${A.clusterOf.get(d)?.label}`);
  r.slice(0, 3).forEach((x) => console.log('  ~', A.nodes.get(x.id).label, x.score.toFixed(2), x.viaMechanismOnly ? 'MECH-ONLY' : '', x.viable ? 'viable' : 'weak', x.shared.map((m) => A.nodes.get(m).label).slice(0, 2)));
}
const ap = actionPlan(A, id('CLN2 Disease'));
console.log('\nCLN2 plan: studies', ap.studies.length, 'interventions', ap.interventions.length, 'reuse', ap.reuse.length, 'gaps', ap.gaps);
const p = findPath(A, id('CLN7 Disease'), id('Alzheimer')); 
console.log('path CLN7->Alzheimer:', p ? p.map((e) => sentence(A, e)) : null);
console.log('papers for CLN3:', papersFor(A, id('Batten Disease'), 2).map((x) => x.paper.label.slice(0, 50) + ' x' + x.count));
const g = egoGraph(A, [id('Neuronal Ceroid Lipofuscinosis')]);
console.log('ego(NCL):', g.nodes.length, 'nodes', g.links.length, 'links; hidden', [...g.more.values()]);
