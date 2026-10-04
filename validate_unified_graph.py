import json
from pathlib import Path
from collections import Counter, defaultdict

DATA = Path("data")

NODES_FILE = DATA / "graph_nodes_unified.jsonl"
EDGES_FILE = DATA / "edges_unified.jsonl"


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


nodes = load_jsonl(NODES_FILE)
edges = load_jsonl(EDGES_FILE)

node_map = {n["id"]: n for n in nodes}


# ============================================================
# 1. BASIC COUNTS
# ============================================================

print("\n========== BASIC GRAPH ==========")
print(f"Nodes: {len(nodes)}")
print(f"Edges: {len(edges)}")


print("\nNode types:")
for node_type, count in Counter(
    n.get("type") for n in nodes
).most_common():
    print(f"  {node_type}: {count}")


print("\nPredicates:")
for predicate, count in Counter(
    e.get("predicate") for e in edges
).most_common():
    print(f"  {predicate}: {count}")


# ============================================================
# 2. DUPLICATE NODE IDS
# ============================================================

print("\n========== DUPLICATES ==========")

ids = [n["id"] for n in nodes]
duplicate_ids = [
    node_id
    for node_id, count in Counter(ids).items()
    if count > 1
]

print(f"Duplicate node IDs: {len(duplicate_ids)}")

for node_id in duplicate_ids[:20]:
    print(" ", node_id)


# ============================================================
# 3. ORPHAN EDGES
# ============================================================

print("\n========== ORPHAN EDGES ==========")

orphans = []

for edge in edges:
    if edge["subject"] not in node_map:
        orphans.append(("subject", edge))

    if edge["object"] not in node_map:
        orphans.append(("object", edge))

print(f"Orphan endpoints: {len(orphans)}")

for side, edge in orphans[:20]:
    print(
        f"  {side}: "
        f"{edge['subject']} "
        f"--{edge['predicate']}--> "
        f"{edge['object']}"
    )


# ============================================================
# 4. IMPORTANT DISEASES
# ============================================================

print("\n========== DISEASE CHECK ==========")

disease_ids = [
    "MONDO:0016295",  # NCL
    "MONDO:0008767",  # CLN3
    "MONDO:0008769",  # CLN2
    "MONDO:0009745",  # CLN5
    "MONDO:0008768",  # CLN6
]

for disease_id in disease_ids:
    node = node_map.get(disease_id)

    if node:
        print(
            f"OK  {disease_id}: "
            f"{node.get('label')}"
        )
    else:
        print(f"MISS {disease_id}")


# ============================================================
# 5. RELATIONSHIP SUMMARY FOR IMPORTANT DISEASES
# ============================================================

print("\n========== DISEASE CONNECTIONS ==========")

for disease_id in disease_ids:

    node = node_map.get(disease_id)

    if not node:
        continue

    print(f"\n{node.get('label')} [{disease_id}]")

    connections = []

    for edge in edges:

        if edge["subject"] == disease_id:
            other = node_map.get(edge["object"])

            connections.append(
                (
                    "OUT",
                    edge["predicate"],
                    other.get("label") if other else edge["object"],
                    other.get("type") if other else "?",
                )
            )

        elif edge["object"] == disease_id:
            other = node_map.get(edge["subject"])

            connections.append(
                (
                    "IN",
                    edge["predicate"],
                    other.get("label") if other else edge["subject"],
                    other.get("type") if other else "?",
                )
            )

    for direction, predicate, label, node_type in connections:
        print(
            f"  {direction:3} "
            f"{predicate:25} "
            f"{label} [{node_type}]"
        )


# ============================================================
# 6. NIH CHECK
# ============================================================

print("\n========== NIH REPORTER ==========")

nih_projects = [
    n for n in nodes
    if n["id"].startswith("nih_project:")
]

nih_people = [
    n for n in nodes
    if n["id"].startswith("nih_person:")
]

nih_orgs = [
    n for n in nodes
    if n.get("type") == "organization"
]

print(f"NIH projects: {len(nih_projects)}")
print(f"People:       {len(nih_people)}")
print(f"Organizations: {len(nih_orgs)}")

print("\nNIH project connections:")

for project in nih_projects[:20]:

    pid = project["id"]

    connections = [
        e for e in edges
        if e["subject"] == pid
        or e["object"] == pid
    ]

    print(
        f"\n{project.get('label')} [{pid}]"
    )

    for e in connections:
        other_id = (
            e["object"]
            if e["subject"] == pid
            else e["subject"]
        )

        other = node_map.get(other_id)

        print(
            f"  {e['predicate']:15} "
            f"→ {other.get('label') if other else other_id}"
        )


# ============================================================
# 7. REGISTRY CHECK
# ============================================================

print("\n========== PATIENT REGISTRY ==========")

registries = [
    n for n in nodes
    if (
        n.get("type") == "asset"
        and (
            "registry" in n.get("id", "").lower()
            or "registry" in n.get("label", "").lower()
        )
    )
]

print(f"Registry-like assets: {len(registries)}")

for registry in registries:

    print(
        f"\n{registry['label']} "
        f"[{registry['id']}]"
    )

    connections = [
        e for e in edges
        if (
            e["subject"] == registry["id"]
            or e["object"] == registry["id"]
        )
    ]

    for e in connections:

        other_id = (
            e["object"]
            if e["subject"] == registry["id"]
            else e["subject"]
        )

        other = node_map.get(other_id)

        print(
            f"  {e['predicate']:15} "
            f"→ {other.get('label') if other else other_id}"
        )


# ============================================================
# 8. SOURCE COUNTS
# ============================================================

print("\n========== SOURCES ==========")

sources = Counter(
    e.get("source", "unknown")
    for e in edges
)

for source, count in sources.most_common():
    print(f"  {source}: {count}")


# ============================================================
# 9. FINAL STATUS
# ============================================================

print("\n========== FINAL STATUS ==========")

problems = []

if duplicate_ids:
    problems.append(
        f"{len(duplicate_ids)} duplicate node IDs"
    )

if orphans:
    problems.append(
        f"{len(orphans)} orphan edge endpoints"
    )

required = [
    "MONDO:0016295",
    "MONDO:0008767",
]

for required_id in required:
    if required_id not in node_map:
        problems.append(
            f"missing required disease {required_id}"
        )


if problems:

    print("FAILED")
    for problem in problems:
        print(" -", problem)

else:

    print("PASSED")
    print("Unified graph is structurally consistent.")