"""Summarize why edges were rejected. Run: python inspect_rejected.py"""
import difflib
import json
import re
from collections import Counter
from pathlib import Path

from ontology import NAMESPACES, Ontology, variants

DATA = Path("data")
onto = Ontology()
rows = [json.loads(line) for line in open(DATA / "rejected.jsonl", encoding="utf-8")]

unresolved, quote_fail = Counter(), []
for r in rows:
    c = r["candidate"]
    if r["reason"] == "quote_not_in_source":
        quote_fail.append(r)
        continue
    for side in ("subject", "object"):
        t = c[side + "_type"]
        if t in NAMESPACES and not onto.resolve(c[side], t):
            unresolved[(t, c[side])] += 1

print(f"{sum(unresolved.values())} unresolved mentions, {len(unresolved)} distinct names. Most common:")
for (t, name), cnt in unresolved.most_common(25):
    n = variants(name, t)[0]
    near = [k for k in onto.maps[t] if n in k][:3] if len(n) >= 4 else []
    print(f"  {cnt:2d}  [{t}] {name}    {t} entries containing it: {near}")

abstracts = {}
for line in open(DATA / "papers.jsonl", encoding="utf-8"):
    p = json.loads(line)
    abstracts[p["pmid"]] = p["abstract"]

print(f"\n{len(quote_fail)} quotes not found in the abstract:")
for r in quote_fail[:5]:
    q = r["candidate"]["quote"]
    sents = re.split(r"(?<=[.!?])\s+", abstracts.get(r["pmid"], ""))
    best = difflib.get_close_matches(q, sents, n=1, cutoff=0.0)
    print(f"\nPMID {r['pmid']}\n  model quote : {q}\n  closest real: {best[0] if best else '(abstract not found)'}")
