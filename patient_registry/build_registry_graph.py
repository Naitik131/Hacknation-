import json
import sys
from datetime import datetime
from pathlib import Path


# ============================================================
# PROJECT ROOT
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(
    0,
    str(PROJECT_ROOT)
)

from schema import Node, Edge


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "registries.jsonl"

NODES_FILE = DATA_DIR / "registry_nodes.jsonl"
EDGES_FILE = DATA_DIR / "registry_edges.jsonl"


# ============================================================
# HELPERS
# ============================================================

def clean_id(text):

    text = str(text).strip().lower()

    result = ""

    for char in text:

        if char.isalnum():
            result += char

        else:
            result += "_"

    while "__" in result:
        result = result.replace(
            "__",
            "_"
        )

    return result.strip("_")


def add_node(
    nodes,
    node_id,
    node_type,
    label,
    synonyms=None,
    attrs=None,
):

    if node_id in nodes:
        return

    node = Node(
        id=node_id,
        type=node_type,
        label=label,
        synonyms=synonyms or [],
        attrs=attrs or {},
    )

    nodes[node_id] = node


def add_edge(
    edges,
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
):

    edge = Edge(
        subject=subject,
        predicate=predicate,
        object=object_id,
        evidence_type="observed",
        source=source,
        quote=quote,
        extracted_by="parser",
        date=date,
        confidence=1.0,
        subject_type=subject_type,
        object_type=object_type,
        subject_label=subject_label,
        object_label=object_label,
    )

    edges.append(edge)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("PATIENT REGISTRY GRAPH BUILDER")
    print("=" * 70)

    nodes = {}
    edges = []

    # --------------------------------------------------------
    # Read registry records
    # --------------------------------------------------------

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8",
    ) as f:

        records = [
            json.loads(line)
            for line in f
            if line.strip()
        ]

    print(
        f"Registry records loaded: {len(records)}"
    )

    # --------------------------------------------------------
    # Process each registry
    # --------------------------------------------------------

    for record in records:

        registry_id = record["id"]
        registry_name = record["name"]

        source = record["source"]
        source_url = record["source_url"]

        disease_name = record["disease"]

        # ----------------------------------------------------
        # Registry node
        # ----------------------------------------------------

        add_node(
            nodes=nodes,
            node_id=registry_id,
            node_type="asset",
            label=registry_name,
            synonyms=[],
            attrs={
                "resource_type": "patient_registry",
                "source": source,
                "source_url": source_url,
                "country": record.get(
                    "country"
                ),
                "retrieval_status": record.get(
                    "retrieval_status"
                ),
            },
        )

        # ----------------------------------------------------
        # Disease node
        # ----------------------------------------------------

        disease_id = (
            "disease:"
            + clean_id(disease_name)
        )

        add_node(
            nodes=nodes,
            node_id=disease_id,
            node_type="disease",
            label=disease_name,
            synonyms=[],
            attrs={
                "source": source,
                "source_url": source_url,
            },
        )

        # ----------------------------------------------------
        # Disease → Registry
        #
        # This relationship is directly supported by
        # the registry record.
        # ----------------------------------------------------

        quote = (
            f"Registry: {registry_name}; "
            f"Disease covered: {disease_name}"
        )

        add_edge(
            edges=edges,
            subject=disease_id,
            predicate="has_registry",
            object_id=registry_id,
            source=source_url,
            quote=quote,
            date=record.get(
                "retrieved_at",
                datetime.utcnow().isoformat(),
            ),
            subject_type="disease",
            object_type="asset",
            subject_label=disease_name,
            object_label=registry_name,
        )

    # --------------------------------------------------------
    # Write nodes
    # --------------------------------------------------------

    with open(
        NODES_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        for node in nodes.values():

            f.write(
                node.model_dump_json(
                    ensure_ascii=False
                )
                + "\n"
            )

    # --------------------------------------------------------
    # Write edges
    # --------------------------------------------------------

    with open(
        EDGES_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        for edge in edges:

            f.write(
                edge.model_dump_json(
                    ensure_ascii=False
                )
                + "\n"
            )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("PATIENT REGISTRY GRAPH BUILT")
    print("=" * 70)

    print(
        f"Total nodes: {len(nodes)}"
    )

    print(
        f"Total edges: {len(edges)}"
    )

    print()
    print("Node types:")

    node_type_counts = {}

    for node in nodes.values():

        node_type_counts[node.type] = (
            node_type_counts.get(
                node.type,
                0,
            )
            + 1
        )

    for node_type, count in node_type_counts.items():

        print(
            f"  {node_type}: {count}"
        )

    print()
    print("Edge types:")

    edge_type_counts = {}

    for edge in edges:

        edge_type_counts[edge.predicate] = (
            edge_type_counts.get(
                edge.predicate,
                0,
            )
            + 1
        )

    for predicate, count in edge_type_counts.items():

        print(
            f"  {predicate}: {count}"
        )

    print()
    print("Output:")

    print(
        f"  {NODES_FILE}"
    )

    print(
        f"  {EDGES_FILE}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()