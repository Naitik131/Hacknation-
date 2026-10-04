import json
from pathlib import Path

DATA = Path("data")

MAIN_NODES = DATA / "graph_nodes.jsonl"
CLINICAL_NODES = DATA / "clinical_trial_nodes.jsonl"

VERIFIED_EDGES = DATA / "edges_verified.jsonl"
PROVISIONAL_EDGES = DATA / "edges_provisional.jsonl"
CLINICAL_EDGES = DATA / "clinical_trial_edges.jsonl"

OUT_NODES = DATA / "graph_nodes_unified.jsonl"
OUT_EDGES = DATA / "edges_unified.jsonl"


def read_jsonl(path):
    rows = []

    if not path.exists():
        print(f"WARNING: {path} not found")
        return rows

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if line:
                rows.append(json.loads(line))

    return rows


def edge_key(edge):
    return (
        edge.get("subject"),
        edge.get("predicate"),
        edge.get("object"),
        edge.get("source"),
    )


def add_endpoint_node(nodes, node_id, node_type, label):
    """
    Add a biological/extracted entity node if it is missing.
    """

    if not node_id:
        return

    if node_id in nodes:
        return

    if not node_type:
        node_type = "entity"

    if not label:
        label = node_id

    nodes[node_id] = {
        "id": node_id,
        "type": node_type,
        "label": label,
        "synonyms": [],
        "attrs": {}
    }


# ============================================================
# LOAD MAIN NODES
# ============================================================

nodes = {}

main_nodes = read_jsonl(MAIN_NODES)

for node in main_nodes:
    nodes[node["id"]] = node

main_node_count = len(nodes)


# ============================================================
# LOAD CLINICALTRIAL NODES
# ============================================================

clinical_nodes = read_jsonl(CLINICAL_NODES)

for node in clinical_nodes:

    node_id = node["id"]

    if node_id not in nodes:
        nodes[node_id] = node

    else:
        existing = nodes[node_id]

        # Merge synonyms
        existing_synonyms = existing.setdefault("synonyms", [])

        for synonym in node.get("synonyms", []):
            if synonym not in existing_synonyms:
                existing_synonyms.append(synonym)

        # Merge attributes without overwriting existing values
        existing_attrs = existing.setdefault("attrs", {})

        for key, value in node.get("attrs", {}).items():

            if key not in existing_attrs:
                existing_attrs[key] = value


# ============================================================
# LOAD ALL EDGES
# ============================================================

edge_sources = [
    VERIFIED_EDGES,
    PROVISIONAL_EDGES,
    CLINICAL_EDGES,
]

edges = []
seen_edges = set()

edge_counts = {}


for path in edge_sources:

    file_edges = read_jsonl(path)

    edge_counts[path.name] = len(file_edges)

    for edge in file_edges:

        # ----------------------------------------------------
        # IMPORTANT:
        # Biological edges from the LLM pipeline may reference
        # nodes that were never written to graph_nodes.jsonl.
        #
        # Create those endpoint nodes here.
        # ----------------------------------------------------

        add_endpoint_node(
            nodes,
            edge.get("subject"),
            edge.get("subject_type"),
            edge.get("subject_label"),
        )

        add_endpoint_node(
            nodes,
            edge.get("object"),
            edge.get("object_type"),
            edge.get("object_label"),
        )

        # ----------------------------------------------------
        # Deduplicate identical edges
        # ----------------------------------------------------

        key = edge_key(edge)

        if key in seen_edges:
            continue

        seen_edges.add(key)
        edges.append(edge)


# ============================================================
# SAVE NODES
# ============================================================

with open(OUT_NODES, "w", encoding="utf-8") as f:

    for node in nodes.values():

        f.write(
            json.dumps(
                node,
                ensure_ascii=False
            )
            + "\n"
        )


# ============================================================
# SAVE EDGES
# ============================================================

with open(OUT_EDGES, "w", encoding="utf-8") as f:

    for edge in edges:

        f.write(
            json.dumps(
                edge,
                ensure_ascii=False
            )
            + "\n"
        )


# ============================================================
# SUMMARY
# ============================================================

print()
print("==========================================")
print("UNIFIED KNOWLEDGE GRAPH BUILT")
print("==========================================")

print(f"Existing nodes:          {main_node_count}")
print(f"Clinical nodes:          {len(clinical_nodes)}")

print(f"Verified edges:          {edge_counts.get('edges_verified.jsonl', 0)}")
print(f"Provisional edges:       {edge_counts.get('edges_provisional.jsonl', 0)}")
print(f"ClinicalTrials edges:    {edge_counts.get('clinical_trial_edges.jsonl', 0)}")

print()
print(f"Unified nodes:           {len(nodes)}")
print(f"Unified edges:           {len(edges)}")

print()
print(f"Output nodes:            {OUT_NODES}")
print(f"Output edges:            {OUT_EDGES}")

print("==========================================")