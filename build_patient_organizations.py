"""Build a sourced patient-organization layer for the NCL knowledge graph.

Only organizations explicitly listed by Orphanet or GeneReviews are included.
No organization-to-disease relationship is inferred beyond the disease scope
stated by the source.
"""

import json
from pathlib import Path
from datetime import date

DATA = Path("data")
OUT_NODES = DATA / "patient_organization_nodes.jsonl"
OUT_EDGES = DATA / "patient_organization_edges.jsonl"

ORPHANET_SOURCE = "https://www.orpha.net/en/patient-organisations?diseaseName=Neuronal+ceroid+lipofuscinosis&orphaCode=216"
GENEREVIEWS_SOURCE = "https://www.ncbi.nlm.nih.gov/books/NBK1428/"
CLN3_GENEREVIEWS_SOURCE = "https://www.ncbi.nlm.nih.gov/books/NBK624593/"

NCL = "MONDO:0016295"
CLN3 = "MONDO:0008767"

# The 12 organizations explicitly listed by Orphanet for neuronal ceroid lipofuscinosis.
ORPHANET_ORGS = [
    ("Suomen JNCL-perheiden tukiyhdistys ry", "Finland"),
    ("Suomen INCL-yhdistys ry - INCL Föreningen Finnish INCL Association", "Finland"),
    ("NCL-Gruppe Deutschland e.V.", "Germany"),
    ("NCL-NÄCHSTENLIEBE e.V.", "Germany"),
    ("Bee for Battens", "Ireland"),
    ("A-NCL - Associazione Nazionale Ceroidolipofuscinosi", "Italy"),
    ("Norsk NCL-forening Norwegian NCL Association", "Norway"),
    ("AHEDYSIA: Asociación Humanitaria de Enfermedades Degenerativas y Síndromes de la Infancia y Adolescencia", "Spain"),
    ("AEFAL: Asociación para el apoyo e investigación de la enfermedad de ceroidolipofuscinosis", "Spain"),
    ("Svenska Spielmeyer-Vogt Föreningen", "Sweden"),
    ("Svenska NCL föreningen", "Sweden"),
    ("BDFA UK - Batten Disease Family Association", "United Kingdom"),
]

# Additional patient/family organizations explicitly listed by GeneReviews.
# Beat Batten is scoped to CLN3 in the current GeneReviews entry.
GENEREVIEWS_ORGS = [
    ("Batten Disease Family Association (BDFA) UK", "United Kingdom", NCL, "all_ncl"),
    ("BDSRA Australia", "Australia", NCL, "all_ncl"),
    ("BDSRA Canada", "Canada", NCL, "all_ncl"),
    ("BDSRA Foundation (USA)", "United States", NCL, "all_ncl"),
    ("Courageous Parents Network", "United States", NCL, "all_ncl"),
    ("Beat Batten Foundation", "Netherlands", CLN3, "cln3"),
]

OFFICIAL_SITES = {
    "BDSRA Foundation (USA)": "https://bdsrafoundation.org/",
    "BDSRA Australia": "https://bdsraaustralia.org/",
    "BDSRA Canada": "https://battendisease.ca/",
    "BDFA UK - Batten Disease Family Association": "https://bdfa-uk.org.uk/",
    "Batten Disease Family Association (BDFA) UK": "https://bdfa-uk.org.uk/",
    "Beat Batten Foundation": "https://beatbatten.nl/",
}


def slug(value: str) -> str:
    import re
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def make_id(name: str) -> str:
    aliases = {
        "Batten Disease Family Association (BDFA) UK": "BDFA UK - Batten Disease Family Association",
    }
    canonical = aliases.get(name, name)
    return "PATIENT_GROUP:" + slug(canonical)


def make_node(name, country, source, scope="all_ncl"):
    node = {
        "id": make_id(name),
        "type": "patient_group",
        "label": name,
        "synonyms": [],
        "attrs": {
            "organization_category": "patient_organization",
            "country": country,
            "disease_scope": scope,
            "source": source,
            "source_type": "Orphanet" if "orpha.net" in source else "GeneReviews",
        },
    }
    if name in OFFICIAL_SITES:
        node["attrs"]["website"] = OFFICIAL_SITES[name]
    return node


nodes = {}
edges = []

# Orphanet list: all organizations are explicitly associated with NCL.
for name, country in ORPHANET_ORGS:
    node = make_node(name, country, ORPHANET_SOURCE)
    nodes[node["id"]] = node
    edges.append({
        "subject": NCL,
        "predicate": "supported_by",
        "object": node["id"],
        "evidence_type": "observed",
        "source": ORPHANET_SOURCE,
        "quote": None,
        "extracted_by": "parser",
        "date": date.today().isoformat(),
        "confidence": None,
        "contradicted_by": [],
        "subject_type": "disease",
        "object_type": "patient_group",
        "subject_label": "Neuronal Ceroid Lipofuscinoses",
        "object_label": name,
    })

# GeneReviews additions. Avoid duplicating BDFA already represented by Orphanet.
for name, country, disease_id, scope in GENEREVIEWS_ORGS:
    node = make_node(name, country, CLN3_GENEREVIEWS_SOURCE if scope == "cln3" else GENEREVIEWS_SOURCE, scope)
    nodes.setdefault(node["id"], node)
    source = node["attrs"]["source"]
    disease_label = "CLN3-related disorder" if disease_id == CLN3 else "Neuronal Ceroid Lipofuscinoses"
    edges.append({
        "subject": disease_id,
        "predicate": "supported_by",
        "object": node["id"],
        "evidence_type": "observed",
        "source": source,
        "quote": None,
        "extracted_by": "parser",
        "date": date.today().isoformat(),
        "confidence": None,
        "contradicted_by": [],
        "subject_type": "disease",
        "object_type": "patient_group",
        "subject_label": disease_label,
        "object_label": name,
    })

# Deduplicate edges by subject/predicate/object/source.
seen = set()
unique_edges = []
for edge in edges:
    key = (edge["subject"], edge["predicate"], edge["object"], edge["source"])
    if key not in seen:
        seen.add(key)
        unique_edges.append(edge)

with OUT_NODES.open("w", encoding="utf-8") as f:
    for node in nodes.values():
        f.write(json.dumps(node, ensure_ascii=False) + "\n")

with OUT_EDGES.open("w", encoding="utf-8") as f:
    for edge in unique_edges:
        f.write(json.dumps(edge, ensure_ascii=False) + "\n")

print("Patient organization layer built")
print(f"Nodes: {len(nodes)}")
print(f"Edges: {len(unique_edges)}")
print(f"NCL organizations: {sum(1 for e in unique_edges if e['subject'] == NCL)}")
print(f"CLN3 organizations: {sum(1 for e in unique_edges if e['subject'] == CLN3)}")
print(f"Output: {OUT_NODES}")
print(f"Output: {OUT_EDGES}")
