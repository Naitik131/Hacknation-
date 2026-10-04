import json
import sys
from datetime import datetime
from pathlib import Path

# Allow imports from the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from schema import Node, Edge

# ============================================================
# NIH RePORTER GRAPH BUILDER
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "nih_verified_candidates.jsonl"

NODES_FILE = DATA_DIR / "nih_nodes.jsonl"
EDGES_FILE = DATA_DIR / "nih_edges.jsonl"


# ------------------------------------------------------------
# Storage
# ------------------------------------------------------------

nodes = {}
edges = []


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def clean_id(value):
    """
    Make a stable ID-safe string.
    """
    if value is None:
        return ""

    value = str(value).strip()

    return (
        value
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("'", "")
        .replace(".", "")
        .replace(",", "")
        .replace("(", "")
        .replace(")", "")
    )


def add_node(node_id, node_type, label, synonyms=None, attrs=None):

    if node_id in nodes:

        # Merge synonyms if the node already exists.
        existing = nodes[node_id]

        if synonyms:
            for synonym in synonyms:
                if synonym not in existing.synonyms:
                    existing.synonyms.append(synonym)

        # Merge attributes.
        if attrs:
            existing.attrs.update(attrs)

        return

    nodes[node_id] = Node(
        id=node_id,
        type=node_type,
        label=label,
        synonyms=synonyms or [],
        attrs=attrs or {}
    )


def add_edge(
    subject,
    predicate,
    object_id,
    source,
    quote,
    date,
    subject_type,
    object_type,
    subject_label,
    object_label,
    confidence=1.0
):

    edges.append(
        Edge(
            subject=subject,
            predicate=predicate,
            object=object_id,
            evidence_type="observed",
            source=source,
            quote=quote,
            extracted_by="parser",
            date=date,
            confidence=confidence,
            contradicted_by=[],
            subject_type=subject_type,
            object_type=object_type,
            subject_label=subject_label,
            object_label=object_label
        )
    )


# ------------------------------------------------------------
# Disease extraction from title
# ------------------------------------------------------------

def extract_diseases(title):

    title_lower = title.lower()

    diseases = []

    # --------------------------------------------------------
    # Explicit CLN subtype takes priority.
    # If a title says "CLN3 Batten Disease", we only create
    # the CLN3 disease relationship. We do NOT additionally
    # create a Batten Disease relationship.
    # --------------------------------------------------------

    cln_mapping = {
        "cln1": ("disease:cln1", "CLN1 Disease", ["CLN1"]),
        "cln2": ("disease:cln2", "CLN2 Disease", ["CLN2"]),
        "cln3": ("disease:cln3", "CLN3 Disease", ["CLN3"]),
        "cln4": ("disease:cln4", "CLN4 Disease", ["CLN4"]),
        "cln5": ("disease:cln5", "CLN5 Disease", ["CLN5"]),
        "cln6": ("disease:cln6", "CLN6 Disease", ["CLN6"]),
        "cln7": ("disease:cln7", "CLN7 Disease", ["CLN7"]),
        "cln8": ("disease:cln8", "CLN8 Disease", ["CLN8"]),
        "cln10": ("disease:cln10", "CLN10 Disease", ["CLN10"]),
        "cln11": ("disease:cln11", "CLN11 Disease", ["CLN11"]),
        "cln12": ("disease:cln12", "CLN12 Disease", ["CLN12"]),
        "cln13": ("disease:cln13", "CLN13 Disease", ["CLN13"]),
        "cln14": ("disease:cln14", "CLN14 Disease", ["CLN14"]),
    }

    found_cln = False

    for term, disease_info in cln_mapping.items():

        if term in title_lower:

            diseases.append(disease_info)
            found_cln = True

    # --------------------------------------------------------
    # Only use generic Batten Disease when there is no
    # explicit CLN subtype in the title.
    # --------------------------------------------------------

    if not found_cln and "batten disease" in title_lower:

        diseases.append(
            (
                "disease:batten",
                "Batten Disease",
                ["Batten disease"]
            )
        )

    # --------------------------------------------------------
    # Generic NCL title.
    # Only use this when no more specific disease was found.
    # --------------------------------------------------------

    if (
        not diseases
        and "neuronal ceroid lipofuscinosis" in title_lower
    ):

        diseases.append(
            (
                "disease:ncl",
                "Neuronal Ceroid Lipofuscinosis",
                ["NCL"]
            )
        )

    return diseases


# ------------------------------------------------------------
# Principal investigator parsing
# ------------------------------------------------------------

def extract_pi_name(pi):

    if isinstance(pi, str):
        return pi.strip()

    if not isinstance(pi, dict):
        return str(pi)

    # Try common RePORTER fields.
    for key in [
        "full_name",
        "name",
        "principal_investigator_name"
    ]:

        value = pi.get(key)

        if value:
            return str(value).strip()

    # Fallback: construct from first/last names.
    first = pi.get("first_name", "")
    middle = pi.get("middle_name", "")
    last = pi.get("last_name", "")

    name = " ".join(
        x for x in [first, middle, last]
        if x
    )

    return name.strip()


# ------------------------------------------------------------
# Organization parsing
# ------------------------------------------------------------

def organization_name(organization):

    if isinstance(organization, str):
        return organization.strip()

    if isinstance(organization, dict):

        return (
            organization.get("org_name")
            or organization.get("name")
            or ""
        ).strip()

    return str(organization).strip()


# ------------------------------------------------------------
# Main processing
# ------------------------------------------------------------

def process_project(project):

    project_id = (
        project.get("core_project_num")
        or project.get("project_num")
    )

    if not project_id:
        return

    title = project.get("title") or "Untitled NIH Project"

    project_node_id = (
        f"nih_project:{clean_id(project_id)}"
    )

    # --------------------------------------------------------
    # Project node
    # --------------------------------------------------------

    project_attrs = {
        "project_num": project.get("project_num"),
        "core_project_num": project.get(
            "core_project_num"
        ),
        "application_id": project.get(
            "application_id"
        ),
        "title": title,
        "award_amount": project.get(
            "award_amount"
        ),
        "funding_mechanism": project.get(
            "funding_mechanism"
        ),
        "activity_code": project.get(
            "activity_code"
        ),
        "start_date": project.get(
            "project_start_date"
        ),
        "end_date": project.get(
            "project_end_date"
        ),
        "search_terms": project.get(
            "matched_search_terms",
            []
        ),
        "source": "NIH RePORTER",
        "source_url": project.get(
            "nih_url"
        ),
    }

    add_node(
        project_node_id,
        "study",
        project_id,
        attrs=project_attrs
    )

    # --------------------------------------------------------
    # Evidence date
    # --------------------------------------------------------

    date = (
        project.get("project_start_date")
        or datetime.utcnow().isoformat()
    )

    # --------------------------------------------------------
    # Disease relationships
    # --------------------------------------------------------

    diseases = extract_diseases(title)

    for disease_id, disease_label, synonyms in diseases:

        add_node(
            disease_id,
            "disease",
            disease_label,
            synonyms=synonyms,
            attrs={
                "source": "NIH RePORTER",
                "source_evidence": "project title"
            }
        )

        quote = (
            f'NIH RePORTER project title: "{title}"'
        )

        add_edge(
            subject=disease_id,
            predicate="studied_in",
            object_id=project_node_id,
            source=f"NIH RePORTER:{project_id}",
            quote=quote,
            date=date,
            subject_type="disease",
            object_type="study",
            subject_label=disease_label,
            object_label=project_id,
            confidence=1.0
        )

    # --------------------------------------------------------
    # Principal investigators
    # --------------------------------------------------------

    pis = project.get(
        "principal_investigators",
        []
    )

    for pi in pis:

        name = extract_pi_name(pi)

        if not name:
            continue

        person_id = (
            f"person:nih:{clean_id(name)}"
        )

        add_node(
            person_id,
            "person",
            name,
            attrs={
                "role": "Principal Investigator",
                "source": "NIH RePORTER"
            }
        )

        quote = (
            f'NIH RePORTER lists "{name}" '
            f'as a principal investigator for '
            f'project {project_id}.'
        )

        add_edge(
            subject=project_node_id,
            predicate="led_by",
            object_id=person_id,
            source=f"NIH RePORTER:{project_id}",
            quote=quote,
            date=date,
            subject_type="study",
            object_type="person",
            subject_label=project_id,
            object_label=name,
            confidence=1.0
        )

    # --------------------------------------------------------
    # Organization
    # --------------------------------------------------------

    org_name = organization_name(
        project.get("organization")
    )

    if org_name:

        org_id = (
            f"organization:nih:{clean_id(org_name)}"
        )

        add_node(
            org_id,
            "organization",
            org_name,
            attrs={
                "asset_type": "research_organization",
                "source": "NIH RePORTER"
            }
        )

        quote = (
            f'NIH RePORTER identifies '
            f'"{org_name}" as the organization '
            f'for project {project_id}.'
        )

        add_edge(
            subject=project_node_id,
            predicate="studied_in",
            object_id=org_id,
            source=f"NIH RePORTER:{project_id}",
            quote=quote,
            date=date,
            subject_type="study",
            object_type="organization",
            subject_label=project_id,
            object_label=org_name,
            confidence=1.0
        )

    # --------------------------------------------------------
    # NIH funding institute
    # --------------------------------------------------------

    agency = project.get("agency")

    agency_name = ""

    if isinstance(agency, dict):

        agency_name = (
            agency.get("name")
            or agency.get("abbreviation")
            or ""
        ).strip()

    elif agency:

        agency_name = str(agency).strip()

    if agency_name:

        agency_id = (
            f"organization:nih:{clean_id(agency_name)}"
        )

        add_node(
            agency_id,
            "nih_institute",
            agency_name,
            attrs={
                "organization_type": "NIH funding institute",
                "source": "NIH RePORTER"
            }
        )

        quote = (
            f'NIH RePORTER identifies '
            f'"{agency_name}" as the funding '
            f'institute for project {project_id}.'
        )

        add_edge(
            subject=project_node_id,
            predicate="funded_by",
            object_id=agency_id,
            source=f"NIH RePORTER:{project_id}",
            quote=quote,
            date=date,
            subject_type="study",
            object_type="nih_institute",
            subject_label=project_id,
            object_label=agency_name,
            confidence=1.0
        )


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():

    if not INPUT_FILE.exists():

        print(
            f"ERROR: Input file not found:\n"
            f"{INPUT_FILE}"
        )

        return

    nodes.clear()
    edges.clear()

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:

            if not line.strip():
                continue

            project = json.loads(line)

            process_project(project)

    # --------------------------------------------------------
    # Save nodes
    # --------------------------------------------------------

    with open(
        NODES_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        for node in nodes.values():

            f.write(
                node.model_dump_json()
                + "\n"
            )

    # --------------------------------------------------------
    # Save edges
    # --------------------------------------------------------

    with open(
        EDGES_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        for edge in edges:

            f.write(
                edge.model_dump_json()
                + "\n"
            )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("NIH REPORTE​R GRAPH BUILT")
    print("=" * 70)

    print(
        f"Total nodes: {len(nodes)}"
    )

    print(
        f"Total edges: {len(edges)}"
    )

    print("\nNode types:")

    node_counts = {}

    for node in nodes.values():

        node_counts[node.type] = (
            node_counts.get(node.type, 0) + 1
        )

    for node_type, count in node_counts.items():

        print(
            f"  {node_type}: {count}"
        )

    print("\nEdge types:")

    edge_counts = {}

    for edge in edges:

        edge_counts[edge.predicate] = (
            edge_counts.get(edge.predicate, 0) + 1
        )

    for predicate, count in edge_counts.items():

        print(
            f"  {predicate}: {count}"
        )

    print("\nOutput:")

    print(
        f"  {NODES_FILE}"
    )

    print(
        f"  {EDGES_FILE}"
    )


if __name__ == "__main__":
    main()