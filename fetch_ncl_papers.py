"""Fetch a broad, deduplicated PubMed corpus for the NCL Atlas.

Usage:
    python3 fetch_ncl_papers.py

This replaces the narrow single-query PubMed fetch. It runs several
high-signal disease/gene/mechanism queries, deduplicates by PMID, and writes:
    data/papers.jsonl

No LLM is used here.
"""

import json
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
KEY = os.getenv("NCBI_API_KEY")
DATA = Path("data")
DATA.mkdir(exist_ok=True)

# 50 results per query gives us a useful first expansion without exploding
# the LLM extraction cost. Overlapping queries are deduplicated by PMID.
PER_QUERY = 50

QUERIES = [
    '"Neuronal Ceroid-Lipofuscinoses"[MeSH Terms]',
    '"neuronal ceroid lipofuscinosis"[Title/Abstract]',
    '"Batten disease"[Title/Abstract]',

    # Disease/gene-specific literature
    'CLN1[Title/Abstract] AND ("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract])',
    'CLN2[Title/Abstract] AND ("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract])',
    'CLN3[Title/Abstract] AND ("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract])',
    'CLN4[Title/Abstract] AND ("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract])',
    'CLN5[Title/Abstract] AND ("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract])',
    'CLN6[Title/Abstract] AND ("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract])',
    'CLN7[Title/Abstract] AND ("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract])',
    'CLN8[Title/Abstract] AND ("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract])',
    'CLN10[Title/Abstract] AND ("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract])',
    'CLN11[Title/Abstract] AND ("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract])',
    'CLN12[Title/Abstract] AND ("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract])',
    'CLN13[Title/Abstract] AND ("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract])',
    'CLN14[Title/Abstract] AND ("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract])',

    # Mechanistic literature likely to create cross-disease bridges
    '("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract]) AND (lysosomal[Title/Abstract] OR lysosome[Title/Abstract])',
    '("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract]) AND (autophagy[Title/Abstract] OR mitophagy[Title/Abstract])',
    '("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract]) AND (trafficking[Title/Abstract] OR "membrane trafficking"[Title/Abstract])',
    '("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract]) AND (lipid[Title/Abstract] OR phospholipid[Title/Abstract] OR "lipid metabolism"[Title/Abstract])',
    '("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract]) AND (inflammation[Title/Abstract] OR microglia[Title/Abstract] OR neuroinflammation[Title/Abstract])',
    '("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract]) AND (mitochondria[Title/Abstract] OR mitochondrial[Title/Abstract])',
    '("neuronal ceroid lipofuscinosis"[Title/Abstract] OR "Batten disease"[Title/Abstract]) AND (synapse[Title/Abstract] OR synaptic[Title/Abstract])',
]


def _get(endpoint: str, **params):
    if KEY:
        params["api_key"] = KEY
    time.sleep(0.11 if KEY else 0.35)
    r = requests.get(f"{EUTILS}/{endpoint}", params=params, timeout=60)
    r.raise_for_status()
    return r


def txt(el) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def parse(art) -> dict:
    cit = art.find("MedlineCitation")
    a = cit.find("Article")

    abstract = " ".join(
        (f"{x.get('Label')}: " if x.get("Label") else "") + txt(x)
        for x in a.iterfind("Abstract/AbstractText")
    )

    year = (
        a.findtext("Journal/JournalIssue/PubDate/Year")
        or (a.findtext("Journal/JournalIssue/PubDate/MedlineDate") or "")[:4]
    )

    authors = []
    for au in a.iterfind("AuthorList/Author"):
        name = au.findtext("CollectiveName") or (
            f"{au.findtext('ForeName', '')} {au.findtext('LastName', '')}".strip()
        )
        authors.append({
            "name": name,
            "orcid": next(
                (
                    txt(i)
                    for i in au.iterfind("Identifier")
                    if i.get("Source") == "ORCID"
                ),
                None,
            ),
            "affiliations": [
                txt(x) for x in au.iterfind("AffiliationInfo/Affiliation")
            ],
        })

    types = [txt(p) for p in a.iterfind("PublicationTypeList/PublicationType")]

    comments = [
        {"type": c.get("RefType"), "pmid": c.findtext("PMID")}
        for c in cit.iterfind("CommentsCorrectionsList/CommentsCorrections")
    ]

    return {
        "pmid": cit.findtext("PMID"),
        "title": txt(a.find("ArticleTitle")),
        "year": year,
        "journal": a.findtext("Journal/Title"),
        "doi": next(
            (
                txt(i)
                for i in art.iterfind("PubmedData/ArticleIdList/ArticleId")
                if i.get("IdType") == "doi"
            ),
            None,
        ),
        "abstract": abstract,
        "authors": authors,
        "grants": [
            {
                "id": g.findtext("GrantID"),
                "agency": g.findtext("Agency"),
                "country": g.findtext("Country"),
            }
            for g in a.iterfind("GrantList/Grant")
        ],
        "trials": [
            n.text
            for db in a.iterfind("DataBankList/DataBank")
            if db.findtext("DataBankName") == "ClinicalTrials.gov"
            for n in db.iterfind("AccessionNumberList/AccessionNumber")
        ],
        "mesh": [
            {
                "ui": d.get("UI"),
                "term": d.text,
                "major": d.get("MajorTopicYN") == "Y",
            }
            for d in cit.iterfind("MeshHeadingList/MeshHeading/DescriptorName")
        ],
        "pub_types": types,
        "comments_corrections": comments,
        "retracted": (
            "Retracted Publication" in types
            or any(c["type"] == "RetractionIn" for c in comments)
        ),
    }


def fetch_query(query: str) -> list[dict]:
    res = _get(
        "esearch.fcgi",
        db="pubmed",
        term=query,
        retmax=PER_QUERY,
        retmode="json",
        sort="relevance",
    ).json()["esearchresult"]

    ids = res["idlist"]
    print(f"\n{res['count']} matches | fetching {len(ids)}")
    print(query)

    papers = []
    for i in range(0, len(ids), 100):
        xml = _get(
            "efetch.fcgi",
            db="pubmed",
            id=",".join(ids[i:i + 100]),
            retmode="xml",
        ).content
        papers.extend(
            parse(art)
            for art in ET.fromstring(xml).iter("PubmedArticle")
        )

    return papers


def main():
    by_pmid = {}

    for query in QUERIES:
        for paper in fetch_query(query):
            pmid = paper.get("pmid")
            if pmid:
                by_pmid[pmid] = paper

    papers = list(by_pmid.values())

    # Keep retracted records out of the downstream graph.
    papers = [p for p in papers if not p["retracted"]]

    # Put papers with abstracts first because only papers with abstracts can
    # contribute to the current LLM relationship extractor.
    papers.sort(
        key=lambda p: (
            not bool(p["abstract"]),
            -(int(p["year"]) if str(p["year"]).isdigit() else 0),
        )
    )

    output = DATA / "papers.jsonl"
    with output.open("w", encoding="utf-8") as f:
        for paper in papers:
            f.write(json.dumps(paper, ensure_ascii=False) + "\n")

    with_abstract = sum(bool(p["abstract"]) for p in papers)
    with_grants = sum(bool(p["grants"]) for p in papers)
    with_trials = sum(bool(p["trials"]) for p in papers)

    print("\n" + "=" * 60)
    print("NCL PUBMED CORPUS")
    print("=" * 60)
    print(f"Unique non-retracted papers: {len(papers)}")
    print(f"With abstracts:              {with_abstract}")
    print(f"With grants:                 {with_grants}")
    print(f"With ClinicalTrials IDs:     {with_trials}")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
