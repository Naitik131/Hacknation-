"""Saved PubMed abstracts -> LLM candidate edges -> code-verified edges.

Usage: python pipeline.py [N]     # N = how many abstracts to process (default 5)
Reads data/papers.jsonl and data/ontology.json (typed; see build_ontology.py).
Outputs:
  data/edges_verified.jsonl     quote verified AND every entity grounded in an ontology
  data/edges_provisional.jsonl  quote verified, but a pathway/molecule/treatment/other
                                entity has no ontology ID yet (its id starts with PROV:)
  data/rejected.jsonl           everything else, with the reason
"""
import datetime
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from llm import PROVIDER, structured
from ontology import Ontology, norm
from schema import Edge

DATA = Path("data")
(DATA / "cache").mkdir(parents=True, exist_ok=True)
CACHE_TAG = "v2"  # bump when PROMPT or schema changes so stale cache is not reused

EntityType = Literal["gene", "disease", "phenotype", "pathway", "molecule", "treatment", "other"]


class Candidate(BaseModel):
    subject: str
    subject_type: EntityType
    predicate: Literal["causes", "associated_with", "has_phenotype",
                       "disrupts_pathway", "treats", "studied_in"]
    object: str
    object_type: EntityType
    quote: str
    evidence_type: Literal["observed", "inferred", "hypothesis"]


class Extraction(BaseModel):
    edges: list[Candidate]


PROMPT = """Extract relationships between genes, diseases, clinical features, molecules,
pathways and treatments from this abstract. Rules:
- Only claims the abstract explicitly states. Never add outside knowledge.
- `quote` must be ONE sentence copied verbatim from the abstract: exact words, no edits.
- Entity names must be bare names with no extra words: "CLN3", not "loss of CLN3" or
  "CLN3 mutations". Use official gene symbols (e.g. TPP1, CLN3) for genes.
- Entity types: gene; disease (a named disorder); phenotype (a clinical sign or symptom
  seen in patients, e.g. seizures, vision loss); pathway (a biological process);
  molecule (a chemical or metabolite); treatment (a therapy or drug); other.
  Molecular or cellular findings are NOT phenotypes.
- evidence_type: observed = a reported result; inferred = authors' interpretation;
  hypothesis = speculation or proposed mechanism.
- If nothing qualifies, return an empty list.

ENTITY TYPE RULES:

gene:
- Only use a specific, named gene.
- Prefer official HGNC gene symbols such as CLN3, CTSD, DNAJC5.
- Do NOT classify phrases such as "NCL mutations", "CLN genes",
  "mutations in different genes", "lysosomal gene products",
  or "gene deficiency" as genes.
- If a specific gene cannot be identified, do not create a gene entity.

disease:
- Must refer to a specific disease or disease subtype.
- Prefer explicit disease names such as neuronal ceroid lipofuscinosis,
  CLN3 disease, Kufs disease type A.

phenotype:
- Must be a specific clinical, cellular, pathological, or measurable feature.
- Examples: epilepsy, cognitive impairment, cortical atrophy,
  visual decline, motor decline.
- Do NOT extract vague phrases such as "childhood presentation",
  "milder phenotype", "clinical presentation", "pathological changes",
  or generic descriptions as phenotypes.

pathway:
- Only use pathway for a named biological pathway or biological process.
- Examples: autophagy, ubiquitin-dependent microautophagy.
- Do not use pathway for symptoms, phenotypes, or generic functional
  descriptions.

treatment:
- Use for an intervention or therapeutic strategy.
- Specific drugs/therapeutic molecules should be classified as molecule
  when appropriate.
- Distinguish specific treatments such as milasen from generic strategies
  such as gene therapy.

molecule:
- Only use for a specific molecular entity, protein, metabolite,
  lipid, enzyme, or other named molecular entity.
- Do not classify vague biological products or processes as molecules.

other:
- Avoid using "other" unless the entity genuinely does not fit
  any supported category.
If you are uncertain about the entity type or cannot identify a specific
entity, DO NOT extract the relationship.
It is better to omit a relationship than create an incorrectly typed entity.
Abstract:
"""


def load_abstracts(n: int) -> dict[str, str]:
    out = {}
    for line in open(DATA / "papers.jsonl", encoding="utf-8"):
        p = json.loads(line)
        if p["abstract"] and not p["retracted"]:
            out[p["pmid"]] = p["abstract"]
        if len(out) >= n:
            break
    return out


def extract(pmid: str, text: str) -> list[Candidate]:
    cache = DATA / "cache" / f"{PROVIDER}_{CACHE_TAG}_{pmid}.json"
    if cache.exists():
        return Extraction.model_validate_json(cache.read_text()).edges
    parsed = structured(PROMPT + text, Extraction)
    cache.write_text(parsed.model_dump_json())
    return parsed.edges


def verify(c: Candidate, pmid: str, text: str, onto: Ontology
           ) -> tuple[Optional[Edge], Optional[str]]:
    if norm(c.quote) not in norm(text):
        return None, "quote_not_in_source"
    s = onto.entity_id(c.subject, c.subject_type)
    o = onto.entity_id(c.object, c.object_type)
    if not s or not o:
        return None, "entity_unresolved"
    return Edge(subject=s, predicate=c.predicate, object=o,
                evidence_type=c.evidence_type, source=f"PMID:{pmid}",
                quote=c.quote, extracted_by="llm",
                date=datetime.date.today().isoformat(),
                subject_type=c.subject_type, object_type=c.object_type,
                subject_label=c.subject, object_label=c.object), None


def main(n: int):
    onto, stats, seen = Ontology(), Counter(), set()
    with open(DATA / "edges_verified.jsonl", "w") as ok, \
         open(DATA / "edges_provisional.jsonl", "w") as prov, \
         open(DATA / "rejected.jsonl", "w") as bad:
        for pmid, text in load_abstracts(n).items():
            try:
                candidates = extract(pmid, text)
            except Exception as e:  # keep going, but show the error
                print(f"PMID {pmid}: {type(e).__name__}: {e}")
                stats["llm_error"] += 1
                continue
            for c in candidates:
                edge, reason = verify(c, pmid, text, onto)
                if not edge:
                    bad.write(json.dumps({"pmid": pmid, "reason": reason,
                                          "candidate": c.model_dump()}) + "\n")
                    stats[reason] += 1
                    continue
                key = (edge.subject, edge.predicate, edge.object, edge.source)
                if key in seen:
                    stats["duplicate"] += 1
                    continue
                seen.add(key)
                if edge.subject.startswith("PROV:") or edge.object.startswith("PROV:"):
                    prov.write(edge.model_dump_json() + "\n")
                    stats["accepted_provisional"] += 1
                else:
                    ok.write(edge.model_dump_json() + "\n")
                    stats["accepted"] += 1
    print(dict(stats))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
