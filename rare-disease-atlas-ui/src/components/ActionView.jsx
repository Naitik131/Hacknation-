import { useMemo, useState } from 'react';
import { actionPlan, sentence } from '../atlas/data.js';
import { useAtlas } from '../atlas/AtlasContext.jsx';
import { PERSONAS } from './PersonaSwitch.jsx';
import { Reveal, Section } from './ui.jsx';

/** Patient action view: what is shared, who could help, what to do next, and what is still missing. */
export function ActionView({ id }) {
  const { A, persona, goTo, setEdgeId, select } = useAtlas();
  const plan = useMemo(() => actionPlan(A, id), [A, id]);
  const [open, setOpen] = useState(null);
  const [all, setAll] = useState(false);
  const name = (x) => A.nodes.get(x).label;
  const { communities: c } = plan;
  const groups = all ? c.groups : c.groups.slice(0, 4);

  const sections = {
    community: (
      <Section key="community" title="Patient groups"
        hint={c.level === 'exact' ? 'Groups linked to this disease.' : c.level === 'related' ? 'No group is listed for exactly this disease. These cover closely related ones, and could help you build the missing group.' : undefined}>
        {c.level === 'none' ? <p className="gap">No patient group found for this disease or a close relative. Starting one would fill a real gap.</p> : (
          <>
            <ul className="plain">
              {groups.map(({ group: g, match }) => (
                <li key={g.id}>
                  {g.attrs.website ? <a href={g.attrs.website} target="_blank" rel="noreferrer">{g.label}</a> : <span>{g.label}</span>}
                  <small>{g.attrs.country}</small>
                  <small>{match === 'exact' ? 'For this disease' : 'For a related disease'}</small>
                </li>
              ))}
            </ul>
            {c.groups.length > 4 && <button className="link" onClick={() => setAll(!all)}>{all ? 'Show fewer' : `Show all ${c.groups.length}`}</button>}
          </>
        )}
      </Section>
    ),
    leads: (
      <Section key="leads" title="Diseases that share this biology" hint="Found by shared mechanism, so the names may look unrelated.">
        {!plan.leads.length ? <p className="gap">No other disease shares a mechanism with this one in the evidence collected.</p> : (
          <ul className="plain">
            {plan.leads.map((l) => {
              const there = actionPlan(A, l.id);
              return (
                <li key={l.id} className="lead">
                  <button className="row-btn" aria-expanded={open === l.id} onClick={() => setOpen(open === l.id ? null : l.id)}>
                    <span>{name(l.id)}</span>
                    <small>{l.viable ? 'Backed by observed evidence' : 'Inferred only'}</small>
                    {l.viaMechanismOnly && <small>Linked only through mechanism</small>}
                  </button>
                  <Reveal open={open === l.id}>
                    <p>Shared: {l.shared.slice(0, 4).map(name).join(', ')}.</p>
                    <ul className="plain">{l.support.slice(0, 4).map((e) => <li key={e.id}><button className="link" onClick={() => setEdgeId(e.id)}>{sentence(A, e)}</button></li>)}</ul>
                    <p className="proposal"><b>Proposed next step</b> (a suggestion, not a finding): {there.studies.length
                      ? `${there.studies.length} registered studies for ${name(l.id)} could inform a shared design. Ask a clinician whether the eligibility criteria and mechanism carry over.`
                      : `${name(l.id)} has no registered study here yet. A joint natural history study could be the first.`}</p>
                    <button className="link" onClick={() => goTo(l.id)}>Center the map on {name(l.id)}</button>
                  </Reveal>
                </li>
              );
            })}
          </ul>
        )}
      </Section>
    ),
    reuse: (
      <Section key="reuse" title="Work you could reuse" hint="Interventions studied here that were also studied for another disease.">
        {plan.reuse.length ? (
          <ul className="plain">{plan.reuse.slice(0, 6).map((r) => (
            <li key={r.asset.id}><span>{r.asset.label}</span><small>also studied for {r.elsewhere.slice(0, 2).map(name).join(', ')}</small></li>
          ))}</ul>
        ) : <p className="gap">{plan.studies.length ? 'None of this disease’s interventions appear in studies of other diseases.' : 'No registered studies are linked to this disease in this dataset.'}</p>}
        {!!plan.studies.length && <p className="hint">{plan.studies.length} registered {plan.studies.length === 1 ? 'study' : 'studies'} linked.</p>}
      </Section>
    ),
    people: (
      <Section key="people" title="People and funders">
        {plan.people.length ? <ul className="plain">{plan.people.slice(0, 8).map((p) => <li key={p.id}><button className="link" onClick={() => select(p.id)}>{p.label}</button></li>)}</ul>
          : <p className="gap">No investigator or funding links are recorded for this disease. The data has researcher names but no authorship edges yet, so shared experts cannot be found.</p>}
      </Section>
    ),
    gaps: plan.gaps.length ? (
      <Section key="gaps" title="What we could not find">
        <ul className="plain">{plan.gaps.map((g) => <li key={g} className="gap">{g}</li>)}</ul>
      </Section>
    ) : null,
  };
  return <div className="action">{PERSONAS[persona].order.map((k) => sections[k])}</div>;
}
