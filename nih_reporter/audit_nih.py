import json
import re
from pathlib import Path


# ============================================================
# NIH RePORTER - Relevance Audit
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "data" / "nih_projects_raw.jsonl"


NCL_PHRASES = [
    "neuronal ceroid lipofuscinosis",
    "batten disease",
    "late infantile neuronal ceroid lipofuscinosis",
    "late-infantile neuronal ceroid lipofuscinosis",
]


CLN_PATTERN = re.compile(
    r"\bCLN(?:1|2|3|4|5|6|7|8|10|11|12|13|14)\b",
    re.IGNORECASE
)


def flatten_text(value):
    """
    Convert nested API fields into searchable text.
    """
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        return " ".join(flatten_text(x) for x in value)

    if isinstance(value, dict):
        return " ".join(
            flatten_text(v)
            for v in value.values()
        )

    return str(value)


def contains_direct_ncl(text):
    text = text.lower()

    for phrase in NCL_PHRASES:
        if phrase in text:
            return True

    return bool(CLN_PATTERN.search(text))


def classify_project(project):
    title = project.get("title") or ""
    abstract = project.get("abstract") or ""
    relevance = project.get("public_health_relevance") or ""
    terms = flatten_text(project.get("rcdc_terms"))
    raw = flatten_text(project.get("raw_project"))

    # --------------------------------------------------------
    # Strongest evidence: project title
    # --------------------------------------------------------

    if contains_direct_ncl(title):
        return "DIRECT_TITLE"

    # --------------------------------------------------------
    # Strong evidence: abstract
    # --------------------------------------------------------

    if contains_direct_ncl(abstract):
        return "DIRECT_ABSTRACT"

    # --------------------------------------------------------
    # Supporting structured information
    # --------------------------------------------------------

    if contains_direct_ncl(terms):
        return "STRUCTURED_TERMS"

    # --------------------------------------------------------
    # Public health relevance can contain useful context
    # --------------------------------------------------------

    if contains_direct_ncl(relevance):
        return "PUBLIC_HEALTH_RELEVANCE"

    # --------------------------------------------------------
    # If only the raw API search caused the match but the
    # meaningful fields do not contain NCL evidence, flag it.
    # --------------------------------------------------------

    return "SEARCH_MATCH_ONLY"


def main():

    if not INPUT_FILE.exists():
        print("ERROR:")
        print(f"File not found: {INPUT_FILE}")
        return

    projects = []

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            projects.append(json.loads(line))

    print("=" * 80)
    print("NIH REPORTE​R RELEVANCE AUDIT")
    print("=" * 80)

    print(f"\nProjects to audit: {len(projects)}")

    counts = {}

    for project in projects:

        category = classify_project(project)

        counts[category] = counts.get(category, 0) + 1

        print("\n" + "-" * 80)

        print(
            f"PROJECT: "
            f"{project.get('core_project_num') or project.get('project_num')}"
        )

        print(
            f"TITLE: "
            f"{project.get('title')}"
        )

        print(
            f"SEARCH MATCHES: "
            f"{', '.join(project.get('matched_search_terms', []))}"
        )

        print(
            f"RELEVANCE CLASS: "
            f"{category}"
        )

        # Show relevant evidence
        if category == "DIRECT_TITLE":

            print("EVIDENCE: NCL/CLN appears in project title.")

        elif category == "DIRECT_ABSTRACT":

            print(
                "EVIDENCE: NCL/CLN appears in project abstract."
            )

        elif category == "STRUCTURED_TERMS":

            print(
                "EVIDENCE: NCL/CLN appears in structured NIH terms."
            )

        elif category == "PUBLIC_HEALTH_RELEVANCE":

            print(
                "EVIDENCE: NCL/CLN appears in public health relevance."
            )

        else:

            print(
                "WARNING: Search matched this project, "
                "but no direct NCL/CLN evidence was found "
                "in the main searchable fields."
            )

        # Short abstract preview
        abstract = project.get("abstract") or ""

        if abstract:

            preview = " ".join(
                abstract.split()
            )

            if len(preview) > 500:
                preview = preview[:500] + "..."

            print(f"ABSTRACT: {preview}")

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print("\n")
    print("=" * 80)
    print("AUDIT SUMMARY")
    print("=" * 80)

    for category, count in counts.items():

        print(
            f"{category:25s}: {count}"
        )

    print("\n")
    print("IMPORTANT:")
    print(
        "SEARCH_MATCH_ONLY projects should NOT become graph "
        "relationships without further evidence."
    )


if __name__ == "__main__":
    main()