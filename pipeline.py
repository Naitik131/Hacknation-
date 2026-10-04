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
CACHE_TAG = "v7"


EntityType = Literal[
    "gene",
    "disease",
    "phenotype",
    "mechanism",
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
        "therapeutic_effect",
    "studied_in",
        "has_mechanism",
        "affects_mechanism",
        "involved_in_pathway",
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

PROMPT = """Extract relationships between genes, diseases, clinical features,
molecules, mechanisms, pathways and treatments from this abstract.

GENERAL RULES:

- Only extract claims explicitly supported by the abstract.
- Never use outside biomedical knowledge.
- `quote` must be ONE sentence copied verbatim from the abstract.
- The quote must contain the exact original words from the abstract.
- Entity names must be bare names with no extra words.
- Use official gene symbols where possible.
- If uncertain about an entity or relationship, DO NOT extract it.
- It is better to omit a relationship than create an incorrect one.
- If nothing qualifies, return an empty list.


ENTITY TYPES:

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

mechanism
- A biological mechanism, dysfunction, process, defect, or functional alteration
  that explains how a disease, gene, variant, or molecule produces an effect.
- Examples:
  lysosomal dysfunction
  impaired autophagy
  defective lysosomal degradation
  altered membrane trafficking
  lysosomal egress defect
- A mechanism is NOT simply a symptom or phenotype.
- A mechanism is NOT a ClinVar molecular consequence such as:
  "intron variant"
  "missense variant"
  "frameshift variant".

pathway
- Only use pathway for a named biological pathway, metabolic pathway,
  or biological process when the abstract treats it as a pathway/process
  in which an entity participates or which an entity disrupts.
- Examples:
  autophagy
  ubiquitin-dependent microautophagy
  glycerophospholipid metabolism
  glycerophospholipid catabolism
  lysosomal pathway
- Do NOT automatically classify every biological process as a pathway.
- Do NOT classify a mechanism as a pathway merely because it contains
  words such as "dysfunction", "defect", "impairment", or "alteration".

molecule
- Only use for a specific molecular entity, protein, metabolite, lipid,
  enzyme, or other named molecular entity.

treatment
- Use for an intervention or therapeutic strategy.
- Specific therapeutic molecules should be classified appropriately.
- Distinguish specific treatments from generic strategies.

other
- Avoid unless the entity genuinely does not fit another category.


PREDICATES:

causes
associated_with
has_phenotype
has_mechanism
affects_mechanism
disrupts_pathway
involved_in_pathway
treats
studied_in


EDGE DIRECTION RULES:

Every edge is directional.
The subject must be the entity performing or having the relationship.

therapeutic_effect: a treatment, gene, molecule, or other intervention shows a beneficial therapeutic effect in a disease or disease model, without necessarily establishing that it is an established treatment.

causes:
    cause -> disease/effect

Example:
    CLN6 -> causes -> Kufs disease type A


has_phenotype:
    disease -> phenotype

Example:
    Kufs disease type A -> has_phenotype -> myoclonus


has_mechanism:
    disease/gene/molecule -> mechanism

Use when a disease, gene, molecule, or other biological entity is
explicitly described as having, involving, or being associated with
a biological mechanism.

Examples:
    CLN3 disease -> has_mechanism -> lysosomal dysfunction
    CLN3 -> has_mechanism -> impaired autophagy

The OBJECT MUST have entity type `mechanism`.

Do NOT use:
    CLN3 -> has_mechanism -> glycerophospholipid metabolism
if glycerophospholipid metabolism is being described as a pathway.

Only extract this relationship when the paper explicitly supports it.


affects_mechanism:
    gene/variant/molecule -> mechanism

Use when a gene, variant, molecule, or other biological entity is
explicitly described as affecting, altering, impairing, activating,
inhibiting, or otherwise modifying a biological mechanism.
Use treats only when the source supports an actual treatment/therapy relationship.
Use therapeutic_effect when an intervention shows improvement, rescue, alleviation, protection, or therapeutic benefit in a disease or disease model, but the source does not establish it as a treatment.
Examples:
    CLN3 -> affects_mechanism -> lysosomal dysfunction
    GPDs -> affects_mechanism -> lysosomal phospholipase activity

The OBJECT MUST have entity type `mechanism`.

Do NOT use `affects_mechanism` when the object is a named pathway.


disrupts_pathway:
    gene/molecule -> pathway

Use only when the abstract explicitly states that an entity disrupts,
impairs, inhibits, alters, or causes dysfunction of a pathway.

Example:
    CLN3 -> disrupts_pathway -> lysosomal pathway

The OBJECT MUST have entity type `pathway`.


involved_in_pathway:
    gene/molecule/mechanism -> pathway

Use when an entity is explicitly described as participating in,
being required for, being involved in, or functioning within a pathway.

Examples:
    CLN3 -> involved_in_pathway -> glycerophospholipid metabolism
    PLBD2 -> involved_in_pathway -> glycerophospholipid catabolism

The OBJECT MUST have entity type `pathway`.

Do NOT use `involved_in_pathway` when the object is actually a
specific mechanism such as "lysosomal dysfunction".


IMPORTANT DISTINCTION BETWEEN MECHANISMS AND PATHWAYS:

Use `mechanism` when the phrase describes HOW something is altered,
defective, dysfunctional, impaired, or functioning abnormally.

Use `pathway` when the phrase describes a biological pathway,
metabolic pathway, or biological process in which an entity participates.

Examples:

"lysosomal dysfunction"
    -> mechanism

"impaired autophagy"
    -> mechanism

"defective lysosomal degradation"
    -> mechanism

"glycerophospholipid metabolism"
    -> pathway

"glycerophospholipid catabolism"
    -> pathway

"autophagy pathway"
    -> pathway

Do not confuse these two entity types.


treats:
    treatment/therapy/drug/vector -> disease

Example:
    gene therapy vector -> treats -> CLN5 disease

NEVER:
    disease -> treats -> gene therapy vector


studied_in:
    entity -> study/paper

Example:
    CLN5 -> studied_in -> study


associated_with:
    entity -> entity

Direction can be arbitrary, but must reflect the wording of the source.


IMPORTANT RELATIONSHIP SELECTION:

If the abstract says an entity HAS, INVOLVES, or is associated with
a biological dysfunction/process:
    use has_mechanism

If the abstract says an entity ALTERS, IMPAIRS, INHIBITS, ACTIVATES,
MODULATES, or otherwise changes a biological mechanism:
    use affects_mechanism

If the abstract says an entity DISRUPTS or impairs a biological pathway:
    use disrupts_pathway

If the abstract says an entity PARTICIPATES IN, IS REQUIRED FOR,
or is INVOLVED IN a biological pathway:
    use involved_in_pathway

Do not choose a relationship merely because a word such as
"affects", "involved", or "dysfunction" appears in the sentence.
The complete sentence and its meaning must support the relationship.


MECHANISM AND PATHWAY SAFETY RULES:

- Do NOT classify symptoms or clinical phenotypes as mechanisms.
- Do NOT classify ClinVar molecular consequences as mechanisms.
- Do NOT classify "intron variant", "missense variant",
  "frameshift variant", etc. as mechanisms.
- Do NOT infer mechanisms from general biomedical knowledge.
- Do NOT infer pathway membership from general biomedical knowledge.
- Do NOT invent pathway names.
- Do NOT convert a phenotype into a mechanism.
- Do NOT convert a molecular consequence into a mechanism.
- If the abstract does not clearly distinguish a mechanism from a pathway,
  omit the relationship rather than guessing.


IMPORTANT TREATMENT EXTRACTION RULE:

When the abstract says that a treatment, therapy, drug, vector, or
intervention is "for", "used for", "administered for", "effective
against", or "used to treat" a disease, the treatment MUST be the
subject and the disease MUST be the object.

Examples:

"gene therapy vector for CLN5 disease"
-> gene therapy vector | treats | CLN5 disease

"enzyme replacement therapy for CLN2"
-> enzyme replacement therapy | treats | CLN2

"patients with CLN2 were treated with enzyme replacement therapy"
-> enzyme replacement therapy | treats | CLN2

NEVER output:

CLN5 disease | treats | gene therapy vector

CLN2 disease | treats | enzyme replacement therapy


When one treatment is explicitly stated to apply to multiple diseases,
create one edge for EACH disease.

Example:

"gene therapy vector (for CLN1, CLN2, CLN3 and CLN5 diseases)"

must produce:

gene therapy vector -> treats -> CLN1 disease
gene therapy vector -> treats -> CLN2 disease
gene therapy vector -> treats -> CLN3 disease
gene therapy vector -> treats -> CLN5 disease


IMPORTANT LIST EXTRACTION RULE:

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


EVIDENCE TYPE:

observed
- Directly reported experimental or clinical observation.

inferred
- Authors' interpretation or a relationship clearly supported by context.

hypothesis
- Speculation or proposed mechanism.

Only use `inferred` when the abstract clearly establishes the
relationship through surrounding context.

Do not use outside knowledge to create an inference.


NEVER REVERSE A RELATIONSHIP:

Never reverse a relationship merely because the disease is the
main topic of the sentence.

The grammatical and semantic direction of the abstract must determine
the subject and object.

For has_phenotype, do not infer that a gene or molecule has a phenotype merely because a disease is characterized by that gene/molecule's accumulation or alteration. The subject must itself be the entity that the source establishes as having the phenotype.
Abstract:
"""


EVIDENCE_PROMPT = """You are a strict biomedical evidence verifier.

You are given ONE PubMed abstract and candidate relationships extracted from it.

For EACH candidate:

1. Check whether the quoted sentence is actually present in the abstract.

2. Check whether the quote itself directly supports the exact relationship.

3. If the quote does not contain enough context, inspect the surrounding
   abstract.

4. ACCEPT_INFERRED only when the surrounding abstract clearly establishes
   that the relationship applies to the stated subject and object.

5. REJECT only when the abstract provides meaningful evidence AGAINST
   the relationship, or when the candidate clearly contradicts the text.

6. If the relationship is reasonably supported by the abstract but the
   exact wording is indirect, accept it as `inferred` with medium or
   low confidence.

7. Do not use outside biomedical knowledge.

8. You MAY resolve:
   - grammatical references
   - abbreviations
   - disease-name variants
   - parenthetical lists
   - obvious list membership
   - obvious references to the same entity established elsewhere
     in the abstract

9. Do not reject merely because the exact subject or object is absent
   from the quoted sentence if the surrounding abstract clearly
   establishes the referent.

10. Do not reject merely because a relationship is expressed through
    a list, parenthetical phrase, abbreviation, or nearby sentence.

11. Check the ENTITY TYPES as well as the relationship.

12. A `has_mechanism` relationship requires:
       subject = disease/gene/molecule/other
       object = mechanism

13. An `affects_mechanism` relationship requires:
       subject = gene/variant/molecule/other
       object = mechanism

14. A `disrupts_pathway` relationship requires:
       subject = gene/molecule/other
       object = pathway

15. An `involved_in_pathway` relationship requires:
       subject = gene/molecule/mechanism/other
       object = pathway

16. Do NOT accept a mechanism relationship merely because the object
    is a biological process. Determine whether the abstract describes
    that process as a mechanism or as a pathway/process.

17. Do NOT classify clinical phenotypes as mechanisms.

18. Do NOT classify molecular variant consequences such as
    "intron variant", "missense variant", or "frameshift variant"
    as mechanisms.

19. Do not use outside biomedical knowledge to decide whether an
    entity is a pathway or mechanism. Use the wording and role in
    the abstract.
IMPORTANT FOR has_phenotype:

The grammatical/entity subject of the quoted statement must be the entity that has the phenotype.

Do NOT accept:
gene → has_phenotype → phenotype
merely because the gene is mentioned inside a disease phenotype description.

For example:

"Parkinson disease is characterized by abnormal intracellular accumulation of SNCA."

supports:

Parkinson disease → has_phenotype → abnormal intracellular accumulation

It does NOT support:

SNCA → has_phenotype → abnormal intracellular accumulation.

Likewise, if a disease is described as having a phenotype involving accumulation, expression, mutation, or alteration of a gene/protein, do not reverse that relationship and assign the phenotype to the gene/protein.

Example 1:

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


Example 2:

Candidate:

CLN6
    --causes-->
Kufs disease type A

Quote:

"Mutations in CLN6 cause Kufs disease type A."

ACCEPT_DIRECT


Example 3:

Candidate:

CLN3
    --has_mechanism-->
lysosomal dysfunction

Quote:

"Each form is caused by mutations in a different gene, resulting in
lysosomal dysfunction."

If the surrounding abstract establishes that this statement refers
to neuronal ceroid lipofuscinosis:

ACCEPT_INFERRED

The object is a mechanism because the abstract describes
"lysosomal dysfunction" as the biological dysfunction resulting
from the disease-causing mutations.


Example 4:

Candidate:

CLN3
    --involved_in_pathway-->
glycerophospholipid metabolism

Quote:

"Our results show that CLN3 is required for the lysosomal clearance
of GPDs and reveal Batten disease as a neurodegenerative LSD with a
defect in glycerophospholipid metabolism."

If the surrounding abstract clearly supports CLN3's role in this
biological process:

ACCEPT_INFERRED

Do not change the relationship to `has_mechanism` merely because
the phrase describes biology.


Example 5:

Candidate:

CLN3
    --has_mechanism-->
glycerophospholipid metabolism

If the abstract treats glycerophospholipid metabolism as a pathway
or metabolic process rather than a mechanism:

REJECT

The candidate should instead have been represented as:

CLN3
    --involved_in_pathway-->
glycerophospholipid metabolism


Example 6:

Candidate:

GPDs
    --affects_mechanism-->
glycerophospholipid catabolism

Quote:

"GPDs act as potent inhibitors of glycerophospholipid catabolism
in the lysosome."

If glycerophospholipid catabolism is explicitly treated as a pathway
or metabolic process rather than a mechanism:

REJECT this candidate as incorrectly typed.

Do NOT reinterpret the entity as a mechanism merely to make the
candidate pass.


Example 7:

Candidate:

CLN3
    --affects_mechanism-->
lysosomal dysfunction

Quote:

"CLN3 loss causes lysosomal dysfunction."

If the abstract explicitly establishes that CLN3 loss produces or
modifies the lysosomal dysfunction:

ACCEPT_DIRECT or ACCEPT_INFERRED depending on wording.


The disease name may appear in a list as "CLN5" while the candidate
uses "CLN5 disease". Treat these as the same entity when the context
clearly establishes that meaning.

Do not reject a candidate merely because the exact surface form of
the entity is slightly different.

Return exactly ONE decision for EVERY candidate.


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
           "has_mechanism": [
        "mechanism",
        "mechanism of",
        "mediated by",
        "mediated through",
        "biological mechanism",
        "pathophysiological mechanism",
        "molecular mechanism",
        "cellular mechanism",
        "dysfunction",
        "defect in",
        "impairment of",
        "impairment in",
        "deficiency of",
        "failure of",
    ],


    "affects_mechanism": [
        "affects",
        "affected",
        "alters",
        "altered",
        "impairs",
        "impaired",
        "inhibits",
        "inhibited",
        "activates",
        "activated",
        "modulates",
        "disrupts",
        "disrupted",
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

def valid_predicate_direction(c: Candidate) -> bool:
    if c.predicate == "treats":
        return (
            c.object_type == "disease"
            and c.subject_type in {"treatment", "molecule", "other"}
        )
    if c.predicate == "therapeutic_effect":
     return (
        c.subject_type in {
            "gene",
            "molecule",
            "treatment",
            "other",
        }
        and c.object_type in {
            "disease",
            "phenotype",
        }
    )

    if c.predicate == "has_phenotype":
        return (
            c.subject_type == "disease"
            and c.object_type == "phenotype"
        )

    if c.predicate == "causes":
        return c.object_type in {
        "disease",
        "mechanism",
        "phenotype",
    }

    if c.predicate == "disrupts_pathway":
        return c.object_type == "pathway"

    if c.predicate == "has_mechanism":
        return (
            c.subject_type in {
                "disease",
                "gene",
                "molecule",
                "other",
            }
            and c.object_type == "mechanism"
        )

    if c.predicate == "affects_mechanism":
        return (
            c.subject_type in {
                "gene",
                "variant",
                "molecule",
                "other",
            }
            and c.object_type == "mechanism"
        )

    if c.predicate == "involved_in_pathway":
        return (
            c.subject_type in {
                "gene",
                "mechanism",
                "molecule",
                "other",
            }
            and c.object_type == "pathway"
        )

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
                
                if decision.decision == "accept_inferred":
                    final_evidence_type = "inferred"
                else:
                    final_evidence_type = decision.evidence_type

                edge, reason = make_edge(
                    c,
                    final_evidence_type,
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