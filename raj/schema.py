"""Graph schema. Rule: no source, no edge."""
from typing import Literal, Optional
from pydantic import BaseModel, Field

NodeType = Literal["disease", "gene", "variant", "mechanism", "phenotype",
                   "patient_group", "paper", "study", "asset", "person",
                   "grant", "topic"]
EvidenceType = Literal["observed", "inferred", "hypothesis"]
Predicate = Literal[
    "causes",
    "associated_with",
    "has_phenotype",
    "disrupts_pathway",
    "treats",
    "studied_in",
    "involves_intervention",
    "tests",
    "authored",
    "funded_by",
    "reports_trial",
    "tagged_with"
]


class Node(BaseModel):
    id: str                       # stable ID: MONDO:..., HGNC:..., HP:..., PMID:...
    type: NodeType
    label: str
    synonyms: list[str] = Field(default_factory=list)
    attrs: dict = Field(default_factory=dict)  # year, journal, affiliation, id_basis...


class Edge(BaseModel):
    subject: str                  # node id
    predicate: Predicate
    object: str                   # node id
    evidence_type: EvidenceType   # observed / inferred / hypothesis
    source: str                   # PMID:..., NCT..., or URL (required)
    quote: Optional[str] = None   # verbatim sentence; required when extracted_by="llm"
    extracted_by: Literal["parser", "llm"]
    date: str                     # retrieval date
    confidence: Optional[float] = None  # computed later from cross-checks, never guessed
    contradicted_by: list[str] = Field(default_factory=list)  # edge keys / sources
    # as written in the source text; ids starting "PROV:" are not yet ontology-grounded
    subject_type: Optional[str] = None
    object_type: Optional[str] = None
    subject_label: Optional[str] = None
    object_label: Optional[str] = None
