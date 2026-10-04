# AI Atlas for Rare Diseases (Hack-Nation Challenge 05)

Knowledge graph where every edge carries a source, an evidence type
(observed / inferred / hypothesis), and, for LLM-extracted edges, a
code-verified verbatim quote. No source, no edge.

## Run

```bash
pip install anthropic openai pydantic requests
python build_ontology.py          # one-time: HGNC + MONDO + HPO -> data/ontology.json
export ANTHROPIC_API_KEY=...      # default provider
# or: export LLM_PROVIDER=openai OPENAI_API_KEY=...
python pipeline.py "neuronal ceroid lipofuscinosis" 20
```

Outputs `data/edges_verified.jsonl` and `data/rejected.jsonl` (each rejection
has a reason: `quote_not_in_source` or `entity_unresolved`).

## Architecture (so far)

1. `schema.py`: node/edge types, provenance fields required.
2. `pipeline.py`: PubMed fetch, OpenAI structured extraction, then code checks
   (quote must appear in the abstract; both entities must resolve to ontology IDs).

## Next

- Build `data/ontology.json` from HGNC / MONDO / HPO.
- Parse structured sources (ClinVar, HPO, Orphanet, ClinicalTrials.gov, RePORTER) straight into edges.
- Clustering, then UI with evidence drawer per edge.
