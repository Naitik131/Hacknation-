"""
Build structured knowledge-graph nodes and edges from
ClinicalTrials.gov data.

Input:
    data/clinical_trials.jsonl

Output:
    data/clinical_trial_nodes.jsonl
    data/clinical_trial_edges.jsonl

Design principle:
    Only create disease relationships that are explicitly
    relevant to neuronal ceroid lipofuscinosis (NCL) /
    Batten disease / CLN subtypes.

    Other ClinicalTrials.gov conditions are preserved inside
    the study's metadata but are NOT turned into graph edges.

All ClinicalTrials.gov relationships created here are treated
as observed structured evidence.

No LLM is used in this step.
"""

import datetime
import json
import re
from pathlib import Path
from ontology import Ontology

ontology = Ontology()
from schema import Edge, Node


# =========================================================
# CONFIGURATION
# =========================================================

DATA = Path(__file__).resolve().parent / "data"

INPUT_FILE = DATA / "clinical_trials.jsonl"

NODE_OUTPUT = DATA / "clinical_trial_nodes.jsonl"

EDGE_OUTPUT = DATA / "clinical_trial_edges.jsonl"

TODAY = datetime.date.today().isoformat()


# =========================================================
# STORAGE
# =========================================================

nodes = {}

edges = []


# =========================================================
# NODE CREATION
# =========================================================

def add_node(
    node_id,
    node_type,
    label,
    synonyms=None,
    **attrs
):
    """
    Add a node if it does not already exist.

    If the node already exists, merge additional synonyms
    and attributes rather than creating a duplicate node.
    """

    if node_id not in nodes:

        nodes[node_id] = Node(
            id=node_id,
            type=node_type,
            label=label,
            synonyms=synonyms or [],
            attrs=attrs
        )

    else:

        existing = nodes[node_id]

        # Merge synonyms
        if synonyms:

            for synonym in synonyms:

                if synonym != existing.label and synonym not in existing.synonyms:

                    existing.synonyms.append(
                        synonym
                    )

        # Add missing attributes
        for key, value in attrs.items():

            if key not in existing.attrs:

                existing.attrs[key] = value

    return node_id


# =========================================================
# EDGE CREATION
# =========================================================

def add_edge(
    subject,
    predicate,
    object_id,
    nct_id
):

    edges.append(
        Edge(
            subject=subject,
            predicate=predicate,
            object=object_id,

            evidence_type="observed",

            source=nct_id,

            extracted_by="parser",

            date=TODAY,

            confidence=None
        )
    )


# =========================================================
# NORMALIZE TEXT
# =========================================================

def normalize_text(text):

    if not text:
        return ""

    text = text.lower()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# CHECK WHETHER CONDITION IS NCL-RELATED
# =========================================================

def is_ncl_condition(condition):

    text = normalize_text(
        condition
    )

    # Explicit NCL / Batten terminology
    if "neuronal ceroid lipofuscinosis" in text:
        return True

    if "batten disease" in text:
        return True

    # Explicit CLN subtype
    if re.search(
        r"\bcln\s*\d+\b",
        text
    ):
        return True

    # Some ClinicalTrials.gov records may use
    # "CLN1 disease", "CLN2 disease", etc.
    if re.search(
        r"\bcln\d+\b",
        text
    ):
        return True

    return False


# =========================================================
# CANONICALIZE NCL CONDITION
# =========================================================

def canonical_ncl_condition(condition):

    original = condition

    text = normalize_text(
        condition
    )

    # -----------------------------------------------------
    # CLN subtype detection
    # -----------------------------------------------------

    cln_match = re.search(
        r"\bcln\s*(\d+)\b",
        text
    )

    if cln_match:

        number = cln_match.group(1)

        canonical_label = (
            f"CLN{number} Disease"
        )

        return canonical_label


    # -----------------------------------------------------
    # Explicit NCL Type X
    # -----------------------------------------------------

    type_match = re.search(
        r"neuronal ceroid lipofuscinosis"
        r".*?"
        r"(?:type|cln)\s*(\d+)",
        text
    )

    if type_match:

        number = type_match.group(1)

        canonical_label = (
            f"CLN{number} Disease"
        )

        return canonical_label


    # -----------------------------------------------------
    # Generic NCL
    # -----------------------------------------------------

    if (
        "neuronal ceroid lipofuscinosis" in text
        and "late" not in text
    ):

        return "Neuronal Ceroid Lipofuscinosis"


    # -----------------------------------------------------
    # Batten Disease
    #
    # Keep it separate because we do NOT want to make
    # an unsupported equivalence claim in the graph.
    # -----------------------------------------------------

    if "batten disease" in text:

        return "Batten Disease"


    # -----------------------------------------------------
    # Late-infantile NCL without explicit CLN subtype
    #
    # Do NOT infer CLN2.
    # -----------------------------------------------------

    if "late" in text and "neuronal ceroid lipofuscinosis" in text:

        return (
            "Late-Infantile Neuronal Ceroid Lipofuscinosis"
        )


    # -----------------------------------------------------
    # Fallback
    # -----------------------------------------------------

    return original


# =========================================================
# DISEASE ID
# =========================================================

def disease_id(condition):
    canonical = canonical_ncl_condition(condition)

    # Try your existing MONDO ontology first
    mondo_id = ontology.resolve(canonical, "disease")

    if mondo_id:
        return mondo_id

    # Also try original ClinicalTrials.gov wording
    mondo_id = ontology.resolve(condition, "disease")

    if mondo_id:
        return mondo_id

    # Keep genuinely unresolved conditions provisional
    normalized = normalize_text(canonical)
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")

    return f"PROV:DISEASE:{normalized}"

# =========================================================
# INTERVENTION / ASSET ID
# =========================================================

def intervention_id(name):

    normalized = normalize_text(
        name
    )

    normalized = re.sub(
        r"[^a-z0-9]+",
        "_",
        normalized
    ).strip("_")

    return (
        f"PROV:ASSET:{normalized}"
    )


# =========================================================
# PROCESS ONE TRIAL
# =========================================================

def process_trial(trial):

    nct_id = trial.get(
        "nct_id"
    )

    title = trial.get(
        "title"
    )

    if not nct_id:

        return


    # -----------------------------------------------------
    # Study node
    # -----------------------------------------------------

    study_id = nct_id

    # Preserve ALL original ClinicalTrials.gov conditions
    # as metadata. We do not throw information away.
    all_conditions = trial.get(
        "conditions",
        []
    )

    add_node(
        study_id,
        "study",
        title or nct_id,

        nct_id=nct_id,

        status=trial.get(
            "status"
        ),

        study_type=trial.get(
            "study_type"
        ),

        phase=trial.get(
            "phase"
        ),

        enrollment=trial.get(
            "enrollment"
        ),

        start_date=trial.get(
            "start_date"
        ),

        completion_date=trial.get(
            "completion_date"
        ),

        source="ClinicalTrials.gov",

        all_conditions=all_conditions
    )


    # -----------------------------------------------------
    # Disease / condition nodes
    # -----------------------------------------------------

    for condition in all_conditions:

        if not condition:

            continue


        # IMPORTANT:
        # Only explicitly NCL-related conditions enter
        # the NCL knowledge graph.
        if not is_ncl_condition(condition):

            continue


        did = disease_id(
            condition
        )

        canonical_label = canonical_ncl_condition(
            condition
        )


        add_node(
            did,
            "disease",
            canonical_label,

            synonyms=[condition],

            id_basis="ClinicalTrials.gov condition",

            source_condition=condition
        )


        # Directly observed relationship:
        # ClinicalTrials.gov explicitly lists this condition
        # for this study.
        add_edge(
            study_id,
            "studied_in",
            did,
            nct_id
        )


    # -----------------------------------------------------
    # Intervention / asset nodes
    # -----------------------------------------------------

    for intervention in trial.get(
        "interventions",
        []
    ):

        name = intervention.get(
            "name"
        )

        if not name:

            continue


        aid = intervention_id(
            name
        )


        add_node(
            aid,
            "asset",
            name,

            intervention_type=intervention.get(
                "type"
            ),

            description=intervention.get(
                "description"
            ),

            id_basis="ClinicalTrials.gov intervention"
        )


        # Directly observed relationship:
        # ClinicalTrials.gov explicitly lists this
        # intervention for the study.
        add_edge(
            study_id,
            "involves_intervention",
            aid,
            nct_id
        )


# =========================================================
# MAIN
# =========================================================

def main():

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"Input file not found: "
            f"{INPUT_FILE}"
        )


    # -----------------------------------------------------
    # Read normalized clinical trials
    # -----------------------------------------------------

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:

            line = line.strip()

            if not line:

                continue

            trial = json.loads(
                line
            )

            process_trial(
                trial
            )


    # -----------------------------------------------------
    # Save nodes
    # -----------------------------------------------------

    with open(
        NODE_OUTPUT,
        "w",
        encoding="utf-8"
    ) as f:

        for node in nodes.values():

            f.write(
                node.model_dump_json()
                + "\n"
            )


    # -----------------------------------------------------
    # Save edges
    # -----------------------------------------------------

    with open(
        EDGE_OUTPUT,
        "w",
        encoding="utf-8"
    ) as f:

        for edge in edges:

            f.write(
                edge.model_dump_json()
                + "\n"
            )


    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    study_count = sum(
        1
        for n in nodes.values()
        if n.type == "study"
    )

    disease_count = sum(
        1
        for n in nodes.values()
        if n.type == "disease"
    )

    asset_count = sum(
        1
        for n in nodes.values()
        if n.type == "asset"
    )

    studied_in_count = sum(
        1
        for e in edges
        if e.predicate == "studied_in"
    )

    involves_intervention_count = sum(
        1
        for e in edges
        if e.predicate == "involves_intervention"
    )


    print()
    print(
        "=========================================="
    )

    print(
        "NCL CLINICALTRIALS GRAPH BUILT"
    )

    print(
        "=========================================="
    )

    print(
        f"Studies:       {study_count}"
    )

    print(
        f"Diseases:      {disease_count}"
    )

    print(
        f"Assets:        {asset_count}"
    )

    print(
        f"studied_in:    {studied_in_count}"
    )

    print(
        f"Involves intervention: {involves_intervention_count}"
    )

    print(
        f"Total nodes:   {len(nodes)}"
    )

    print(
        f"Total edges:   {len(edges)}"
    )

    print(
        "=========================================="
    )

    print()
    print(
        "Node file:"
    )

    print(
        NODE_OUTPUT
    )

    print()
    print(
        "Edge file:"
    )

    print(
        EDGE_OUTPUT
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()