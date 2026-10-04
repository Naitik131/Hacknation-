"""papers.jsonl -> structured nodes and edges. No LLM, so nothing can be hallucinated.

Run: python build_graph.py
Writes data/graph_nodes.jsonl and data/edges_structured.jsonl, prints a summary.
Retracted papers are excluded. Authors with no ORCID are matched by normalized
name only (id starts with NAME:), so treat those links as probable, not certain.
"""
import datetime
import json
import re
from collections import Counter
from pathlib import Path

from schema import Edge, Node

DATA = Path("data")
TODAY = datetime.date.today().isoformat()
nodes: dict[str, Node] = {}
edges: list[Edge] = []


def add_node(nid: str, ntype: str, label: str, **attrs) -> str:
    if nid not in nodes:
        nodes[nid] = Node(id=nid, type=ntype, label=label, attrs=attrs)
    return nid


def add_edge(subj: str, pred: str, obj: str, pmid: str):
    edges.append(Edge(subject=subj, predicate=pred, object=obj, evidence_type="observed",
                      source=f"PMID:{pmid}", extracted_by="parser", date=TODAY))


def norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


def main():
    skipped = 0
    for line in open(DATA / "papers.jsonl", encoding="utf-8"):
        p = json.loads(line)
        if p["retracted"]:
            skipped += 1
            continue
        pmid = p["pmid"]
        pid = add_node(f"PMID:{pmid}", "paper", p["title"], year=p["year"],
                       journal=p["journal"], doi=p["doi"], pub_types=p["pub_types"],
                       has_abstract=bool(p["abstract"]))
        for a in p["authors"]:
            if not a["name"]:
                continue
            if a["orcid"]:
                aid, basis = "ORCID:" + re.sub(r"^.*orcid\.org/", "", a["orcid"]), "orcid"
            else:
                aid, basis = f"NAME:{norm_name(a['name'])}", "name_only"
            add_node(aid, "person", a["name"], id_basis=basis,
                     affiliation=(a["affiliations"] or [None])[0])
            add_edge(aid, "authored", pid, pmid)
        for g in p["grants"]:
            if g["id"]:
                gid = add_node(f"GRANT:{g['agency'] or 'unknown'}:{g['id']}", "grant",
                               g["id"], agency=g["agency"], country=g["country"])
                add_edge(pid, "funded_by", gid, pmid)
        for nct in p["trials"]:
            add_edge(pid, "reports_trial", add_node(nct, "study", nct), pmid)
        for m in p["mesh"]:
            if m["ui"]:
                add_edge(pid, "tagged_with", add_node(f"MESH:{m['ui']}", "topic", m["term"]), pmid)

    with open(DATA / "graph_nodes.jsonl", "w", encoding="utf-8") as f:
        f.writelines(n.model_dump_json() + "\n" for n in nodes.values())
    with open(DATA / "edges_structured.jsonl", "w", encoding="utf-8") as f:
        f.writelines(e.model_dump_json() + "\n" for e in edges)

    print(f"excluded {skipped} retracted papers")
    print("nodes:", dict(Counter(n.type for n in nodes.values())))
    print("edges:", dict(Counter(e.predicate for e in edges)))
    by_author = Counter(e.subject for e in edges if e.predicate == "authored")
    print("\nmost prolific authors in this slice (potential key opinion leaders):")
    for aid, c in by_author.most_common(10):
        print(f"  {c:3d} papers  {nodes[aid].label}  [{nodes[aid].attrs['id_basis']}]")
    by_topic = Counter(e.object for e in edges if e.predicate == "tagged_with")
    print("\nmost common MeSH topics (hints for sub-diseases, genes, mechanisms):")
    for tid, c in by_topic.most_common(15):
        print(f"  {c:3d}  {nodes[tid].label}")
    trials = [n.id for n in nodes.values() if n.type == "study"]
    print(f"\ntrial IDs found: {len(trials)} {trials[:10]}")


if __name__ == "__main__":
    main()
