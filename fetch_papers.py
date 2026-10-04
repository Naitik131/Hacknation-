"""Fetch structured PubMed records -> data/papers.jsonl (no LLM involved).

Usage:  python fetch_papers.py            # uses QUERY and N below
        python fetch_papers.py "<query>" 200
Optional: set NCBI_API_KEY (free) to raise the rate limit from ~3 to ~10 req/s.
"""
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

# Edit me. Test this query on pubmed.ncbi.nlm.nih.gov first and check the count.
QUERY = '"Neuronal Ceroid-Lipofuscinoses"[MeSH Terms]'
N = 150

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
KEY = os.getenv("NCBI_API_KEY")
DATA = Path("data")
DATA.mkdir(exist_ok=True)


def _get(endpoint: str, **params):
    if KEY:
        params["api_key"] = KEY
    time.sleep(0.11 if KEY else 0.35)  # stay under NCBI rate limits
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
        for x in a.iterfind("Abstract/AbstractText"))
    year = a.findtext("Journal/JournalIssue/PubDate/Year") or \
        (a.findtext("Journal/JournalIssue/PubDate/MedlineDate") or "")[:4]
    authors = []
    for au in a.iterfind("AuthorList/Author"):
        name = au.findtext("CollectiveName") or \
            f"{au.findtext('ForeName', '')} {au.findtext('LastName', '')}".strip()
        authors.append({
            "name": name,
            "orcid": next((txt(i) for i in au.iterfind("Identifier")
                           if i.get("Source") == "ORCID"), None),
            "affiliations": [txt(x) for x in au.iterfind("AffiliationInfo/Affiliation")]})
    types = [txt(p) for p in a.iterfind("PublicationTypeList/PublicationType")]
    comments = [{"type": c.get("RefType"), "pmid": c.findtext("PMID")}
                for c in cit.iterfind("CommentsCorrectionsList/CommentsCorrections")]
    return {
        "pmid": cit.findtext("PMID"),
        "title": txt(a.find("ArticleTitle")),
        "year": year,
        "journal": a.findtext("Journal/Title"),
        "doi": next((txt(i) for i in art.iterfind("PubmedData/ArticleIdList/ArticleId")
                     if i.get("IdType") == "doi"), None),
        "abstract": abstract,
        "authors": authors,
        "grants": [{"id": g.findtext("GrantID"), "agency": g.findtext("Agency"),
                    "country": g.findtext("Country")}
                   for g in a.iterfind("GrantList/Grant")],
        "trials": [n.text for db in a.iterfind("DataBankList/DataBank")
                   if db.findtext("DataBankName") == "ClinicalTrials.gov"
                   for n in db.iterfind("AccessionNumberList/AccessionNumber")],
        "mesh": [{"ui": d.get("UI"), "term": d.text, "major": d.get("MajorTopicYN") == "Y"}
                 for d in cit.iterfind("MeshHeadingList/MeshHeading/DescriptorName")],
        "pub_types": types,
        "comments_corrections": comments,
        "retracted": "Retracted Publication" in types
                     or any(c["type"] == "RetractionIn" for c in comments),
    }


def main(query: str, n: int):
    res = _get("esearch.fcgi", db="pubmed", term=query, retmax=n,
               retmode="json", sort="relevance").json()["esearchresult"]
    ids = res["idlist"]
    print(f"{res['count']} total matches for this query, fetching {len(ids)}")
    papers = []
    for i in range(0, len(ids), 100):
        xml = _get("efetch.fcgi", db="pubmed", id=",".join(ids[i:i + 100]),
                   retmode="xml").content
        papers += [parse(art) for art in ET.fromstring(xml).iter("PubmedArticle")]
    with open(DATA / "papers.jsonl", "w", encoding="utf-8") as f:
        for p in papers:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    c = lambda cond: sum(1 for p in papers if cond(p))
    print(f"saved {len(papers)} papers to data/papers.jsonl")
    print("with abstract:", c(lambda p: p["abstract"]),
          "| with grants:", c(lambda p: p["grants"]),
          "| with NCT ids:", c(lambda p: p["trials"]),
          "| retracted:", c(lambda p: p["retracted"]),
          "| with ORCID author:", c(lambda p: any(a["orcid"] for a in p["authors"])))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else QUERY,
         int(sys.argv[2]) if len(sys.argv) > 2 else N)
