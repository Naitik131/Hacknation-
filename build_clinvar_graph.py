"""
Build graph nodes and edges from ClinVar variant records.

Input:
    data/clinvar_variants.jsonl

Output:
    data/clinvar_nodes.jsonl
    data/clinvar_edges.jsonl
"""

import json
from datetime import date
from pathlib import Path


INPUT = Path("data/clinvar_variants.jsonl")
NODES_OUT = Path("data/clinvar_nodes.jsonl")
EDGES_OUT = Path("data/clinvar_edges.jsonl")

TODAY = date.today().isoformat()


def load_jsonl(path):
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path, rows):
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def make_gene_id(record):
    hgnc_id = record.get("hgnc_id")

    if hgnc_id:
        return hgnc_id

    gene = record.get("gene")

    if gene:
        return f"HGNC_SYMBOL:{gene}"

    return None


def make_variant_id(record):
    accession = record.get("clinvar_accession")

    if accession:
        return f"ClinVar:{accession}"

    variation_id = record.get("variation_id")

    if variation_id:
        return f"ClinVarVariation:{variation_id}"

    return None


def main():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT}"
        )

    nodes = {}
    edges = []

    records = list(load_jsonl(INPUT))

    print(f"Loaded {len(records)} ClinVar records")

    for record in records:

        variant_id = make_variant_id(record)

        if not variant_id:
            continue

        gene = record.get("gene")
        gene_id = make_gene_id(record)

        # -------------------------------------------------
        # Variant node
        # -------------------------------------------------

        variant_attrs = {
            "clinvar_variation_id": record.get("variation_id"),
            "clinvar_accession": record.get("clinvar_accession"),
            "variation_name": record.get("variation_name"),
            "variation_type": record.get("variation_type"),
            "hgvs": record.get("hgvs", []),
            "canonical_spdi": record.get("canonical_spdi"),
            "locations": record.get("locations", []),
            "clinical_significance": record.get(
                "clinical_significance", []
            ),
        }

        nodes[variant_id] = {
            "id": variant_id,
            "type": "variant",
            "label": (
                record.get("variation_name")
                or record.get("clinvar_accession")
                or variant_id
            ),
            "synonyms": record.get("hgvs", []),
            "attrs": variant_attrs,
        }

        # -------------------------------------------------
        # Gene node
        # -------------------------------------------------

        if gene_id and gene:

            if gene_id not in nodes:
                nodes[gene_id] = {
                    "id": gene_id,
                    "type": "gene",
                    "label": gene,
                    "synonyms": [],
                    "attrs": {
                        "gene_symbol": gene,
                        "ncbi_gene_id": record.get("gene_id"),
                        "hgnc_id": record.get("hgnc_id"),
                        "full_name": record.get("gene_full_name"),
                    },
                }

            # -------------------------------------------------
            # Gene -> Variant
            # -------------------------------------------------

            edges.append({
                "subject": gene_id,
                "predicate": "has_variant",
                "object": variant_id,

                "evidence_type": "observed",
                "source": "ClinVar",

                "quote": None,
                "extracted_by": "parser",
                "date": TODAY,

                "confidence": 1.0,
                "contradicted_by": [],

                "subject_type": "gene",
                "object_type": "variant",

                "subject_label": gene,
                "object_label": (
                    record.get("variation_name")
                    or record.get("clinvar_accession")
                    or variant_id
                ),
            })

        # -------------------------------------------------
        # Molecular consequences
        # -------------------------------------------------

        for consequence in record.get(
            "molecular_consequences", []
        ):

            label = consequence.get("label")

            if not label:
                continue

            so_id = consequence.get("so_id")

            if so_id:
                mechanism_id = f"SO:{so_id.split(':')[-1]}"
            else:
                slug = (
                    label.lower()
                    .replace(" ", "_")
                    .replace("/", "_")
                )
                mechanism_id = f"PROV:mechanism:{slug}"

            if mechanism_id not in nodes:
                nodes[mechanism_id] = {
                    "id": mechanism_id,
                    "type": "mechanism",
                    "label": label,
                    "synonyms": [],
                    "attrs": {
                        "sequence_ontology_id": so_id,
                    },
                }

            # -------------------------------------------------
            # Variant -> Molecular consequence
            # -------------------------------------------------

            edges.append({
                "subject": variant_id,
                "predicate": "has_molecular_consequence",
                "object": mechanism_id,

                "evidence_type": "observed",
                "source": "ClinVar",

                "quote": None,
                "extracted_by": "parser",
                "date": TODAY,

                "confidence": 1.0,
                "contradicted_by": [],

                "subject_type": "variant",
                "object_type": "mechanism",

                "subject_label": (
                    record.get("variation_name")
                    or record.get("clinvar_accession")
                ),
                "object_label": label,
            })

    # -----------------------------------------------------
    # Deduplicate edges
    # -----------------------------------------------------

    unique_edges = []
    seen_edges = set()

    for edge in edges:

        key = (
            edge["subject"],
            edge["predicate"],
            edge["object"],
        )

        if key in seen_edges:
            continue

        seen_edges.add(key)
        unique_edges.append(edge)

    nodes_list = list(nodes.values())

    write_jsonl(NODES_OUT, nodes_list)
    write_jsonl(EDGES_OUT, unique_edges)

    # -----------------------------------------------------
    # Stats
    # -----------------------------------------------------

    variant_count = sum(
        1 for n in nodes_list
        if n["type"] == "variant"
    )

    gene_count = sum(
        1 for n in nodes_list
        if n["type"] == "gene"
    )

    mechanism_count = sum(
        1 for n in nodes_list
        if n["type"] == "mechanism"
    )

    has_variant_count = sum(
        1 for e in unique_edges
        if e["predicate"] == "has_variant"
    )

    consequence_count = sum(
        1 for e in unique_edges
        if e["predicate"] == "has_molecular_consequence"
    )

    print()
    print("ClinVar graph built")
    print("-------------------")
    print(f"Records:                  {len(records)}")
    print(f"Variant nodes:            {variant_count}")
    print(f"Gene nodes:               {gene_count}")
    print(f"Mechanism nodes:          {mechanism_count}")
    print(f"has_variant edges:        {has_variant_count}")
    print(f"Molecular consequence:    {consequence_count}")
    print(f"Total nodes:              {len(nodes_list)}")
    print(f"Total edges:              {len(unique_edges)}")
    print()
    print(f"Nodes written to: {NODES_OUT}")
    print(f"Edges written to: {EDGES_OUT}")


if __name__ == "__main__":
    main()