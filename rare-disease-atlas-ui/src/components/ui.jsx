import { GRADE_HELP, GRADE_LABEL } from '../atlas/data.js';

export const TYPE_NAME = { disease: 'Disease', gene: 'Gene', phenotype: 'Symptom', mechanism: 'Mechanism', pathway: 'Pathway', study: 'Study', asset: 'Asset', treatment: 'Treatment', molecule: 'Molecule', patient_group: 'Patient group', paper: 'Paper', person: 'Researcher', grant: 'Grant', other: 'Other' };

/** Smoothly opens and closes its children. Closed content is removed from tab order. */
export function Reveal({ open, children }) {
  return (
    <div className="reveal" data-open={open} inert={open ? undefined : ''}>
      <div>{children}</div>
    </div>
  );
}

/** Evidence grade as text first, mark second, so it never relies on colour alone. */
export function Grade({ g, sources }) {
  return (
    <span className={`grade g${g}`} title={GRADE_HELP[g]}>
      <i aria-hidden="true" />
      {GRADE_LABEL[g]}
      {sources > 1 && <small>{sources} sources</small>}
    </span>
  );
}

export const Section = ({ title, hint, children }) => (
  <section className="sec">
    <h4>{title}</h4>
    {hint && <p className="hint">{hint}</p>}
    {children}
  </section>
);

/** Section titles for the edges around a node, depending on which way the edge points. */
export const EDGE_TITLE = {
  has_phenotype: ['Symptoms', 'Diseases with this symptom'], causes: ['Causes', 'Caused by'], associated_with: ['Linked to', 'Linked to'],
  has_mechanism: ['Mechanisms', 'Mechanism of'], involved_in_pathway: ['Pathways', 'Acts in this pathway'], studied_in: ['Studied in', 'Studies'],
  treats: ['Treats', 'Treated by'], affects_mechanism: ['Affects', 'Affected by'], involves_intervention: ['Tests', 'Tested in'],
  supported_by: ['Patient groups', 'Supports'], disrupts_pathway: ['Disrupts', 'Disrupted by'],
};
