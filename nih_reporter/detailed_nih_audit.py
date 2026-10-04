import json
import re
from pathlib import Path


# ============================================================
# NIH RePORTER - Detailed Evidence Audit
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "data" / "nih_projects_raw.jsonl"


NCL_TERMS = [
    "neuronal ceroid lipofuscinosis",
    "batten disease",
    "late infantile neuronal ceroid lipofuscinosis",
    "late-infantile neuronal ceroid lipofuscinosis",
    "cln1",
    "cln2",
    "cln3",
    "cln4",
    "cln5",
    "cln6",
    "cln7",
    "cln8",
    "cln10",
    "cln11",
    "cln12",
    "cln13",
    "cln14",
]


def flatten(value):
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        return " ".join(flatten(x) for x in value)

    if isinstance(value, dict):
        return " ".join(
            flatten(v)
            for v in value.values()
        )

    return str(value)


def find_matches(text):
    text_lower = text.lower()

    matches = []

    for term in NCL_TERMS:
        if term in text_lower:
            matches.append(term)

    return matches


def evidence_snippets(text, matches, window=220):

    if not text:
        return []

    snippets = []
    lower = text.lower()

    for term in matches:

        start = 0

        while True:

            pos = lower.find(term, start)

            if pos == -1:
                break

            left = max(0, pos - window)
            right = min(
                len(text),
                pos + len(term) + window
            )

            snippet = " ".join(
                text[left:right].split()
            )

            snippets.append(
                {
                    "term": term,
                    "snippet": snippet
                }
            )

            start = pos + len(term)

            # Don't print dozens of repeated snippets
            if len(snippets) >= 5:
                break

        if len(snippets) >= 5:
            break

    return snippets


def main():

    projects = []

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:

            if line.strip():
                projects.append(
                    json.loads(line)
                )

    print("=" * 90)
    print("DETAILED NIH EVIDENCE AUDIT")
    print("=" * 90)

    for project in projects:

        title = project.get("title") or ""
        abstract = project.get("abstract") or ""
        relevance = (
            project.get("public_health_relevance")
            or ""
        )
        terms = flatten(
            project.get("rcdc_terms")
        )

        title_matches = find_matches(title)
        abstract_matches = find_matches(abstract)
        relevance_matches = find_matches(relevance)
        term_matches = find_matches(terms)

        # ----------------------------------------------------
        # Only print projects that have some direct evidence.
        # ----------------------------------------------------

        if not (
            title_matches
            or abstract_matches
            or relevance_matches
            or term_matches
        ):
            continue

        project_id = (
            project.get("core_project_num")
            or project.get("project_num")
        )

        print("\n" + "=" * 90)

        print(f"PROJECT: {project_id}")
        print(f"TITLE: {title}")

        print(
            "SEARCH TERMS: "
            + ", ".join(
                project.get(
                    "matched_search_terms",
                    []
                )
            )
        )

        print("\n--- TITLE MATCHES ---")

        print(
            ", ".join(title_matches)
            if title_matches
            else "None"
        )

        print("\n--- ABSTRACT MATCHES ---")

        print(
            ", ".join(abstract_matches)
            if abstract_matches
            else "None"
        )

        if abstract_matches:

            print("\nABSTRACT EVIDENCE:")

            for item in evidence_snippets(
                abstract,
                abstract_matches
            ):

                print(
                    f"[{item['term']}] "
                    f"{item['snippet']}"
                )

        print("\n--- STRUCTURED TERM MATCHES ---")

        print(
            ", ".join(term_matches)
            if term_matches
            else "None"
        )

        print("\n--- PUBLIC HEALTH RELEVANCE ---")

        if relevance_matches:

            print(
                ", ".join(relevance_matches)
            )

            for item in evidence_snippets(
                relevance,
                relevance_matches
            ):

                print(
                    f"[{item['term']}] "
                    f"{item['snippet']}"
                )

        else:

            print("No NCL/CLN match")

    print("\n" + "=" * 90)
    print("END OF AUDIT")
    print("=" * 90)


if __name__ == "__main__":
    main()