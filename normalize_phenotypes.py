import json
import re
from pathlib import Path

from pydantic import BaseModel
from llm import structured
from ontology import Ontology, norm


DATA = Path("data")

CACHE_DIR = DATA / "cache" / "phenotype_normalization_v2"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT = DATA / "phenotype_aliases.json"


class Normalization(BaseModel):
    canonical_name: str | None
    confidence: str


# ============================================================
# LOAD HPO LABELS + SYNONYMS
# ============================================================

def load_hpo_candidates(onto):
    """
    Build a searchable HPO vocabulary from ontology.json.

    ontology.json maps:
        normalized label -> HP ID

    We use those labels as the canonical vocabulary.

    If ontology.json contains synonym metadata in the future,
    this function can be extended without changing the
    normalization pipeline.
    """

    hpo = onto.maps.get(
        "phenotype",
        {}
    )

    return list(hpo.keys())


# ============================================================
# CANDIDATE GENERATION
# ============================================================

def candidate_labels(
    name,
    hpo_labels,
    limit=40,
):
    """
    Generate lexical HPO candidates.

    The LLM can ONLY choose from these candidates.
    """

    target = norm(name)

    target_words = set(
        target.split()
    )

    scored = []

    for label in hpo_labels:

        candidate = norm(label)

        candidate_words = set(
            candidate.split()
        )

        overlap = len(
            target_words &
            candidate_words
        )

        score = overlap

        # Exact match
        if target == candidate:
            score += 100

        # Substring relationship
        if target in candidate:
            score += 20

        if candidate in target:
            score += 20

        if overlap > 0:
            scored.append(
                (
                    score,
                    label,
                )
            )

    scored.sort(
        reverse=True
    )

    return [
        label
        for _, label
        in scored[:limit]
    ]


# ============================================================
# STRICT HPO NORMALIZATION
# ============================================================

PROMPT = """
You are a strict biomedical phenotype normalization system.

Your task is to normalize a phenotype surface form to an
EXISTING Human Phenotype Ontology (HPO) concept.

The extracted phrase comes directly from a PubMed abstract.

You must choose ONLY from the supplied HPO candidate labels.

Do NOT invent an HPO term.

Do NOT invent an HPO ID.

Do NOT choose a candidate simply because it is related.

============================================================
WHAT COUNTS AS A VALID NORMALIZATION
============================================================

The candidate must represent essentially the SAME clinical
phenotype.

Accept recognized synonyms or very close equivalent wording.

Examples:

"cognitive dysfunction"
→ "cognitive decline"

"vision loss"
→ "visual loss"

"involuntary jerks"
→ "myoclonic jerks"

"tonic-clonic seizure"
→ "generalized tonic-clonic seizure"

============================================================
DO NOT OVER-NORMALIZE
============================================================

Do NOT map a broad term to a more specific phenotype.

Example:

"bowel disease"
→ "inflammatory bowel disease"

INVALID.

Do NOT map a biological mechanism to a phenotype.

Examples:

"lysosomal dysfunction"
"reduced lysosome number"
"increased autophagosomes"

should NOT be normalized as HPO clinical phenotypes.

If the phrase is not clearly a clinical phenotype,
return null.

============================================================
CONTEXT
============================================================

Use the source quote to understand the meaning.

For example:

Surface form:
"cognitive dysfunction"

Quote:
"Patients developed progressive cognitive dysfunction."

A matching HPO cognitive phenotype is appropriate.

But if the phrase describes a cellular or molecular
process, do not force an HPO mapping.

============================================================
SPECIFICITY
============================================================

Do not increase specificity.

For example:

"early death"
→ a highly specific infant mortality phenotype

should only be accepted if the source wording actually
supports that specificity.

If uncertain, return null.

============================================================
CONFIDENCE
============================================================

high:
Clearly equivalent phenotype.

medium:
Probably equivalent but wording differs.

low:
Uncertain.

none:
No valid match.

Only HIGH confidence results will be accepted.

Return only the structured result.
"""


# ============================================================
# CACHE
# ============================================================

def cache_key(
    surface_form,
    quote,
):
    raw = (
        surface_form
        + "|"
        + quote
    )

    return re.sub(
        r"[^a-zA-Z0-9]+",
        "_",
        raw,
    )[:180]


# ============================================================
# NORMALIZE ONE
# ============================================================

def normalize_one(
    name,
    quote,
    hpo_labels,
):

    key = cache_key(
        name,
        quote,
    )

    cache = (
        CACHE_DIR
        / f"{key}.json"
    )

    if cache.exists():

        return Normalization.model_validate_json(
            cache.read_text()
        )

    candidates = candidate_labels(
        name,
        hpo_labels,
    )

    if not candidates:

        result = Normalization(
            canonical_name=None,
            confidence="none",
        )

        cache.write_text(
            result.model_dump_json()
        )

        return result

    prompt = (
        PROMPT
        + "\n\nPHENOTYPE SURFACE FORM:\n"
        + name
        + "\n\nSOURCE QUOTE:\n"
        + quote
        + "\n\nHPO CANDIDATES:\n"
        + "\n".join(
            f"- {x}"
            for x in candidates
        )
    )

    result = structured(
        prompt,
        Normalization,
    )

    cache.write_text(
        result.model_dump_json()
    )

    return result


# ============================================================
# LOAD UNRESOLVED PHENOTYPES
# ============================================================

def load_unresolved_phenotypes():

    entities = {}

    with open(
        DATA / "rejected.jsonl"
    ) as f:

        for line in f:

            item = json.loads(
                line
            )

            if (
                item.get("reason")
                != "entity_unresolved"
            ):
                continue

            c = item[
                "candidate"
            ]

            quote = c.get(
                "quote",
                "",
            )

            for name, entity_type in [
                (
                    c["subject"],
                    c["subject_type"],
                ),
                (
                    c["object"],
                    c["object_type"],
                ),
            ]:

                if entity_type != "phenotype":
                    continue

                key = (
                    norm(name),
                    norm(quote),
                )

                entities[key] = {
                    "surface_form": name,
                    "quote": quote,
                }

    return list(
        entities.values()
    )


# ============================================================
# MAIN
# ============================================================

def main():

    onto = Ontology()

    hpo_labels = load_hpo_candidates(
        onto
    )

    unresolved = (
        load_unresolved_phenotypes()
    )

    print(
        f"Unresolved phenotype contexts: "
        f"{len(unresolved)}"
    )

    aliases = {}

    for i, item in enumerate(
        unresolved,
        1,
    ):

        name = item[
            "surface_form"
        ]

        quote = item[
            "quote"
        ]

        result = normalize_one(
            name,
            quote,
            hpo_labels,
        )

        canonical_id = None

        if result.canonical_name:

            canonical_id = onto.resolve(
                result.canonical_name,
                "phenotype",
            )

        if (
            canonical_id
            and result.confidence == "high"
        ):

            key = (
                norm(name),
                canonical_id,
            )

            aliases[key] = {
                "surface_form": name,
                "canonical_name":
                    result.canonical_name,
                "canonical_id":
                    canonical_id,
                "entity_type":
                    "phenotype",
                "confidence":
                    "high",
                "quote": quote,
            }

            print(
                f"[{i}/{len(unresolved)}] "
                f"ACCEPT: "
                f"{name} -> "
                f"{result.canonical_name} "
                f"({canonical_id})"
            )

        else:

            print(
                f"[{i}/{len(unresolved)}] "
                f"REJECT: "
                f"{name}"
            )

    OUTPUT.write_text(
        json.dumps(
            list(
                aliases.values()
            ),
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print(
        f"Saved {len(aliases)} "
        f"phenotype aliases to "
        f"{OUTPUT}"
    )


if __name__ == "__main__":
    main()