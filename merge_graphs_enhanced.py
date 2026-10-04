import json
import zipfile
import tempfile
from pathlib import Path

DATA = Path("data")

# Core graph
MAIN_NODES = DATA / "graph_nodes.jsonl"
STRUCTURED_EDGES = DATA / "edges_structured.jsonl"
VERIFIED_EDGES = DATA / "edges_verified.jsonl"
PROVISIONAL_EDGES = DATA / "edges_provisional.jsonl"

# Existing source layers
CLINICAL_NODES = DATA / "clinical_trial_nodes.jsonl"
CLINICAL_EDGES = DATA / "clinical_trial_edges.jsonl"

PATIENT_NODES = DATA / "patient_organization_nodes.jsonl"
PATIENT_EDGES = DATA / "patient_organization_edges.jsonl"

REGISTRY_NODES = DATA / "registry_nodes.jsonl"
REGISTRY_EDGES = DATA / "registry_edges.jsonl"

NIH_NODES = DATA / "nih_nodes.jsonl"
NIH_EDGES = DATA / "nih_edges.jsonl"

# ClinVar layer
CLINVAR_NODES = DATA / "clinvar_nodes.jsonl"
CLINVAR_EDGES = DATA / "clinvar_edges.jsonl"

# Optional ZIP fallbacks
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
    if not path or not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"WARNING: skipped invalid JSON in {path}: {line[:100]}")
    return rows

def zip_member(zip_path, suffix):
    if not zip_path.exists():
        return None
    with zipfile.ZipFile(zip_path) as z:
        matches = [n for n in z.namelist() if n.endswith(suffix)]
        if not matches:
            return None
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
        with z.open(matches[0]) as src, open(tmp.name, "wb") as dst:
            dst.write(src.read())
        return Path(tmp.name)

def optional_rows(primary, zip_path=None, suffix=None):
    if primary.exists():
        return read_jsonl(primary)
    if zip_path and suffix:
        p = zip_member(zip_path, suffix)
        if p:
            return read_jsonl(p)
    return []

def canonical_id(node_id):
    return DISEASE_ALIASES.get(node_id, node_id)

def canonical_node(node):
    node = dict(node)
    node["id"] = canonical_id(node.get("id"))
    if node.get("type") == "nih_institute":
        node["type"] = "organization"
    node.setdefault("synonyms", [])
    node.setdefault("attrs", {})
    return node

def canonical_edge(edge):
    edge = dict(edge)
    edge["subject"] = canonical_id(edge.get("subject"))
    edge["object"] = canonical_id(edge.get("object"))
    if edge.get("subject_type") == "nih_institute":
        edge["subject_type"] = "organization"
    if edge.get("object_type") == "nih_institute":
        edge["object_type"] = "organization"
    edge.setdefault("evidence_type", "observed")
    edge.setdefault("contradicted_by", [])
    return edge

def merge_node(nodes, node):
    node = canonical_node(node)
    nid = node.get("id")
    if not nid:
        return
    if nid not in nodes:
        nodes[nid] = node
        return

    existing = nodes[nid]

    for s in node.get("synonyms", []):
        if s not in existing.setdefault("synonyms", []):
            existing["synonyms"].append(s)

    for k, v in node.get("attrs", {}).items():
        if k not in existing.setdefault("attrs", {}) or existing["attrs"][k] in (None, "", [], {}):
            existing["attrs"][k] = v

    # Preserve a more informative label if the existing one is just an ID.
    if existing.get("label") in (None, "", nid) and node.get("label"):
        existing["label"] = node["label"]

def add_endpoint(nodes, nid, ntype, label):
    if not nid:
        return
    nid = canonical_id(nid)
    if nid in nodes:
        return
    nodes[nid] = {
        "id": nid,
        "type": ntype or "other",
        "label": label or nid,
        "synonyms": [],
        "attrs": {}
    }

def add_edges(edges, seen, rows, nodes):
    for raw in rows:
        edge = canonical_edge(raw)
        s = edge.get("subject")
        o = edge.get("object")
        if not s or not o:
            continue

        add_endpoint(nodes, s, edge.get("subject_type"), edge.get("subject_label"))
        add_endpoint(nodes, o, edge.get("object_type"), edge.get("object_label"))

        key = (s, edge.get("predicate"), o, edge.get("source"))
        if key in seen:
            continue
        seen.add(key)
        edges.append(edge)

def main():
    nodes = {}
    edges = []
    seen = set()

    # -----------------------------
    # Nodes
    # -----------------------------
    for node in read_jsonl(MAIN_NODES):
        merge_node(nodes, node)

    for path in [
        CLINICAL_NODES,
        PATIENT_NODES,
        REGISTRY_NODES,
        CLINVAR_NODES,
    ]:
        for node in read_jsonl(path):
            merge_node(nodes, node)

    for node in optional_rows(NIH_NODES, NIH_ZIP, "nih_reporter/data/nih_nodes.jsonl"):
        merge_node(nodes, node)

    for node in optional_rows(REGISTRY_NODES, REGISTRY_ZIP, "patient_registry/data/registry_nodes.jsonl"):
        merge_node(nodes, node)

    # -----------------------------
    # Edges
    # -----------------------------
    # IMPORTANT: edges_structured contains parser-generated author,
    # paper->grant and paper->trial links. Previous merge omitted it.
    add_edges(edges, seen, read_jsonl(STRUCTURED_EDGES), nodes)

    for path in [
        VERIFIED_EDGES,
        PROVISIONAL_EDGES,
        CLINICAL_EDGES,
        PATIENT_EDGES,
        REGISTRY_EDGES,
        CLINVAR_EDGES,
    ]:
        add_edges(edges, seen, read_jsonl(path), nodes)

    add_edges(
        edges, seen,
        optional_rows(NIH_EDGES, NIH_ZIP, "nih_reporter/data/nih_edges.jsonl"),
        nodes
    )

    add_edges(
        edges, seen,
        optional_rows(REGISTRY_EDGES, REGISTRY_ZIP, "patient_registry/data/registry_edges.jsonl"),
        nodes
    )

    OUT_NODES.parent.mkdir(parents=True, exist_ok=True)

    with OUT_NODES.open("w", encoding="utf-8") as f:
        for node in nodes.values():
            f.write(json.dumps(node, ensure_ascii=False) + "\n")

    with OUT_EDGES.open("w", encoding="utf-8") as f:
        for edge in edges:
            f.write(json.dumps(edge, ensure_ascii=False) + "\n")

    from collections import Counter
    node_counts = Counter(n.get("type") for n in nodes.values())
    edge_counts = Counter(e.get("predicate") for e in edges)

    print("\n" + "=" * 65)
    print("ENHANCED UNIFIED GRAPH BUILT")
    print("=" * 65)
    print(f"Nodes: {len(nodes):,}")
    print(f"Edges: {len(edges):,}")

    print("\nNODE TYPES")
    for k, v in sorted(node_counts.items()):
        print(f"  {k:20s} {v:>6,}")

    print("\nKEY EDGE TYPES")
    for key in [
        "authored",
        "has_variant",
        "has_molecular_consequence",
        "variant_associated_with",
        "funded_by",
        "reports_trial",
        "studied_in",
        "involves_intervention",
        "supported_by",
        "has_registry",
    ]:
        print(f"  {key:28s} {edge_counts.get(key, 0):>6,}")

    print("\nFILES")
    print(f"  {OUT_NODES}")
    print(f"  {OUT_EDGES}")
    print("=" * 65)

if __name__ == "__main__":
    main()
