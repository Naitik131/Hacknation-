"""
Opportunity detection for the unified rare-disease knowledge graph.

Run from the project root:
    python3 opportunity_detection.py

Inputs:
    data/graph_nodes_unified.jsonl
    data/edges_unified.jsonl

Outputs:
    data/opportunities.jsonl
    data/opportunities.md

Important:
This script does NOT invent biological relationships. It only detects
opportunities that are structurally supported by relationships already
present in the unified graph.

Opportunity classes:
1. shared_mechanism
   Two diseases connect to the same gene, phenotype, mechanism, pathway,
   or molecule.

2. translational_bridge
   Two diseases share a biological entity, but research activity is
   asymmetric. One side has trials/NIH projects while the other has less.

3. patient_ready_gap
   A disease has a patient registry and/or patient organization but no
   connected clinical trial or NIH project in the current graph.

4. research_gap
   A disease has biological/literature evidence but no connected clinical
   study or NIH project in the current graph.

5. registry_research_gap
   A disease has a registry but no connected NIH project or clinical study.

Scores are ranking heuristics, NOT probabilities or medical recommendations.
Every opportunity includes the graph paths that produced it.
"""

import json
from collections import defaultdict, Counter
from pathlib import Path

DATA = Path("data")

NODES_FILE = DATA / "graph_nodes_unified.jsonl"
EDGES_FILE = DATA / "edges_unified.jsonl"

OUT_JSONL = DATA / "opportunities.jsonl"
OUT_MD = DATA / "opportunities.md"


# ============================================================
# LOAD
# ============================================================

def read_jsonl(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")

    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


nodes = read_jsonl(NODES_FILE)
edges = read_jsonl(EDGES_FILE)

node_by_id = {n["id"]: n for n in nodes}


# ============================================================
# HELPERS
# ============================================================

def node_type(node_id):
    node = node_by_id.get(node_id, {})
    return node.get("type", "unknown")


def node_label(node_id):
    node = node_by_id.get(node_id, {})
    return node.get("label") or node_id


def edge_source(edge):
    return edge.get("source") or "unknown"


def evidence_type(edge):
    return edge.get("evidence_type") or "unknown"


# Undirected adjacency is intentional here.
# We are asking whether two disease nodes are connected to the same
# biological/research entity, not asserting a new causal direction.
adj = defaultdict(list)

for edge in edges:
    s = edge.get("subject")
    o = edge.get("object")

    if not s or not o:
        continue

    adj[s].append(edge)
    adj[o].append(edge)


# ============================================================
# ENTITY CATEGORIES
# ============================================================

BIOLOGICAL_TYPES = {
    "gene",
    "variant",
    "mechanism",
    "phenotype",
    "pathway",
    "molecule",
}

# A phenotype alone is useful for clustering, but is NOT sufficient
# to call a disease-to-disease research opportunity.
STRONG_BRIDGE_TYPES = {
    "gene",
    "variant",
    "mechanism",
    "pathway",
    "molecule",
}

RESEARCH_TYPES = {
    "study",
    "asset",
    "paper",
    "grant",
}

PATIENT_TYPES = {
    "patient_group",
}

# These are the predicates we consider useful for shared-biology detection.
BIOLOGICAL_PREDICATES = {
    "causes",
    "associated_with",
    "has_phenotype",
    "has_mechanism",
    "affects_mechanism",
    "disrupts_pathway",
    "involved_in_pathway",
    "has_variant",
    "variant_in_gene",
    "variant_associated_with",
    "has_molecular_consequence",
}

STUDY_PREDICATES = {
    "studied_in",
    "involves_intervention",
    "tests",
    "reports_trial",
}

PATIENT_PREDICATES = {
    "has_registry",
    "supported_by",
}


def is_disease(node_id):
    return node_type(node_id) == "disease"


def disease_ids():
    return sorted(
        n["id"]
        for n in nodes
        if n.get("type") == "disease"
    )


DISEASES = disease_ids()

# Current Atlas scope: neuronal ceroid lipofuscinoses and their named CLN
# disease subtypes. Do not surface unrelated diseases merely because they
# appear in imported paper metadata.
NCL_SCOPE_IDS = {
    "MONDO:0016295",  # neuronal ceroid lipofuscinosis
    "MONDO:0009744",  # CLN1
    "MONDO:0008769",  # CLN2
    "MONDO:0008767",  # CLN3
    "MONDO:0008083",  # CLN4
    "MONDO:0009745",  # CLN5
    "MONDO:0008768",  # CLN6
    "MONDO:0012588",  # CLN7
    "MONDO:0017809",  # CLN12
    "MONDO:0012721",  # CLN14
}

SCOPED_DISEASES = [
    disease_id
    for disease_id in DISEASES
    if disease_id in NCL_SCOPE_IDS
]


# ============================================================
# DISEASE PROFILE
# ============================================================

def disease_profile(disease_id):
    biological = []
    research = []
    patient = []

    for edge in adj.get(disease_id, []):

        other = (
            edge["object"]
            if edge.get("subject") == disease_id
            else edge.get("subject")
        )

        if not other:
            continue

        t = node_type(other)
        p = edge.get("predicate")

        if t in BIOLOGICAL_TYPES and p in BIOLOGICAL_PREDICATES:
            biological.append((other, edge))

        if t in RESEARCH_TYPES or p in STUDY_PREDICATES:
            research.append((other, edge))

        if t in PATIENT_TYPES or p in PATIENT_PREDICATES:
            patient.append((other, edge))

    return {
        "biological": biological,
        "research": research,
        "patient": patient,
    }


PROFILES = {
    disease_id: disease_profile(disease_id)
    for disease_id in DISEASES
}


# ============================================================
# RESEARCH / PATIENT ACTIVITY
# ============================================================

def connected_types(profile):
    return Counter(
        node_type(node_id)
        for node_id, _ in (
            profile["research"] + profile["patient"]
        )
    )


def has_trial_or_study(profile):
    for node_id, edge in profile["research"]:
        if node_type(node_id) == "study":
            return True

        if edge.get("predicate") in {
            "studied_in",
            "reports_trial",
            "tests",
        }:
            return True

    return False


def has_nih_project(profile):
    for node_id, edge in profile["research"]:
        if str(node_id).startswith("nih_project:"):
            return True

        label = node_label(node_id).lower()

        if "nih" in label and node_type(node_id) in {
            "study",
            "asset",
            "grant",
        }:
            return True

    return False


def has_registry(profile):
    for node_id, edge in profile["patient"]:
        if edge.get("predicate") == "has_registry":
            return True

        label = node_label(node_id).lower()

        if "registry" in label:
            return True

    return False


def has_patient_group(profile):
    return any(
        node_type(node_id) == "patient_group"
        for node_id, _ in profile["patient"]
    )


def research_activity_score(profile):
    score = 0

    if has_trial_or_study(profile):
        score += 2

    if has_nih_project(profile):
        score += 2

    paper_count = sum(
        1 for node_id, _ in profile["research"]
        if node_type(node_id) == "paper"
    )

    score += min(paper_count, 3)

    return score


# ============================================================
# EVIDENCE STRENGTH
# ============================================================

def edge_strength(edge):
    """
    Ranking weight only.

    observed > inferred > hypothesis > unknown.
    Source-backed graph edges receive an additional small weight.
    """
    evidence = evidence_type(edge)

    base = {
        "observed": 3.0,
        "inferred": 2.0,
        "hypothesis": 1.0,
    }.get(evidence, 0.5)

    source = edge_source(edge)

    if source and source != "unknown":
        base += 0.5

    return base


# ============================================================
# SHARED BIOLOGY
# ============================================================

def shared_biological_entities(disease_a, disease_b):
    a = {
        node_id: edge
        for node_id, edge in PROFILES[disease_a]["biological"]
    }

    b = {
        node_id: edge
        for node_id, edge in PROFILES[disease_b]["biological"]
    }

    shared = []

    for node_id in sorted(set(a) & set(b)):

        edge_a = a[node_id]
        edge_b = b[node_id]

        shared.append(
            {
                "entity_id": node_id,
                "entity_label": node_label(node_id),
                "entity_type": node_type(node_id),
                "edge_a": {
                    "predicate": edge_a.get("predicate"),
                    "source": edge_source(edge_a),
                    "evidence_type": evidence_type(edge_a),
                },
                "edge_b": {
                    "predicate": edge_b.get("predicate"),
                    "source": edge_source(edge_b),
                    "evidence_type": evidence_type(edge_b),
                },
                "strength": round(
                    edge_strength(edge_a) + edge_strength(edge_b),
                    2,
                ),
            }
        )

    return shared


# ============================================================
# OPPORTUNITY BUILDERS
# ============================================================

opportunities = []


def add_opportunity(
    kind,
    title,
    disease_ids_,
    score,
    rationale,
    evidence,
    caution,
):
    opportunities.append(
        {
            "id": f"OPP:{len(opportunities) + 1:04d}",
            "type": kind,
            "title": title,
            "diseases": disease_ids_,
            "score": round(score, 2),
            "rationale": rationale,
            "evidence": evidence,
            "caution": caution,
        }
    )


# ------------------------------------------------------------
# 1. Shared mechanism / phenotype / gene / pathway
# ------------------------------------------------------------

for i, disease_a in enumerate(SCOPED_DISEASES):

    for disease_b in SCOPED_DISEASES[i + 1:]:

        shared = shared_biological_entities(
            disease_a,
            disease_b,
        )

        if not shared:
            continue

        # Do not call a phenotype-only overlap an opportunity.
        # Things such as "epilepsy", "cerebellar atrophy", and
        # "neurodegeneration" are common across many rare diseases.
        strong_shared = [
            item
            for item in shared
            if item["entity_type"] in STRONG_BRIDGE_TYPES
        ]

        if not strong_shared:
            continue

        # Give greater weight to mechanisms/pathways/genes.
        weighted = 0

        for item in strong_shared:
            weights = {
                "mechanism": 4,
                "pathway": 4,
                "gene": 4,
                "variant": 3,
                "molecule": 3,
                "phenotype": 2,
            }

            weighted += (
                weights.get(item["entity_type"], 1)
                * item["strength"]
            )

        top_shared = sorted(
            strong_shared,
            key=lambda x: x["strength"],
            reverse=True,
        )[:5]

        # We only surface a shared-biology opportunity when there
        # is meaningful evidence, not merely one weak edge.
        if weighted < 8:
            continue

        research_a = research_activity_score(
            PROFILES[disease_a]
        )
        research_b = research_activity_score(
            PROFILES[disease_b]
        )

        asymmetry = abs(research_a - research_b)

        kind = (
            "translational_bridge"
            if asymmetry >= 3
            else "shared_mechanism"
        )

        labels = [
            f"{x['entity_label']} ({x['entity_type']})"
            for x in top_shared
        ]

        evidence = []

        for item in top_shared:
            evidence.append(
                {
                    "shared_entity": item["entity_label"],
                    "entity_type": item["entity_type"],
                    "disease_a_edge": item["edge_a"],
                    "disease_b_edge": item["edge_b"],
                }
            )

        if kind == "translational_bridge":

            more_researched = (
                disease_a
                if research_a > research_b
                else disease_b
            )

            less_researched = (
                disease_b
                if research_a > research_b
                else disease_a
            )

            title = (
                f"Potential translational bridge: "
                f"{node_label(more_researched)} → "
                f"{node_label(less_researched)}"
            )

            rationale = (
                f"The two diseases share graph-supported biological "
                f"entities, while research activity is asymmetric. "
                f"The more research-connected disease is "
                f"{node_label(more_researched)} and the less-connected "
                f"disease is {node_label(less_researched)}. "
                f"Shared entities include: {', '.join(labels)}."
            )

            caution = (
                "This is a research-prioritization signal, not evidence "
                "that a treatment should be transferred between diseases."
            )

        else:

            title = (
                f"Shared biology: "
                f"{node_label(disease_a)} ↔ "
                f"{node_label(disease_b)}"
            )

            rationale = (
                f"The graph connects both diseases to shared biological "
                f"entities: {', '.join(labels)}."
            )

            caution = (
                "Shared graph neighbors indicate an investigational "
                "connection only. They do not establish shared causality "
                "or therapeutic equivalence."
            )

        score = 10 + weighted + min(asymmetry * 2, 10)

        add_opportunity(
            kind=kind,
            title=title,
            disease_ids_=[disease_a, disease_b],
            score=score,
            rationale=rationale,
            evidence=evidence,
            caution=caution,
        )


# ------------------------------------------------------------
# 2. Patient-ready gaps
# ------------------------------------------------------------

for disease_id in SCOPED_DISEASES:

    profile = PROFILES[disease_id]

    registry = has_registry(profile)
    patient_group = has_patient_group(profile)
    trial = has_trial_or_study(profile)
    nih = has_nih_project(profile)

    if not (registry or patient_group):
        continue

    if trial or nih:
        continue

    patient_signals = []

    if registry:
        patient_signals.append("patient registry")

    if patient_group:
        patient_signals.append("patient organization")

    add_opportunity(
        kind="patient_ready_gap",
        title=(
            f"Patient infrastructure without connected research: "
            f"{node_label(disease_id)}"
        ),
        disease_ids_=[disease_id],
        score=18 + (3 if registry and patient_group else 0),
        rationale=(
            f"The graph contains {', '.join(patient_signals)} for "
            f"{node_label(disease_id)}, but no connected clinical study "
            f"or NIH project was found in the current dataset."
        ),
        evidence=[
            {
                "patient_infrastructure": patient_signals,
                "registry": registry,
                "patient_group": patient_group,
                "clinical_study": trial,
                "nih_project": nih,
            }
        ],
        caution=(
            "Absence means absence from the current graph, not proof that "
            "no study or funding exists elsewhere."
        ),
    )


# ------------------------------------------------------------
# 3. Registry without research
# ------------------------------------------------------------

for disease_id in SCOPED_DISEASES:

    profile = PROFILES[disease_id]

    if not has_registry(profile):
        continue

    if has_trial_or_study(profile) or has_nih_project(profile):
        continue

    add_opportunity(
        kind="registry_research_gap",
        title=(
            f"Registry-to-research gap: {node_label(disease_id)}"
        ),
        disease_ids_=[disease_id],
        score=20,
        rationale=(
            f"A patient registry is connected to {node_label(disease_id)}, "
            f"but no connected NIH project or clinical study appears in "
            f"the current graph."
        ),
        evidence=[
            {
                "predicate": "has_registry",
                "registry_present": True,
                "nih_project": False,
                "clinical_study": False,
            }
        ],
        caution=(
            "This identifies a gap in the integrated dataset. It should "
            "not be interpreted as proof of absent research worldwide."
        ),
    )


# ------------------------------------------------------------
# 4. Research gaps
# ------------------------------------------------------------

for disease_id in SCOPED_DISEASES:

    profile = PROFILES[disease_id]

    biological_count = len(profile["biological"])
    research_score = research_activity_score(profile)

    # Require at least some biological evidence before calling this
    # a research gap.
    if biological_count < 2:
        continue

    if research_score > 0:
        continue

    add_opportunity(
        kind="research_gap",
        title=(
            f"Biology-rich but clinically sparse: "
            f"{node_label(disease_id)}"
        ),
        disease_ids_=[disease_id],
        score=12 + min(biological_count, 8),
        rationale=(
            f"{node_label(disease_id)} has {biological_count} "
            f"graph-supported biological connections but no connected "
            f"clinical study or NIH project in the current graph."
        ),
        evidence=[
            {
                "biological_connections": biological_count,
                "clinical_study": False,
                "nih_project": False,
            }
        ],
        caution=(
            "This is a dataset-level research-gap signal. The graph is "
            "not a complete census of all worldwide research."
        ),
    )


# ============================================================
# RANK + DEDUP
# ============================================================

def dedup_key(opportunity):
    return (
        opportunity["type"],
        tuple(sorted(opportunity["diseases"])),
        opportunity["title"],
    )


unique = {}

for opportunity in opportunities:
    key = dedup_key(opportunity)

    if key not in unique:
        unique[key] = opportunity
    elif opportunity["score"] > unique[key]["score"]:
        unique[key] = opportunity


opportunities = sorted(
    unique.values(),
    key=lambda x: x["score"],
    reverse=True,
)


# Re-number after deduplication.
for index, opportunity in enumerate(opportunities, 1):
    opportunity["id"] = f"OPP:{index:04d}"


# ============================================================
# WRITE JSONL
# ============================================================

with OUT_JSONL.open("w", encoding="utf-8") as f:
    for opportunity in opportunities:
        f.write(
            json.dumps(
                opportunity,
                ensure_ascii=False,
            )
            + "\n"
        )


# ============================================================
# WRITE HUMAN-READABLE REPORT
# ============================================================

with OUT_MD.open("w", encoding="utf-8") as f:

    f.write("# Rare Disease Opportunity Report\n\n")

    f.write(
        "This report is generated only from relationships already "
        "present in `edges_unified.jsonl`. Scores are ranking heuristics, "
        "not probabilities or medical recommendations.\n\n"
    )

    f.write(f"Total opportunities: **{len(opportunities)}**\n\n")

    counts = Counter(
        opportunity["type"]
        for opportunity in opportunities
    )

    f.write("## Opportunity types\n\n")

    for kind, count in counts.most_common():
        f.write(f"- **{kind}**: {count}\n")

    f.write("\n---\n\n")

    for opportunity in opportunities:

        f.write(
            f"## {opportunity['id']} · "
            f"{opportunity['title']}\n\n"
        )

        f.write(
            f"**Type:** `{opportunity['type']}`  \n"
            f"**Score:** `{opportunity['score']}`  \n"
        )

        f.write(
            "**Diseases:** "
            + ", ".join(
                node_label(d)
                for d in opportunity["diseases"]
            )
            + "\n\n"
        )

        f.write(
            f"### Why this surfaced\n\n"
            f"{opportunity['rationale']}\n\n"
        )

        f.write("### Evidence\n\n")

        for item in opportunity["evidence"]:
            f.write(
                "```json\n"
                + json.dumps(
                    item,
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n```\n\n"
            )

        f.write(
            f"### Caution\n\n"
            f"{opportunity['caution']}\n\n"
        )

        f.write("---\n\n")


# ============================================================
# SUMMARY
# ============================================================

print("=" * 60)
print("OPPORTUNITY DETECTION")
print("=" * 60)
print(f"Nodes: {len(nodes)}")
print(f"Edges: {len(edges)}")
print(f"Diseases in graph: {len(DISEASES)}")
print(f"Diseases in NCL scope: {len(SCOPED_DISEASES)}")
print(f"Opportunities: {len(opportunities)}")
print()

for kind, count in counts.most_common():
    print(f"{kind}: {count}")

print()
print(f"Saved: {OUT_JSONL}")
print(f"Saved: {OUT_MD}")
