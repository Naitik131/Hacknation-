import json
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path("data")

NODES_FILE = DATA / "graph_nodes_unified.jsonl"
EDGES_FILE = DATA / "edges_unified.jsonl"


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"BAD JSON: {path}:{line_no}: {e}")
    return rows


nodes = read_jsonl(NODES_FILE)
edges = read_jsonl(EDGES_FILE)

node_ids = [n["id"] for n in nodes]
node_id_set = set(node_ids)

print()
print("==========================================")
print("UNIFIED GRAPH VALIDATION")
print("==========================================")

# ---------------------------------------------------------
# 1. Duplicate node IDs
# ---------------------------------------------------------

node_counts = Counter(node_ids)
duplicate_nodes = {
    node_id: count
    for node_id, count in node_counts.items()
    if count > 1
}

print(f"Nodes:                  {len(nodes)}")
print(f"Unique node IDs:        {len(node_id_set)}")
print(f"Duplicate node IDs:     {len(duplicate_nodes)}")

if duplicate_nodes:
    print("\nDUPLICATE NODES:")
    for node_id, count in duplicate_nodes.items():
        print(f"  {node_id}: {count}")


# ---------------------------------------------------------
# 2. Edge endpoint validation
# ---------------------------------------------------------

orphan_edges = []

for i, edge in enumerate(edges):
    subject = edge.get("subject")
    object_id = edge.get("object")

    missing = []

    if subject not in node_id_set:
        missing.append(f"subject={subject}")

    if object_id not in node_id_set:
        missing.append(f"object={object_id}")

    if missing:
        orphan_edges.append((i, edge, missing))

print(f"\nEdges:                  {len(edges)}")
print(f"Orphan/broken edges:    {len(orphan_edges)}")

if orphan_edges:
    print("\nBROKEN EDGES:")
    for i, edge, missing in orphan_edges[:20]:
        print(
            f"  [{i}] "
            f"{edge.get('subject')} "
            f"--{edge.get('predicate')}--> "
            f"{edge.get('object')}"
        )
        print(f"       Missing: {', '.join(missing)}")


# ---------------------------------------------------------
# 3. Node types
# ---------------------------------------------------------

node_types = Counter(n.get("type") for n in nodes)

print("\nNODE TYPES:")
for node_type, count in sorted(node_types.items()):
    print(f"  {node_type:20} {count}")


# ---------------------------------------------------------
# 4. Predicates
# ---------------------------------------------------------

predicates = Counter(e.get("predicate") for e in edges)

print("\nPREDICATES:")
for predicate, count in sorted(predicates.items()):
    print(f"  {predicate:25} {count}")


# ---------------------------------------------------------
# 5. PROV disease duplication check
# ---------------------------------------------------------

prov_diseases = [
    n for n in nodes
    if n.get("type") == "disease"
    and n.get("id", "").startswith("PROV:")
]

mondo_diseases = [
    n for n in nodes
    if n.get("type") == "disease"
    and n.get("id", "").startswith("MONDO:")
]

print("\nDISEASE IDS:")
print(f"  MONDO diseases:       {len(mondo_diseases)}")
print(f"  PROV diseases:        {len(prov_diseases)}")


# ---------------------------------------------------------
# 6. Check specific CLN canonical IDs
# ---------------------------------------------------------

expected_mondo = [
    "MONDO:0008767",  # CLN3
    "MONDO:0008769",  # CLN2
    "MONDO:0009745",  # CLN5
    "MONDO:0008768",  # CLN6
]

print("\nCANONICAL CLN CHECK:")

for node_id in expected_mondo:
    matches = [
        n for n in nodes
        if n.get("id") == node_id
    ]

    if matches:
        print(f"  OK   {node_id}: {matches[0].get('label')}")
    else:
        print(f"  MISS {node_id}")


# ---------------------------------------------------------
# 7. Check duplicate provisional CLN diseases
# ---------------------------------------------------------

print("\nPROVISIONAL CLN DUPLICATE CHECK:")

for n in prov_diseases:
    node_id = n["id"].lower()

    if any(
        cln.lower() in node_id
        for cln in [
            "cln2",
            "cln3",
            "cln5",
            "cln6",
        ]
    ):
        print(f"  WARNING: {n['id']} -> {n['label']}")


# ---------------------------------------------------------
# 8. ClinicalTrials validation
# ---------------------------------------------------------

clinical_edges = [
    e for e in edges
    if e.get("source", "").startswith("NCT")
]

clinical_nodes = [
    n for n in nodes
    if n.get("type") in {"study", "asset"}
]

print("\nCLINICALTRIALS:")
print(f"  Study/asset nodes:    {len(clinical_nodes)}")
print(f"  NCT-sourced edges:    {len(clinical_edges)}")

bad_clinical = []

for e in clinical_edges:
    if e.get("evidence_type") != "observed":
        bad_clinical.append(
            (e, "evidence_type is not observed")
        )

    if e.get("extracted_by") != "parser":
        bad_clinical.append(
            (e, "extracted_by is not parser")
        )

print(f"  Bad CT evidence:      {len(bad_clinical)}")


# ---------------------------------------------------------
# 9. Predicate direction checks
# ---------------------------------------------------------

direction_errors = []

for e in edges:
    predicate = e.get("predicate")
    subject = next(
        (n for n in nodes if n["id"] == e.get("subject")),
        None
    )
    object_node = next(
        (n for n in nodes if n["id"] == e.get("object")),
        None
    )

    if not subject or not object_node:
        continue

    st = subject.get("type")
    ot = object_node.get("type")

    if predicate == "has_phenotype":
        if st != "disease" or ot != "phenotype":
            direction_errors.append((e, st, ot))

    elif predicate == "causes":
        if ot != "disease":
            direction_errors.append((e, st, ot))

    elif predicate == "involves_intervention":
        if st != "study" or ot != "asset":
            direction_errors.append((e, st, ot))

    elif predicate == "studied_in":
        if st != "study" or ot != "disease":
            direction_errors.append((e, st, ot))


print(f"\nPredicate direction errors: {len(direction_errors)}")

if direction_errors:
    for e, st, ot in direction_errors[:20]:
        print(
            f"  {e.get('subject')} ({st}) "
            f"--{e.get('predicate')}--> "
            f"{e.get('object')} ({ot})"
        )


# ---------------------------------------------------------
# FINAL
# ---------------------------------------------------------

print()
print("==========================================")

problems = (
    len(duplicate_nodes)
    + len(orphan_edges)
    + len(direction_errors)
    + len(bad_clinical)
)

if problems == 0:
    print("✅ GRAPH VALIDATION PASSED")
else:
    print(f"⚠️ GRAPH VALIDATION FOUND {problems} PROBLEMS")

print("==========================================")