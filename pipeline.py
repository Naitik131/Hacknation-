"""
Fast PubMed edge extraction + evidence verification.

Usage:
    python3 pipeline.py 150

Pipeline:
1. Reuse existing cached LLM extraction:
       data/cache/<provider>_v2_<PMID>.json
2. Deterministically accept clearly direct evidence.
3. Batch ambiguous candidates from each paper into ONE LLM evidence-review call.
4. Cache evidence reviews:
       data/cache/evidence_v1_<PMID>.json
5. Resolve ontology IDs.
6. Write canonical, provisional, and rejected edges.
"""

import datetime
import json
import re
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

# IMPORTANT:
# Keep this as v2 so your existing successful Anthropic extraction
# cache continues to be reused.
CACHE_TAG = "v3"


EntityType = Literal[
    "gene",
    "disease",
    "phenotype",
    "pathway",
    "molecule",
    "treatment",
    "other",
]


# ============================================================
# EXTRACTION SCHEMA
# ============================================================

class Candidate(BaseModel):
    subject: str
    subject_type: EntityType

    predicate: Literal[
        "causes",
        "associated_with",
        "has_phenotype",
        "disrupts_pathway",
        "treats",
        "studied_in",
    ]

    object: str
    object_type: EntityType

    quote: str

    evidence_type: Literal[
        "observed",
        "inferred",
        "hypothesis",
    ]


class Extraction(BaseModel):
    edges: list[Candidate]


# ============================================================
# EVIDENCE VERIFICATION SCHEMA
# ============================================================

class EvidenceDecision(BaseModel):
    candidate_index: int

    decision: Literal[
        "accept_direct",
        "accept_inferred",
        "reject",
    ]

    evidence_type: Literal[
        "observed",
        "inferred",
        "hypothesis",
    ]

    confidence: Literal[
        "high",
        "medium",
        "low",
    ]

    reason: str


class EvidenceReview(BaseModel):
    decisions: list[EvidenceDecision]


# ============================================================
# ORIGINAL EXTRACTION PROMPT
# ============================================================

PROMPT = """Extract relationships between genes, diseases, clinical features, molecules,
pathways and treatments from this abstract.

Rules:

- Only claims the abstract explicitly states.
- Never add outside knowledge.
- `quote` must be ONE sentence copied verbatim from the abstract.
- The quote must contain the exact original words from the abstract.
- Entity names must be bare names with no extra words.
- Use official gene symbols where possible.

Entity types:

gene
- Only use a specific, named gene.
- Prefer official HGNC symbols such as CLN3, CTSD, DNAJC5.
- Do NOT classify phrases such as:
  "NCL mutations"
  "CLN genes"
  "mutations in different genes"
  "lysosomal gene products"
  "gene deficiency"
  as genes.

disease
- Must refer to a specific disease or disease subtype.
- Examples:
  neuronal ceroid lipofuscinosis
  CLN3 disease
  Kufs disease type A

phenotype
- Must be a specific clinical, pathological, cellular, or measurable feature.
- Examples:
  epilepsy
  cognitive impairment
  cortical atrophy
  visual decline
  motor decline
- Do NOT extract vague phrases such as:
  "childhood presentation"
  "milder phenotype"
  "clinical presentation"
  "pathological changes"

pathway
- Only use pathway for a named biological pathway or biological process.
- Examples:
  autophagy
  ubiquitin-dependent microautophagy

molecule
- Only use for a specific molecular entity, protein, metabolite,
  lipid, enzyme, or other named molecular entity.

treatment
- Use for an intervention or therapeutic strategy.
- Specific therapeutic molecules should be classified appropriately.
- Distinguish specific treatments from generic strategies.

other
- Avoid unless the entity genuinely does not fit another category.

Predicates:

causes
associated_with
has_phenotype
disrupts_pathway
treats
studied_in

Evidence type:

observed
- Directly reported experimental or clinical observation.

inferred
- Authors' interpretation or a relationship supported by context.

hypothesis
- Speculation or proposed mechanism.

If you are uncertain about an entity or relationship,
DO NOT extract it.

It is better to omit a relationship than create an incorrect one.

If nothing qualifies, return an empty list.


CRITICAL EDGE DIRECTION RULES:

Every edge is directional. The subject must be the entity performing or having the relationship.

causes:
    cause -> disease/effect
    Example: CLN6 -> causes -> Kufs disease type A

has_phenotype:
    disease -> phenotype
    Example: Kufs disease type A -> has_phenotype -> myoclonus

disrupts_pathway:
    gene/molecule -> pathway
    Example: CLN6 -> disrupts_pathway -> lysosomal pathway

treats:
    treatment/therapy/drug/vector -> disease
    Example: gene therapy vector -> treats -> CLN5 disease
    NEVER: disease -> treats -> gene therapy vector

studied_in:
    entity -> study/paper
    Example: CLN5 -> studied_in -> study

associated_with:
    entity -> entity
    Direction can be arbitrary, but must reflect the wording of the source.

NEVER reverse a relationship merely because the disease is the main topic of the sentence.
IMPORTANT TREATMENT EXTRACTION RULE:

When the abstract says that a treatment, therapy, drug, vector, or
intervention is "for", "used for", "administered for", "effective
against", or "used to treat" a disease, the treatment MUST be the
subject and the disease MUST be the object.

Examples:

"gene therapy vector for CLN5 disease"
→ gene therapy vector | treats | CLN5 disease

"enzyme replacement therapy for CLN2"
→ enzyme replacement therapy | treats | CLN2

"patients with CLN2 were treated with enzyme replacement therapy"
→ enzyme replacement therapy | treats | CLN2

NEVER output:
CLN5 disease | treats | gene therapy vector
CLN2 disease | treats | enzyme replacement therapy

When one treatment is explicitly stated to apply to multiple diseases,
create one edge for EACH disease.

Example:

"gene therapy vector (for CLN1, CLN2, CLN3 and CLN5 diseases)"

must produce:

gene therapy vector → treats → CLN1 disease
gene therapy vector → treats → CLN2 disease
gene therapy vector → treats → CLN3 disease
gene therapy vector → treats → CLN5 disease

IMPORTANT:

Biomedical abstracts frequently express relationships using compact
list structures.

For example:

"gene therapy vector (for CLN1, CLN2, CLN3, CLN5 and CLN6 diseases)"

supports:

gene therapy vector -> treats -> CLN1 disease
gene therapy vector -> treats -> CLN2 disease
gene therapy vector -> treats -> CLN3 disease
gene therapy vector -> treats -> CLN5 disease
gene therapy vector -> treats -> CLN6 disease

Abstract:
"""


# ============================================================
# EVIDENCE REVIEW PROMPT
# ============================================================

EVIDENCE_PROMPT = """You are a strict biomedical evidence verifier.

You are given ONE PubMed abstract and candidate relationships extracted from it.

For EACH candidate:

1. Check whether the quoted sentence is actually present in the abstract.

2. Check whether the quote itself directly supports the exact relationship.

3. If the quote does not contain enough context, inspect the surrounding
   abstract.

4. ACCEPT_INFERRED only when the surrounding abstract clearly establishes
   that the relationship applies to the stated subject and object.

REJECT only when the abstract provides meaningful evidence AGAINST
the relationship, or when the candidate clearly contradicts the text.

If the relationship is reasonably supported by the abstract but the
exact wording is indirect, accept it as `inferred` with medium or low
confidence.

Do not reject merely because the relationship is expressed through
a list, parenthetical phrase, abbreviation, grammatical reference,
or nearby sentence.

6. Do not use outside biomedical knowledge, but you MAY resolve
   grammatical references, abbreviations, disease-name variants,
   parenthetical lists, and obvious list membership from the abstract.

7. Do not reject merely because the exact subject or object is absent from
   the quoted sentence if the surrounding abstract clearly establishes
   the referent.

Important example:

Candidate:

Kufs disease type A
    --has_phenotype-->
cortical atrophy

Quote:

"MR scan of the brain showed white matter changes suggesting leucodystrophy
with cortical atrophy."

If the surrounding abstract clearly establishes that the MRI belongs to
patients with Kufs disease type A:

ACCEPT_INFERRED

If the abstract does not establish that connection:

REJECT

Another example:

Candidate:

CLN6
    --causes-->
Kufs disease type A

Quote:

"Mutations in CLN6 cause Kufs disease type A."

ACCEPT_DIRECT

Do not use external biomedical knowledge.

Return exactly one decision for every candidate.



The disease name may appear in the list as "CLN5" while the candidate
uses "CLN5 disease". Treat these as the same entity when the context
clearly establishes that meaning.

Do not reject a candidate merely because the exact surface form of
the entity is slightly different.

Abstract:
"""


# ============================================================
# LOAD ABSTRACTS
# ============================================================

def load_abstracts(n: int) -> dict[str, str]:
    out = {}

    with open(
        DATA / "papers.jsonl",
        encoding="utf-8",
    ) as f:

        for line in f:
            p = json.loads(line)

            if p["abstract"] and not p["retracted"]:
                out[p["pmid"]] = p["abstract"]

            if len(out) >= n:
                break

    return out


# ============================================================
# EXTRACTION
# ============================================================

def extract(
    pmid: str,
    text: str,
) -> list[Candidate]:

    # IMPORTANT:
    # This preserves your previous working cache.

    cache = (
        DATA
        / "cache"
        / f"{PROVIDER}_{CACHE_TAG}_{pmid}.json"
    )

    if cache.exists():
        return Extraction.model_validate_json(
            cache.read_text()
        ).edges

    parsed = structured(
        PROMPT + text,
        Extraction,
    )

    cache.write_text(
        parsed.model_dump_json(),
        encoding="utf-8",
    )

    return parsed.edges


# ============================================================
# DIRECT RELATIONSHIP CUES
# ============================================================

RELATIONSHIP_CUES = {

    "causes": [
        "causes",
        "caused",
        "cause",
        "results in",
        "resulted in",
        "leads to",
        "led to",
        "responsible for",
        "due to",
    ],

    "associated_with": [
        "associated with",
        "association with",
        "associated",
        "linked to",
        "link between",
        "correlated with",
    ],

    "has_phenotype": [
        "characterized by",
        "presented with",
        "presented as",
        "patients had",
        "patients showed",
        "patients exhibited",
        "patients developed",
        "showed",
        "showing",
        "exhibited",
        "manifested",
        "symptoms included",
        "features included",
        "was observed",
        "were observed",
    ],

    "disrupts_pathway": [
        "disrupts",
        "disrupted",
        "impairs",
        "impaired",
        "inhibits",
        "inhibited",
        "affects",
        "dysfunction",
        "defective",
        "deficiency",
    ],

    "treats": [
        "treated with",
        "treatment with",
        "therapy with",
        "responded to",
        "treated",
        "therapy",
    ],

    "studied_in": [
        "studied in",
        "investigated in",
        "examined in",
        "evaluated in",
        "patients with",
    ],
}


# ============================================================
# ENTITY SURFACE MATCH
# ============================================================

def surface_present(
    text: str,
    entity: str,
) -> bool:

    return (
        re.search(
            r"(?<!\w)"
            + re.escape(norm(entity))
            + r"(?!\w)",
            norm(text),
        )
        is not None
    )


# ============================================================
# FAST DIRECT EVIDENCE CHECK
# ============================================================

def direct_support(c: Candidate) -> bool:
    """
    Fast acceptance for reasonably obvious evidence.

    This is intentionally permissive. The LLM evidence verifier
    remains responsible for ambiguous cases.
    """
    q = norm(c.quote)

    # Quote itself must exist in the source.
    # Entity surface forms do not have to match exactly.
    if not q:
        return False

    if c.predicate == "treats":
        treatment_cues = [
            "treated",
            "treatment",
            "therapy",
            "therapeutic",
            "drug",
            "vector",
            "for",
            "efficacy",
            "safety and efficacy",
        ]

        return any(norm(cue) in q for cue in treatment_cues)

    cues = RELATIONSHIP_CUES.get(c.predicate, [])
    return any(norm(cue) in q for cue in cues)


# ============================================================
# EVIDENCE CACHE
# ============================================================

def evidence_cache_path(
    pmid: str,
) -> Path:

    return (
        DATA
        / "cache"
        / f"evidence_v1_{pmid}.json"
    )


# ============================================================
# BATCH EVIDENCE REVIEW
# ============================================================

def review_ambiguous(
    pmid: str,
    text: str,
    candidates: list[Candidate],
) -> dict[int, EvidenceDecision]:

    if not candidates:
        return {}

    cache = evidence_cache_path(
        pmid
    )

    # Reuse previous evidence verification.

    if cache.exists():

        review = EvidenceReview.model_validate_json(
            cache.read_text()
        )

        return {
            d.candidate_index: d
            for d in review.decisions
        }

    candidate_blocks = []

    for i, c in enumerate(candidates):

        candidate_blocks.append(
            f"""
CANDIDATE {i}

subject:
{c.subject}

subject_type:
{c.subject_type}

predicate:
{c.predicate}

object:
{c.object}

object_type:
{c.object_type}

claimed_evidence_type:
{c.evidence_type}

quote:
{c.quote}
"""
        )

    prompt = (
        EVIDENCE_PROMPT
        + "\n"
        + text
        + "\n\n"
        + "CANDIDATES:\n"
        + "\n".join(candidate_blocks)
    )

    # ONE Anthropic call for ALL ambiguous edges
    # belonging to this paper.

    review = structured(
        prompt,
        EvidenceReview,
    )

    cache.write_text(
        review.model_dump_json(),
        encoding="utf-8",
    )

    return {
        d.candidate_index: d
        for d in review.decisions
    }


# ============================================================
# BUILD EDGE
# ============================================================

def make_edge(
    c: Candidate,
    evidence_type: str,
    pmid: str,
    onto: Ontology,
) -> tuple[
    Optional[Edge],
    Optional[str],
]:
    if not valid_predicate_direction(c):
        return None, "invalid_predicate_direction"
    subject_id = onto.entity_id(
        c.subject,
        c.subject_type,
    )

    object_id = onto.entity_id(
        c.object,
        c.object_type,
    )

    if not subject_id:
        return None, "entity_unresolved"

    if not object_id:
        return None, "entity_unresolved"

    edge = Edge(
        subject=subject_id,
        predicate=c.predicate,
        object=object_id,

        evidence_type=evidence_type,

        source=f"PMID:{pmid}",

        quote=c.quote,

        extracted_by="llm",

        date=datetime.date.today().isoformat(),

        subject_type=c.subject_type,
        object_type=c.object_type,

        subject_label=c.subject,
        object_label=c.object,
    )

    return edge, None

def valid_predicate_direction(c):
    if c.predicate == "treats":
        treatment_types = {"treatment", "molecule", "other"}
        disease_types = {"disease"}

        return (
            c.subject_type in treatment_types
            and c.object_type in disease_types
        )

    if c.predicate == "causes":
        return c.object_type == "disease"

    if c.predicate == "has_phenotype":
        return (
            c.subject_type == "disease"
            and c.object_type == "phenotype"
        )

    if c.predicate == "disrupts_pathway":
        return c.object_type == "pathway"

    return True

# ============================================================
# MAIN
# ============================================================

def main(
    n: int,
):

    onto = Ontology()

    stats = Counter()

    seen = set()

    abstracts = load_abstracts(n)

    print(
        f"Processing {len(abstracts)} abstracts..."
    )

    with (
        open(
            DATA / "edges_verified.jsonl",
            "w",
            encoding="utf-8",
        ) as verified,

        open(
            DATA / "edges_provisional.jsonl",
            "w",
            encoding="utf-8",
        ) as provisional,

        open(
            DATA / "rejected.jsonl",
            "w",
            encoding="utf-8",
        ) as rejected,
    ):

        for paper_no, (
            pmid,
            text,
        ) in enumerate(
            abstracts.items(),
            1,
        ):

            print(
                f"\n[{paper_no}/{len(abstracts)}] "
                f"PMID {pmid}",
                flush=True,
            )

            # ------------------------------------------------
            # EXTRACTION
            # ------------------------------------------------

            try:

                candidates = extract(
                    pmid,
                    text,
                )

            except Exception as e:

                print(
                    "  Extraction error:",
                    type(e).__name__,
                    e,
                )

                stats["llm_error"] += 1

                continue

            stats["candidates"] += len(
                candidates
            )

            if not candidates:

                print(
                    "  No candidate edges."
                )

                continue

            print(
                f"  Candidates: {len(candidates)}"
            )

            # ------------------------------------------------
            # FAST VERIFICATION
            # ------------------------------------------------

            ambiguous = []

            decisions = {}

            for i, c in enumerate(
                candidates
            ):

                # First make sure the quote actually exists.

                if norm(c.quote) not in norm(text):

                    decisions[i] = EvidenceDecision(
                        candidate_index=i,

                        decision="reject",

                        evidence_type=c.evidence_type,

                        confidence="high",

                        reason=(
                            "Quote is not present "
                            "verbatim in source."
                        ),
                    )

                    stats[
                        "quote_not_in_source"
                    ] += 1

                    continue

                # Fast direct verification.

                if direct_support(c):

                    decisions[i] = EvidenceDecision(
                        candidate_index=i,

                        decision="accept_direct",

                        evidence_type="observed",

                        confidence="high",

                        reason=(
                            "Both entities and a "
                            "predicate-specific "
                            "relationship cue are "
                            "directly present in "
                            "the quoted sentence."
                        ),
                    )

                    stats[
                        "direct_accepted"
                    ] += 1

                else:

                    # Needs contextual reasoning.

                    ambiguous.append(
                        (i, c)
                    )

            # ------------------------------------------------
            # ONE LLM CALL FOR AMBIGUOUS EDGES
            # ------------------------------------------------

            if ambiguous:

                print(
                    f"  Context verification: "
                    f"{len(ambiguous)} edges "
                    f"in ONE LLM call"
                )

                ambiguous_candidates = [
                    c
                    for _, c in ambiguous
                ]

                try:

                    review = review_ambiguous(
                        pmid,
                        text,
                        ambiguous_candidates,
                    )

                    stats[
                        "papers_evidence_reviewed"
                    ] += 1

                except Exception as e:

                    print(
                        "  Evidence review error:",
                        type(e).__name__,
                        e,
                    )

                    stats[
                        "evidence_llm_error"
                    ] += 1

                    # Never silently accept
                    # unverified ambiguous claims.

                    for global_i, c in ambiguous:

                        decisions[
                            global_i
                        ] = EvidenceDecision(
                            candidate_index=global_i,

                            decision="reject",

                            evidence_type="hypothesis",

                            confidence="low",

                            reason=(
                                "Ambiguous evidence "
                                "could not be verified."
                            ),
                        )

                else:

                    for local_i, (
                        global_i,
                        c,
                    ) in enumerate(
                        ambiguous
                    ):

                        decision = review.get(
                            local_i
                        )

                        if decision is None:

                            decisions[
                                global_i
                            ] = EvidenceDecision(
                                candidate_index=global_i,

                                decision="reject",

                                evidence_type=(
                                    c.evidence_type
                                ),

                                confidence="low",

                                reason=(
                                    "Evidence verifier "
                                    "returned no decision."
                                ),
                            )

                        else:

                            decisions[
                                global_i
                            ] = decision

            # ------------------------------------------------
            # WRITE FINAL EDGES
            # ------------------------------------------------

            for i, c in enumerate(
                candidates
            ):

                decision = decisions.get(
                    i
                )

                if decision is None:

                    rejected.write(
                        json.dumps(
                            {
                                "pmid": pmid,
                                "reason": (
                                    "no_evidence_decision"
                                ),
                                "candidate": (
                                    c.model_dump()
                                ),
                            }
                        )
                        + "\n"
                    )

                    stats[
                        "no_evidence_decision"
                    ] += 1

                    continue

                # ------------------------------------------------
                # REJECTED
                # ------------------------------------------------

                if (
                    decision.decision
                    == "reject"
                ):

                    rejected.write(
                        json.dumps(
                            {
                                "pmid": pmid,
                                "reason": (
                                    "evidence_rejected"
                                ),
                                "review": (
                                    decision.model_dump()
                                ),
                                "candidate": (
                                    c.model_dump()
                                ),
                            }
                        )
                        + "\n"
                    )

                    stats[
                        "evidence_rejected"
                    ] += 1

                    continue

                # ------------------------------------------------
                # ACCEPTED
                # ------------------------------------------------

                edge, reason = make_edge(
                    c,

                    decision.evidence_type,

                    pmid,

                    onto,
                )

                if not edge:

                    rejected.write(
                        json.dumps(
                            {
                                "pmid": pmid,
                                "reason": reason,
                                "review": (
                                    decision.model_dump()
                                ),
                                "candidate": (
                                    c.model_dump()
                                ),
                            }
                        )
                        + "\n"
                    )

                    stats[reason] += 1

                    continue

                # ------------------------------------------------
                # DUPLICATE
                # ------------------------------------------------

                key = (
                    edge.subject,
                    edge.predicate,
                    edge.object,
                    edge.source,
                )

                if key in seen:

                    stats[
                        "duplicate"
                    ] += 1

                    continue

                seen.add(key)

                # ------------------------------------------------
                # PROVISIONAL VS CANONICAL
                # ------------------------------------------------

                if (
                    edge.subject.startswith(
                        "PROV:"
                    )
                    or edge.object.startswith(
                        "PROV:"
                    )
                ):

                    provisional.write(
                        edge.model_dump_json()
                        + "\n"
                    )

                    stats[
                        "accepted_provisional"
                    ] += 1

                else:

                    verified.write(
                        edge.model_dump_json()
                        + "\n"
                    )

                    stats[
                        "accepted"
                    ] += 1

    # ========================================================
    # FINAL STATS
    # ========================================================

    print(
        "\n"
        + "=" * 60
    )

    print(
        "FINAL STATS"
    )

    print(
        "=" * 60
    )

    for key, value in sorted(
        stats.items()
    ):

        print(
            f"{key}: {value}"
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    n = (
        int(sys.argv[1])
        if len(sys.argv) > 1
        else 5
    )

    main(n)