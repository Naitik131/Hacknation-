import { useAtlas } from '../atlas/AtlasContext.jsx';

/** `order` decides what the Next steps tab leads with for each person in the brief. */
export const PERSONAS = {
  maria: { name: 'Maria', role: 'Patient group leader', order: ['leads', 'reuse', 'community', 'gaps'] },
  devon: { name: 'Devon', role: 'Newly diagnosed caregiver', order: ['community', 'gaps', 'leads'] },
  priya: { name: 'Priya', role: 'Biotech scout', order: ['leads', 'community', 'reuse', 'gaps'] },
  osei: { name: 'Dr. Osei', role: 'Researcher', order: ['people', 'leads', 'reuse', 'gaps'] },
};

export function PersonaSwitch() {
  const { persona, setPersona } = useAtlas();
  const keys = Object.keys(PERSONAS);
  return (
    <div className="personas" role="radiogroup" aria-label="Viewing as" style={{ '--i': keys.indexOf(persona), '--n': keys.length }}>
      <span className="slider" aria-hidden="true" />
      {keys.map((k) => (
        <button key={k} role="radio" aria-checked={persona === k} onClick={() => setPersona(k)} title={PERSONAS[k].role}>{PERSONAS[k].name}</button>
      ))}
    </div>
  );
}
