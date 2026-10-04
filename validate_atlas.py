import json
from collections import Counter
from pathlib import Path

DATA = Path("data")
nodes = [json.loads(x) for x in (DATA / "graph_nodes_unified.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
edges = [json.loads(x) for x in (DATA / "edges_unified.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]

node_ids = {n["id"] for n in nodes}
node_types = Counter(n.get("type") for n in nodes)
preds = Counter(e.get("predicate") for e in edges)

print(f"Nodes: {len(nodes):,}")
print(f"Edges: {len(edges):,}")
print("\nNodes by type:")
for k, v in sorted(node_types.items()):
    print(f"  {k:20s} {v:>6,}")

print("\nImportant edges:")
for k in [
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
    print(f"  {k:28s} {preds.get(k, 0):>6,}")

orphans = sum(
    1 for e in edges
    if e.get("subject") not in node_ids or e.get("object") not in node_ids
)
print(f"\nOrphan edges: {orphans}")

if preds.get("authored", 0) == 0:
    print("WARNING: authored edges are still zero.")
if node_types.get("variant", 0) == 0:
    print("WARNING: variant nodes are still zero.")
if preds.get("has_variant", 0) == 0:
    print("WARNING: has_variant edges are still zero.")
