"""Graph schema. Rule: no source, no edge."""
from typing import Literal, Optional
from pydantic import BaseModel, Field

NodeType = Literal[
    "disease", "gene", "variant", "mechanism", "phenotype",
    "patient_group", "organization", "paper", "study", "asset",
    "person", "grant", "topic"
]

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
    "tagged_with",
    "has_variant",
    "variant_in_gene",
    "variant_associated_with",
    "has_molecular_consequence",
    "involved_in_pathway",
    "has_mechanism",
    "affects_mechanism",
    "led_by",
    "has_registry",
    "conducted_at",
    "supported_by",
]


class Node(BaseModel):
    id: str
    type: NodeType
    label: str
    synonyms: list[str] = Field(default_factory=list)
    attrs: dict = Field(default_factory=dict)


class Edge(BaseModel):
    subject: str
    predicate: Predicate
    object: str
    evidence_type: EvidenceType
    source: str
    quote: Optional[str] = None
    extracted_by: Literal["parser", "llm"]
    date: str
    confidence: Optional[float] = None
    contradicted_by: list[str] = Field(default_factory=list)
    subject_type: Optional[str] = None
    object_type: Optional[str] = None
    subject_label: Optional[str] = None
    object_label: Optional[str] = None
