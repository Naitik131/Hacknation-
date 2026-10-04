import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from llm import PROVIDER, structured
from ontology import Ontology

DATA = Path("data")
CACHE = DATA / "cache" / "normalization"
CACHE.mkdir(parents=True, exist_ok=True)

EntityType = Literal["gene", "disease", "phenotype"]


class Normalization(BaseModel):
    canonical_name: str | None
    confidence: Literal["high", "medium", "low", "none"]


PROMPT = """You are normalizing biomedical entity names extracted from PubMed.

Your job is NOT to invent an ontology ID.

Given an entity surface form and a small list of candidate ontology labels,
choose the candidate that is semantically equivalent to the surface form.

Rules:
- Preserve the meaning of the original entity.
- Do not infer a more specific disease or phenotype than the text supports.
- Do not convert a gene into a disease.
- Do not convert a disease into a phenotype.
- If none of the candidates is clearly equivalent, return canonical_name=null
  and confidence="none".
- Only return a canonical_name that appears EXACTLY in the candidate list.

Surface form:
{surface}

Entity type:
{etype}

Candidate ontology labels:
{candidates}
"""


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def candidate_labels(onto: Ontology, surface: str, etype: str, limit=12):
    mapping = onto.maps.get(etype, {})
    labels = list(mapping.keys())

    q = norm(surface)
    q_tokens = set(q.split())

    scored = []

    for label in labels:
        tokens = set(label.split())

        overlap = len(q_tokens & tokens)

        if overlap == 0:
            continue

        # Simple lexical score
        union = len(q_tokens | tokens)
        jaccard = overlap / union if union else 0

        # Prefer candidates sharing more words
        score = jaccard * 100

        scored.append((score, label))

    scored.sort(reverse=True)

    return [label for _, label in scored[:limit]]


def normalize_entity(
    surface: str,
    etype: str,
    onto: Ontology,
):
    key = f"{etype}_{norm(surface)}".replace(" ", "_")
    cache_file = CACHE / f"{key}.json"

    if cache_file.exists():
        return json.loads(cache_file.read_text())

    candidates = candidate_labels(onto, surface, etype)

    if not candidates:
        result = {
            "surface_form": surface,
            "canonical_name": None,
            "canonical_id": None,
            "entity_type": etype,
            "confidence": "none",
        }
        cache_file.write_text(json.dumps(result, indent=2))
        return result

    prompt = PROMPT.format(
        surface=surface,
        etype=etype,
        candidates="\n".join(f"- {x}" for x in candidates),
    )

    result = structured(prompt, Normalization)

    canonical_name = result.canonical_name
    canonical_id = None

    if canonical_name:
        canonical_id = onto.resolve(canonical_name, etype)

    # Never accept an LLM answer that is not actually in our ontology.
    if not canonical_id:
        canonical_name = None
        canonical_id = None
        result.confidence = "none"

    output = {
        "surface_form": surface,
        "canonical_name": canonical_name,
        "canonical_id": canonical_id,
        "entity_type": etype,
        "confidence": result.confidence,
    }

    cache_file.write_text(json.dumps(output, indent=2))

    return output


def main():
    onto = Ontology()

    unresolved = set()

    with open(DATA / "rejected.jsonl", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)

            if row.get("reason") != "entity_unresolved":
                continue

            c = row["candidate"]

            for name, etype in [
                (c["subject"], c["subject_type"]),
                (c["object"], c["object_type"]),
            ]:
                if etype in {"gene", "disease", "phenotype"}:
                    unresolved.add((name, etype))

    aliases = []

    for name, etype in sorted(unresolved):
        print(f"Normalizing: {name} [{etype}]")

        result = normalize_entity(
            name,
            etype,
            onto,
        )

        if result["canonical_id"]:
            aliases.append(result)

    output = DATA / "entity_aliases.json"

    output.write_text(
        json.dumps(aliases, indent=2),
        encoding="utf-8",
    )

    print(f"\nSaved {len(aliases)} aliases to {output}")


if __name__ == "__main__":
    main()