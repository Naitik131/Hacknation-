import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
import ssl
import certifi


BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

OUT = Path("data/clinvar_variants.jsonl")

# Start with the NCL genes we already know about.
GENES = [
    "CLN1",
    "CLN2",
    "CLN3",
    "CLN4",
    "CLN5",
    "CLN6",
    "CLN7",
    "CLN8",
    "CLN10",
    "CLN11",
    "CLN12",
    "CLN13",
    "CLN14",
]


def get(url, params):
    query = urllib.parse.urlencode(params)

    full_url = f"{url}?{query}"

    req = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "RareDiseaseAtlas/1.0"
        },
    )

    context = ssl.create_default_context(
        cafile=certifi.where()
    )

    with urllib.request.urlopen(
        req,
        timeout=60,
        context=context,
    ) as response:
        return response.read()
def esearch_gene(gene):
    """
    Find ClinVar Variation IDs for a gene.
    """

    data = get(
        f"{BASE}/esearch.fcgi",
        {
            "db": "clinvar",
            "term": f"{gene}[gene]",
            "retmode": "json",
            "retmax": 10000,
        },
    )

    result = json.loads(data)

    return result["esearchresult"]["idlist"]


def efetch(ids):
    if not ids:
        return ""

    url = f"{BASE}/efetch.fcgi"

    params = {
        "db": "clinvar",
        "rettype": "vcv",
        "retmode": "xml",
        "id": ",".join(ids),
        "from_esearch": "true",
    }

    query = urllib.parse.urlencode(params)

    req = urllib.request.Request(
        f"{url}?{query}",
        headers={
            "User-Agent": "RareDiseaseKnowledgeGraph/1.0"
        },
    )

    context = ssl.create_default_context(
        cafile=certifi.where()
    )

    with urllib.request.urlopen(
        req,
        timeout=60,
        context=context
    ) as response:
        return response.read().decode("utf-8")

def text(element, path):
    child = element.find(path)

    if child is None:
        return None

    return child.text


def parse_records(xml_text):
    root = ET.fromstring(xml_text)

    records = []

    for record in root.findall(".//VariationArchive"):
        variation_id = record.attrib.get("VariationID")
        accession = record.attrib.get("Accession")
        variation_name = record.attrib.get("VariationName")
        variation_type = record.attrib.get("VariationType")

        if not variation_id:
            continue

        # -----------------------------
        # Gene
        # -----------------------------
        gene = None
        gene_id = None
        hgnc_id = None
        gene_full_name = None

        gene_el = record.find(".//GeneList/Gene")

        if gene_el is not None:
            gene = gene_el.attrib.get("Symbol")
            gene_id = gene_el.attrib.get("GeneID")
            hgnc_id = gene_el.attrib.get("HGNC_ID")
            gene_full_name = gene_el.attrib.get("FullName")

        # -----------------------------
        # HGVS
        # -----------------------------
        hgvs = []

        for expr in record.findall(".//HGVS//Expression"):
            if expr.text:
                value = expr.text.strip()

                if value and value not in hgvs:
                    hgvs.append(value)

        # -----------------------------
        # Molecular consequences
        # -----------------------------
        consequences = []

        for mc in record.findall(".//MolecularConsequence"):
            consequence = mc.attrib.get("Type")
            so_id = mc.attrib.get("ID")

            if consequence:
                item = {
                    "label": consequence,
                    "so_id": so_id,
                }

                if item not in consequences:
                    consequences.append(item)
                        # -----------------------------

        # Clinical assertions
        # -----------------------------
        clinical_assertions = []

        for assertion in record.findall(".//ClinicalAssertion"):

            accession_el = assertion.find("ClinVarAccession")

            scv = None
            submitter = None

            if accession_el is not None:
                scv = accession_el.attrib.get("Accession")
                submitter = accession_el.attrib.get("SubmitterName")

            classification_el = assertion.find("Classification")

            review_status = None
            germline_classification = None

            if classification_el is not None:

                review_el = classification_el.find("ReviewStatus")
                if review_el is not None and review_el.text:
                    review_status = review_el.text.strip()

                germline_el = classification_el.find(
                    "GermlineClassification"
                )

                if germline_el is not None and germline_el.text:
                    germline_classification = germline_el.text.strip()

            assertion_type = None

            assertion_el = assertion.find("Assertion")

            if assertion_el is not None and assertion_el.text:
                assertion_type = assertion_el.text.strip()

            # -----------------------------
            # Conditions / traits
            # -----------------------------

            conditions = []

            for trait in assertion.findall(".//TraitSet/Trait"):

                names = trait.findall(".//Name/ElementValue")

                for name in names:
                    if name.text:
                        conditions.append({
                            "name": name.text.strip(),
                            "type": trait.attrib.get("Type"),
                        })

            # -----------------------------
            # PubMed citations
            # -----------------------------

            pubmed_ids = []

            for citation in assertion.findall(".//Citation/ID"):

                if citation.attrib.get("Source") == "PubMed":
                    if citation.text:
                        pubmed_ids.append(citation.text.strip())

            clinical_assertions.append({
                "clinical_assertion_id": assertion.attrib.get("ID"),
                "scv": scv,
                "submitter": submitter,
                "review_status": review_status,
                "germline_classification": germline_classification,
                "assertion": assertion_type,
                "conditions": conditions,
                "pubmed_ids": pubmed_ids,
            })
        # -----------------------------
        # SPDI
        # -----------------------------
        spdi = None

        canonical_spdi = record.find(".//CanonicalSPDI")

        if canonical_spdi is not None and canonical_spdi.text:
            spdi = canonical_spdi.text.strip()

        # -----------------------------
        # Genomic locations
        # -----------------------------
        locations = []

        for loc in record.findall(".//SimpleAllele/Location/SequenceLocation"):
            locations.append({
                "assembly": loc.attrib.get("Assembly"),
                "chromosome": loc.attrib.get("Chr"),
                "accession": loc.attrib.get("Accession"),
                "start": loc.attrib.get("start"),
                "stop": loc.attrib.get("stop"),
                "strand": loc.attrib.get("Strand"),
            })

        # -----------------------------
        # Clinical significance
        # -----------------------------
        classifications = []

        for cs in record.findall(".//ClinicalSignificance"):
            description = cs.find("Description")

            if description is not None and description.text:
                classifications.append(
                    description.text.strip()
                )

            # Some records may expose it as an attribute
            value = cs.attrib.get("Description")

            if value:
                classifications.append(value)

        classifications = list(dict.fromkeys(classifications))

        # -----------------------------
        # Build record
        # -----------------------------
        records.append({
            "variation_id": variation_id,
            "clinvar_accession": accession,
            "variation_name": variation_name,
            "variation_type": variation_type,
            "clinical_assertions": clinical_assertions,

            "gene": gene,
            "gene_id": gene_id,
            "hgnc_id": hgnc_id,
            "gene_full_name": gene_full_name,

            "hgvs": hgvs,
            "canonical_spdi": spdi,

            "molecular_consequences": consequences,
            "locations": locations,

            "clinical_significance": classifications,
        })

    return records

def main():

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_records = {}

    print("=" * 60)
    print("CLINVAR INGESTION")
    print("=" * 60)

    for gene in GENES:

        print(f"\nSearching ClinVar: {gene}")

        ids = esearch_gene(gene)

        print(
            f"  Found {len(ids)} ClinVar records"
        )

        # Fetch in batches
        for start in range(0, len(ids), 100):

            batch = ids[start:start + 100]

            print(
                f"  Fetching "
                f"{start + 1}-{start + len(batch)}"
            )

            xml = efetch(batch)

            records = parse_records(
                xml
            )

            for record in records:

                key = (
                    gene,
                    record["variation_id"],
                )

                all_records[key] = record

            # Stay gentle with NCBI
            time.sleep(0.34)

    with open(
        OUT,
        "w",
        encoding="utf-8",
    ) as f:

        for record in all_records.values():

            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)

    print(
        f"Unique gene/variant records: "
        f"{len(all_records)}"
    )

    print(
        f"Written to: {OUT}"
    )


if __name__ == "__main__":
    main()