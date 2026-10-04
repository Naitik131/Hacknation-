"""Build data/ontology.json.

Sources:
- HGNC -> genes
- MONDO -> diseases
- HPO -> phenotypes

Only canonical labels and ontology synonyms are used.
Ambiguous names mapping to multiple IDs are dropped.
"""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import requests

RAW = Path("data/raw")
RAW.mkdir(parents=True, exist_ok=True)

SOURCES = {
    "hgnc.tsv": "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt",
    "mondo.json": "https://purl.obolibrary.org/obo/mondo.json",
    "hp.json": "https://purl.obolibrary.org/obo/hp.json",
}


# names[entity_type][normalized_name] = set(stable IDs)
names = {
    "gene": defaultdict(set),
    "disease": defaultdict(set),
    "phenotype": defaultdict(set),
}


def norm(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def add(etype: str, name: str, stable_id: str):
    if not name:
        return

    names[etype][norm(name)].add(stable_id)


def download():
    for filename, url in SOURCES.items():
        path = RAW / filename

        if not path.exists():
            print("downloading", url)

            r = requests.get(url, timeout=600)
            r.raise_for_status()

            if r.content.lstrip()[:1] == b"<":
                raise SystemExit(
                    f"{url} returned HTML instead of data."
                )

            path.write_bytes(r.content)


def load_hgnc():
    with open(RAW / "hgnc.tsv", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")

        if not reader.fieldnames or "hgnc_id" not in reader.fieldnames:
            raise SystemExit(
                f"Invalid HGNC file. Columns: {reader.fieldnames}"
            )

        for row in reader:

            if row.get("status", "Approved") != "Approved":
                continue

            stable_id = row["hgnc_id"]

            # Official symbol and name
            add("gene", row.get("symbol", ""), stable_id)
            add("gene", row.get("name", ""), stable_id)

            # HGNC aliases
            for col in (
                "alias_symbol",
                "prev_symbol",
                "alias_name",
                "prev_name",
            ):
                value = row.get(col, "")

                if not value:
                    continue

                for term in value.strip('"').split("|"):
                    add("gene", term, stable_id)


def load_obo(filename: str, prefix: str, etype: str):

    graph = json.loads(
        (RAW / filename).read_text(encoding="utf-8")
    )["graphs"][0]

    for node in graph["nodes"]:

        if node.get("type") != "CLASS":
            continue

        if f"/{prefix}_" not in node.get("id", ""):
            continue

        meta = node.get("meta", {})

        if meta.get("deprecated"):
            continue

        label = node.get("lbl")

        if not label:
            continue

        stable_id = (
            node["id"]
            .rsplit("/", 1)[1]
            .replace("_", ":")
        )

        # Canonical label
        add(etype, label, stable_id)

        # Ontology synonyms
        for synonym in meta.get("synonyms", []):

            if synonym.get("pred") in {
                "hasExactSynonym",
                "hasRelatedSynonym",
                "hasBroadSynonym",
            }:
                add(
                    etype,
                    synonym.get("val", ""),
                    stable_id,
                )


def finalize(etype: str):

    result = {}

    for name, ids in names[etype].items():

        # Keep only unambiguous mappings
        if len(ids) == 1:
            result[name] = next(iter(ids))

    return result


if __name__ == "__main__":

    download()

    load_hgnc()
    load_obo("mondo.json", "MONDO", "disease")
    load_obo("hp.json", "HP", "phenotype")

    ontology = {
        "gene": finalize("gene"),
        "disease": finalize("disease"),
        "phenotype": finalize("phenotype"),
    }

    Path("data/ontology.json").write_text(
        json.dumps(ontology, indent=2)
    )

    for etype, mapping in ontology.items():

        total = len(names[etype])
        kept = len(mapping)

        print(
            f"{etype}: "
            f"{kept} names kept, "
            f"{total - kept} ambiguous dropped"
        )