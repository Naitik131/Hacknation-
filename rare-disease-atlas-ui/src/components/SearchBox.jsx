import { useId, useMemo, useState } from 'react';
import { search } from '../atlas/data.js';
import { useAtlas } from '../atlas/AtlasContext.jsx';
import { TYPE_NAME } from './ui.jsx';

/** One global search: disease, gene, symptom, patient group or mechanism. Synonyms resolve to one node. */
export function SearchBox({ onPick, types, label = 'Search the atlas', placeholder = 'A disease, gene, symptom, patient group or mechanism' }) {
  const { A } = useAtlas();
  const id = useId();
  const [q, setQ] = useState('');
  const [i, setI] = useState(0);
  const [open, setOpen] = useState(false);
  const hits = useMemo(() => (A ? search(A, q, { types }) : []), [A, q, types]);
  const pick = (h) => { onPick(h.node.id); setQ(''); setOpen(false); };
  const onKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setI((x) => Math.min(x + 1, hits.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setI((x) => Math.max(x - 1, 0)); }
    else if (e.key === 'Enter' && hits[i]) pick(hits[i]);
    else if (e.key === 'Escape') setOpen(false);
  };
  return (
    <div className="search">
      <label htmlFor={id}>{label}</label>
      <input id={id} value={q} placeholder={placeholder} autoComplete="off" role="combobox" aria-expanded={open && hits.length > 0} aria-controls={`${id}-l`} aria-activedescendant={hits[i] ? `${id}-${i}` : undefined}
        onChange={(e) => { setQ(e.target.value); setI(0); setOpen(true); }} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onKeyDown={onKey} />
      {open && q && (
        <ul id={`${id}-l`} role="listbox">
          {hits.map((h, k) => (
            <li key={h.node.id} id={`${id}-${k}`} role="option" aria-selected={k === i} onMouseDown={() => pick(h)} onMouseEnter={() => setI(k)}>
              <span>{h.node.label}</span>
              <small>{TYPE_NAME[h.node.type]}</small>
              {h.via && <small>matched the synonym “{h.via}”</small>}
            </li>
          ))}
          {!hits.length && <li className="none">No match. Try a gene symbol, a symptom, or a broader disease name.</li>}
        </ul>
      )}
    </div>
  );
}
