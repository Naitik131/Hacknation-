import json
import tempfile
import zipfile
from pathlib import Path

DATA = Path("data")

MAIN_NODES = DATA / "graph_nodes.jsonl"
VERIFIED_EDGES = DATA / "edges_verified.jsonl"
PROVISIONAL_EDGES = DATA / "edges_provisional.jsonl"
CLINICAL_NODES = DATA / "clinical_trial_nodes.jsonl"
CLINICAL_EDGES = DATA / "clinical_trial_edges.jsonl"
PATIENT_NODES = DATA / "patient_organization_nodes.jsonl"
PATIENT_EDGES = DATA / "patient_organization_edges.jsonl"

NIH_NODES = DATA / "nih_nodes.jsonl"
NIH_EDGES = DATA / "nih_edges.jsonl"
REGISTRY_NODES = DATA / "registry_nodes.jsonl"
REGISTRY_EDGES = DATA / "registry_edges.jsonl"

NIH_ZIP = Path("nih_reporter_zip.zip")
REGISTRY_ZIP = Path("patient_registry_zip.zip")

OUT_NODES = DATA / "graph_nodes_unified.jsonl"
OUT_EDGES = DATA / "edges_unified.jsonl"

DISEASE_ALIASES = {
    "disease:ncl": "MONDO:0016295",
    "disease:neuronal_ceroid_lipofuscinosis": "MONDO:0016295",
    "disease:cln1": "MONDO:0009744",
    "disease:cln2": "MONDO:0008769",
    "disease:cln3": "MONDO:0008767",
    "disease:cln4": "MONDO:0008083",
    "disease:cln5": "MONDO:0009745",
    "disease:cln6": "MONDO:0008768",
    "disease:cln7": "MONDO:0012588",
    "disease:cln12": "MONDO:0017809",
    "disease:cln14": "MONDO:0012721",
}


def read_jsonl(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def zip_member(zip_path, suffix):
    if not zip_path.exists():
        return None
    z = zipfile.ZipFile(zip_path)
    matches = [n for n in z.namelist() if n.endswith(suffix)]
    if not matches:
        return None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
    with z.open(matches[0]) as src, open(tmp.name, "wb") as dst:
        dst.write(src.read())
    return Path(tmp.name)


def first_existing(*paths):
    for p in paths:
        if p and p.exists():
            return p
    return None


def load_optional(primary, zip_path, suffix):
    path = first_existing(primary, zip_member(zip_path, suffix))
    return read_jsonl(path) if path else []


def canonical_node_id(node_id):
    return DISEASE_ALIASES.get(node_id, node_id)


def canonicalize_node(node):
    node = dict(node)
    node["id"] = canonical_node_id(node.get("id"))
    attrs = dict(node.get("attrs") or {})
    if attrs.get("type") == "nih_institute":
        node["type"] = "organization"
    if node.get("type") == "nih_institute":
        node["type"] = "organization"
    node["attrs"] = attrs
    return node


def canonicalize_edge(edge):
    edge = dict(edge)
    edge["subject"] = canonical_node_id(edge.get("subject"))
    edge["object"] = canonical_node_id(edge.get("object"))
    if edge.get("subject_type") == "nih_institute":
        edge["subject_type"] = "organization"
    if edge.get("object_type") == "nih_institute":
        edge["object_type"] = "organization"
    return edge


def merge_node(nodes, node):
    node = canonicalize_node(node)
    node_id = node["id"]
    if node_id not in nodes:
        nodes[node_id] = node
        return

    existing = nodes[node_id]
    for synonym in node.get("synonyms", []):
        if synonym not in existing.setdefault("synonyms", []):
            existing["synonyms"].append(synonym)
    for key, value in node.get("attrs", {}).items():
        if key not in existing.setdefault("attrs", {}):
            existing["attrs"][key] = value


def add_endpoint_node(nodes, node_id, node_type, label):
    if not node_id or node_id in nodes:
        return
    nodes[node_id] = {
        "id": node_id,
        "type": node_type or "topic",
        "label": label or node_id,
        "synonyms": [],
        "attrs": {},
    }


nodes = {}
for node in read_jsonl(MAIN_NODES):
    merge_node(nodes, node)

for path in [CLINICAL_NODES, PATIENT_NODES, REGISTRY_NODES]:
    for node in read_jsonl(path):
        merge_node(nodes, node)

for node in load_optional(REGISTRY_NODES, REGISTRY_ZIP, "patient_registry/data/registry_nodes.jsonl"):
    merge_node(nodes, node)

for node in load_optional(NIH_NODES, NIH_ZIP, "nih_reporter/data/nih_nodes.jsonl"):
    merge_node(nodes, node)

edge_files = [
    VERIFIED_EDGES,
    PROVISIONAL_EDGES,
    CLINICAL_EDGES,
    PATIENT_EDGES,
    REGISTRY_EDGES,
]

edges = []
seen = set()

for path in edge_files:
    for edge in read_jsonl(path):
        edge = canonicalize_edge(edge)
        add_endpoint_node(nodes, edge.get("subject"), edge.get("subject_type"), edge.get("subject_label"))
        add_endpoint_node(nodes, edge.get("object"), edge.get("object_type"), edge.get("object_label"))
        key = (
            edge.get("subject"), edge.get("predicate"),
            edge.get("object"), edge.get("source")
        )
        if key not in seen:
            seen.add(key)
            edges.append(edge)

for edge in load_optional(REGISTRY_EDGES, REGISTRY_ZIP, "patient_registry/data/registry_edges.jsonl"):
    edge = canonicalize_edge(edge)
    add_endpoint_node(nodes, edge.get("subject"), edge.get("subject_type"), edge.get("subject_label"))
    add_endpoint_node(nodes, edge.get("object"), edge.get("object_type"), edge.get("object_label"))
    key = (edge.get("subject"), edge.get("predicate"), edge.get("object"), edge.get("source"))
    if key not in seen:
        seen.add(key)
        edges.append(edge)

for edge in load_optional(NIH_EDGES, NIH_ZIP, "nih_reporter/data/nih_edges.jsonl"):
    edge = canonicalize_edge(edge)
    add_endpoint_node(nodes, edge.get("subject"), edge.get("subject_type"), edge.get("subject_label"))
    add_endpoint_node(nodes, edge.get("object"), edge.get("object_type"), edge.get("object_label"))
    key = (edge.get("subject"), edge.get("predicate"), edge.get("object"), edge.get("source"))
    if key not in seen:
        seen.add(key)
        edges.append(edge)

with OUT_NODES.open("w", encoding="utf-8") as f:
    for node in nodes.values():
        f.write(json.dumps(node, ensure_ascii=False) + "\n")

with OUT_EDGES.open("w", encoding="utf-8") as f:
    for edge in edges:
        f.write(json.dumps(edge, ensure_ascii=False) + "\n")

print("\n==========================================")
print("UNIFIED KNOWLEDGE GRAPH BUILT")
print("==========================================")
print(f"Unified nodes: {len(nodes)}")
print(f"Unified edges: {len(edges)}")
print(f"Patient groups: {sum(1 for n in nodes.values() if n.get('type') == 'patient_group')}")
print(f"Patient-support edges: {sum(1 for e in edges if e.get('predicate') == 'supported_by')}")
print(f"Organizations: {sum(1 for n in nodes.values() if n.get('type') == 'organization')}")
print(f"Output nodes: {OUT_NODES}")
print(f"Output edges: {OUT_EDGES}")
