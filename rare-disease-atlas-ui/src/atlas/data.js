// Pure data layer: no React, no DOM. Works in the browser and in Node (tests).
const BULK = new Set(['paper', 'person', 'grant', 'topic']); // too numerous to draw by default
const MECH = new Set(['mechanism', 'pathway']);
const EV_RANK = { observed: 0, inferred: 1, hypothesis: 2 };
const COST = { A: 1, B: 1.2, C: 2, D: 3 };

export const GRADE_LABEL = { A: 'Replicated', B: 'Reported', C: 'Inferred', D: 'Hypothesis' };
export const GRADE_HELP = {
  A: 'Observed in the literature and reported by 2 or more independent sources.',
  B: 'Observed and reported by a single source.',
  C: 'Inferred by the extraction step, not stated outright by a source.',
  D: 'A hypothesis. Needs expert review and experimental validation.',
};
export const other = (e, id) => (e.s === id ? e.o : e.s);
export const norm = (s) =>
  (s || '').toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
export const parseJSONL = (t) => t.split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l));

export function sourceUrl(src = '') {
  if (src.startsWith('PMID:')) return `https://pubmed.ncbi.nlm.nih.gov/${src.slice(5)}/`;
  const nct = src.match(/^NCT\d+/);
  if (nct) return `https://clinicaltrials.gov/study/${nct[0]}`;
  return src.startsWith('http') ? src : null;
}

export function buildAtlas(nodeRows, edgeRows) {
  const nodes = new Map(nodeRows.map((n) => [n.id, { ...n, synonyms: n.synonyms || [], attrs: n.attrs || {} }]));
  // Merge repeated (subject, predicate, object) rows: one edge, many pieces of evidence.
  // Labels/types are always read from `nodes`, never from the edge row (some rows have them null).
  const merged = new Map();
  for (const r of edgeRows) {
    if (!nodes.has(r.subject) || !nodes.has(r.object)) continue;
    const id = `${r.subject}|${r.predicate}|${r.object}`;
    let e = merged.get(id);
    if (!e) merged.set(id, (e = { id, s: r.subject, p: r.predicate, o: r.object, evidence: r.evidence_type, date: r.date, confidence: r.confidence, evidences: [], contradicted: [] }));
    e.evidences.push({ source: r.source, quote: r.quote, by: r.extracted_by });
    (r.contradicted_by || []).forEach((c) => e.contradicted.push(c));
    if (EV_RANK[r.evidence_type] < EV_RANK[e.evidence]) e.evidence = r.evidence_type;
  }
  const edges = [...merged.values()];
  const adj = new Map();
  for (const e of edges) {
    e.sources = new Set(e.evidences.map((x) => x.source)).size;
    // `confidence` is null in the export, so grade from evidence type + independent sources.
    e.grade = e.evidence === 'hypothesis' ? 'D' : e.evidence === 'inferred' ? 'C' : e.sources > 1 ? 'A' : 'B';
    for (const k of [e.s, e.o]) (adj.get(k) || adj.set(k, []).get(k)).push(e);
  }
  const A = { nodes, edges, adj, deg: (id) => adj.get(id)?.length || 0 };
  return Object.assign(A, mechanismIndex(A));
}

// Each disease gets a mechanism signature: mechanisms/pathways linked to it directly or through its causal genes.
function mechanismIndex(A) {
  const { nodes, adj } = A;
  const sig = new Map();
  const anchored = new Set(); // has a gene or phenotype edge, so it is not just a passing mention
  for (const d of nodes.values()) {
    if (d.type !== 'disease') continue;
    const s = new Map();
    const add = (m, e) => (s.get(m) || s.set(m, []).get(m)).push(e);
    const genes = [];
    for (const e of adj.get(d.id) || []) {
      const o = other(e, d.id), t = nodes.get(o).type;
      if (MECH.has(t)) add(o, e);
      if (t === 'gene') genes.push(o);
      if (t === 'gene' || t === 'phenotype') anchored.add(d.id);
    }
    for (const g of genes) for (const e of adj.get(g) || []) if (MECH.has(nodes.get(other(e, g)).type)) add(other(e, g), e);
    sig.set(d.id, s);
  }
  const df = new Map();
  for (const d of anchored) for (const m of sig.get(d).keys()) df.set(m, (df.get(m) || 0) + 1);
  const idf = (m) => Math.log(1 + (anchored.size || 1) / (df.get(m) || 1));
  // Cluster = the widely shared (but not universal) mechanism a disease leans on most.
  const groups = new Map();
  for (const d of anchored) {
    let best = null, bs = 0;
    for (const m of sig.get(d).keys()) { const c = df.get(m); if (c >= 2 && c / anchored.size <= 0.35 && c * idf(m) > bs) { bs = c * idf(m); best = m; } }
    (groups.get(best || 'none') || groups.set(best || 'none', []).get(best || 'none')).push(d);
  }
  let ci = 0;
  const clusters = [...groups].map(([id, members]) => ({ id, label: id === 'none' ? 'No shared mechanism yet' : nodes.get(id).label, members }))
    .sort((a, b) => (a.id === 'none') - (b.id === 'none') || b.members.length - a.members.length)
    // Only real groups (2+ diseases) get their own colour, so colour always means "shares a mechanism".
    .map((c) => ({ ...c, color: c.id === 'none' || c.members.length < 2 || ci >= 7 ? 'var(--slate)' : `var(--c${ci++})` }));
  const clusterOf = new Map(clusters.flatMap((c) => c.members.map((m) => [m, c])));
  return { sig, anchored, idf, clusters, clusterOf };
}

const genesOf = (A, id) => (A.adj.get(id) || []).map((e) => other(e, id)).filter((o) => A.nodes.get(o).type === 'gene');
const linked = (A, a, b) => (A.adj.get(a) || []).some((e) => other(e, a) === b);

/** Diseases that share mechanisms with `id`. viaMechanismOnly = the link is invisible to name or gene. */
export function related(A, id, { min = 0.15, limit = 12 } = {}) {
  const a = A.sig.get(id);
  if (!a?.size) return [];
  const myGenes = new Set(genesOf(A, id));
  const out = [];
  for (const [d, b] of A.sig) {
    if (d === id || !A.anchored.has(d) || !b.size) continue;
    let inter = 0, uni = 0;
    for (const m of new Set([...a.keys(), ...b.keys()])) { const w = A.idf(m); uni += w; if (a.has(m) && b.has(m)) inter += w; }
    if (!inter || inter / uni < min) continue;
    const shared = [...a.keys()].filter((m) => b.has(m));
    const support = [...new Set(shared.flatMap((m) => [...a.get(m), ...b.get(m)]))];
    const best = (x) => Math.min(...x.map((e) => COST[e.grade]));
    const grades = shared.map((m) => Math.max(best(a.get(m)), best(b.get(m))));
    out.push({
      id: d, score: inter / uni, shared, support,
      viaMechanismOnly: !linked(A, id, d) && !genesOf(A, d).some((g) => myGenes.has(g)),
      viable: grades.some((g) => g <= 1.2), // a shared mechanism with observed evidence on both sides
    });
  }
  return out.sort((x, y) => y.score - x.score).slice(0, limit);
}

function nearDiseases(A, id) {
  const out = new Set();
  for (const e of A.adj.get(id) || []) {
    const o = other(e, id), t = A.nodes.get(o).type;
    if (t === 'disease') out.add(o);
    if (t === 'gene') for (const e2 of A.adj.get(o)) { const d = other(e2, o); if (d !== id && A.nodes.get(d).type === 'disease') out.add(d); }
  }
  return out;
}

/** level: exact = a group is linked to this disease; related = only to close relatives; none = honest gap. */
export function communitiesFor(A, id) {
  const pick = (d, match) => (A.adj.get(d) || []).filter((e) => A.nodes.get(other(e, d)).type === 'patient_group')
    .map((e) => ({ group: A.nodes.get(other(e, d)), edge: e, via: d, match }));
  const exact = pick(id, 'exact');
  const seen = new Map(exact.map((g) => [g.group.id, g]));
  for (const d of nearDiseases(A, id)) for (const g of pick(d, 'related')) if (!seen.has(g.group.id)) seen.set(g.group.id, g);
  const groups = [...seen.values()].sort((a, b) => (a.match === 'exact' ? 0 : 1) - (b.match === 'exact' ? 0 : 1) || !!b.group.attrs.website - !!a.group.attrs.website);
  return { level: exact.length ? 'exact' : groups.length ? 'related' : 'none', groups };
}

/** Papers (by PMID) that back the most edges around a node. */
export function papersFor(A, id, limit = 5) {
  const n = new Map();
  for (const e of A.adj.get(id) || []) for (const x of e.evidences) if (A.nodes.get(x.source)?.type === 'paper') n.set(x.source, (n.get(x.source) || 0) + 1);
  return [...n].sort((a, b) => b[1] - a[1]).slice(0, limit).map(([pid, count]) => ({ paper: A.nodes.get(pid), count }));
}

export function actionPlan(A, id) {
  const studies = (A.adj.get(id) || []).filter((e) => e.p === 'studied_in' && A.nodes.get(e.s).type === 'study').map((e) => A.nodes.get(e.s));
  const interventions = new Map();
  for (const st of studies) for (const e of A.adj.get(st.id) || []) if (e.p === 'involves_intervention') interventions.set(e.o, A.nodes.get(e.o));
  // An intervention already tested for a different disease is a reuse candidate.
  const reuse = [...interventions.values()].map((asset) => ({
    asset,
    elsewhere: [...new Set((A.adj.get(asset.id) || []).flatMap((e) => (A.adj.get(e.s) || []).filter((x) => x.p === 'studied_in').map((x) => x.o)))].filter((d) => d !== id),
  })).filter((r) => r.elsewhere.length);
  const people = [...new Set((A.adj.get(id) || []).flatMap((e) => [other(e, id), ...(A.adj.get(other(e, id)) || []).map((x) => other(x, other(e, id)))]))]
    .map((p) => A.nodes.get(p)).filter((n) => n.type === 'person' || n.type === 'grant');
  const communities = communitiesFor(A, id);
  const leads = related(A, id);
  const gaps = [];
  if (communities.level === 'none') gaps.push('No patient organisation is recorded for this disease or a close relative in the sources searched.');
  if (!studies.length) gaps.push('No registered studies are linked to this disease in this dataset.');
  if (!people.length) gaps.push('No investigator or funding links are recorded here, so shared experts cannot be identified yet.');
  if (!leads.length) gaps.push('No other disease shares a mechanism with this one in the evidence collected.');
  return { communities, studies, interventions: [...interventions.values()], reuse, people, leads, gaps };
}

/** Cheapest evidence-weighted route; skips papers/people/grants so paths stay biological. */
export function findPath(A, from, to, maxHops = 6) {
  const dist = new Map([[from, 0]]), prev = new Map(), done = new Set(), q = [[0, from]];
  while (q.length) {
    q.sort((x, y) => x[0] - y[0]);
    const [d, u] = q.shift();
    if (done.has(u)) continue;
    done.add(u);
    if (u === to) break;
    for (const e of A.adj.get(u) || []) {
      const v = other(e, u);
      if (BULK.has(A.nodes.get(v).type)) continue;
      const nd = d + COST[e.grade] + Math.log2(1 + A.deg(v)) * 0.5 + (e.p === 'associated_with' ? 0.8 : 0);
      if (nd < (dist.get(v) ?? Infinity)) { dist.set(v, nd); prev.set(v, [u, e]); q.push([nd, v]); }
    }
  }
  if (!prev.has(to)) return null;
  const steps = [];
  for (let v = to; v !== from; v = prev.get(v)[0]) steps.unshift(prev.get(v)[1]);
  return steps.length <= maxHops ? steps : null;
}

const PHRASE = { has_phenotype: 'shows', causes: 'causes', associated_with: 'is linked to', has_mechanism: 'works through', involved_in_pathway: 'acts in', studied_in: 'is studied in', treats: 'is tested to treat', affects_mechanism: 'affects', involves_intervention: 'tests', supported_by: 'is supported by', disrupts_pathway: 'disrupts' };
export function sentence(A, e) {
  const s = A.nodes.get(e.s), o = A.nodes.get(e.o);
  const verb = e.p === 'studied_in' && s.type === 'study' ? 'studies' : PHRASE[e.p] || e.p.replace(/_/g, ' ');
  return `${s.label} ${verb} ${o.label}.`;
}

export function search(A, q, { limit = 8, types } = {}) {
  const s = norm(q);
  if (!s) return [];
  const out = [];
  for (const n of A.nodes.values()) {
    if (n.type === 'topic' || (types && !types.includes(n.type))) continue;
    let best = 0, via = null;
    for (const name of [n.label, ...n.synonyms]) {
      const t = norm(name);
      const sc = t === s ? 100 : t.startsWith(s) ? 80 : t.split(' ').some((w) => w.startsWith(s)) ? 60 : t.includes(s) ? 40 : 0;
      if (sc > best) { best = sc; via = name === n.label ? null : name; }
    }
    if (best) out.push({ node: n, via, score: best + Math.min(20, Math.log2(1 + A.deg(n.id)) * 3) + (n.type === 'disease' ? 8 : 0) });
  }
  return out.sort((a, b) => b.score - a.score).slice(0, limit);
}

/** Progressive reveal: only the focus and whatever the person has expanded, each capped. */
export function egoGraph(A, roots, cap = 24) {
  const vis = new Set(roots), more = new Map();
  for (const r of roots) {
    const rootBulk = BULK.has(A.nodes.get(r).type);
    const c = (A.adj.get(r) || []).map((e) => [e, other(e, r)]).filter(([, o]) => rootBulk || !BULK.has(A.nodes.get(o).type))
      .sort((x, y) => COST[x[0].grade] - COST[y[0].grade] || A.deg(y[1]) - A.deg(x[1]));
    c.slice(0, cap).forEach(([, o]) => vis.add(o));
    more.set(r, Math.max(0, c.length - cap));
  }
  return { nodes: [...vis].map((id) => A.nodes.get(id)), links: A.edges.filter((e) => vis.has(e.s) && vis.has(e.o)), more };
}
