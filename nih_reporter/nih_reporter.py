import json
import time
from pathlib import Path

import requests


# ============================================================
# NIH RePORTER - NCL focused extraction
# ============================================================

BASE_URL = "https://api.reporter.nih.gov/v2/projects/search"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

RAW_FILE = DATA_DIR / "nih_projects_raw.jsonl"


# ------------------------------------------------------------
# Search terms
# ------------------------------------------------------------
# We deliberately search several disease/subtype names rather
# than one broad query.
#
# Search hits are NOT automatically promoted to graph edges.
# They will be audited by the relevance filter later.
# ------------------------------------------------------------

SEARCH_TERMS = [
    "neuronal ceroid lipofuscinosis",
    "Batten disease",
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

# Keep the first extraction manageable.
# We can expand after auditing the first results.
RESULTS_PER_QUERY = 20


# ------------------------------------------------------------
# API request
# ------------------------------------------------------------

def search_projects(search_term):
    payload = {
        "criteria": {
            "advanced_text_search": {
                "operator": "or",
                "search_field": "all",
                "search_text": f'"{search_term}"'
            },
            "use_relevance": True,
            "include_active_projects": True
        },
        "limit": RESULTS_PER_QUERY,
        "offset": 0,
        "sort_field": "project_start_date",
        "sort_order": "desc"
    }

    response = requests.post(
        BASE_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60
    )

    response.raise_for_status()
    return response.json()


# ------------------------------------------------------------
# Normalize a project
# ------------------------------------------------------------

def normalize_project(project, search_term):
    return {
        "project_num": project.get("project_num"),
        "core_project_num": project.get("core_project_num"),
        "application_id": project.get("appl_id"),

        "title": project.get("project_title"),
        "abstract": project.get("abstract"),
        "public_health_relevance": project.get(
            "public_health_relevance"
        ),

        "rcdc_terms": project.get("terms"),

        "principal_investigators": project.get(
            "principal_investigators", []
        ),

        "organization": project.get("organization"),

        "agency": project.get("agency_ic_admin"),
        "funding_ic": project.get("agency_ic_fund"),

        "activity_code": project.get("activity_code"),
        "funding_mechanism": project.get("funding_mechanism"),

        "project_start_date": project.get("project_start_date"),
        "project_end_date": project.get("project_end_date"),

        "award_amount": project.get("award_amount"),
        "fiscal_year": project.get("fiscal_year"),

        "nih_url": project.get("project_detail_url"),

        # Very important for auditing:
        # remember WHY this project was retrieved.
        "search_term": search_term,

        # Preserve the complete API record so we do not lose
        # potentially useful information.
        "raw_project": project
    }


# ------------------------------------------------------------
# Main extraction
# ------------------------------------------------------------

def main():

    print("=" * 70)
    print("NIH RePORTER - NCL PROJECT EXTRACTION")
    print("=" * 70)

    all_projects = {}

    for i, search_term in enumerate(SEARCH_TERMS, start=1):

        print(f"\n[{i}/{len(SEARCH_TERMS)}] Searching:")
        print(f"  {search_term}")

        try:
            data = search_projects(search_term)

            meta = data.get("meta", {})
            total = meta.get("total", "unknown")

            print(f"  API total matches: {total}")

            results = data.get("results", [])

            print(f"  Retrieved: {len(results)}")

            for project in results:

                normalized = normalize_project(
                    project,
                    search_term
                )

                project_id = (
                    normalized["core_project_num"]
                    or normalized["project_num"]
                    or normalized["application_id"]
                )

                if project_id is None:
                    continue

                # Deduplicate projects appearing under
                # multiple NCL/CLN searches.
                if project_id not in all_projects:

                    normalized["matched_search_terms"] = [
                        search_term
                    ]

                    all_projects[project_id] = normalized

                else:

                    if search_term not in all_projects[
                        project_id
                    ]["matched_search_terms"]:

                        all_projects[
                            project_id
                        ]["matched_search_terms"].append(
                            search_term
                        )

        except Exception as e:

            print(f"  ERROR: {e}")

        # NIH recommends limiting request frequency.
        time.sleep(1.1)

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    with open(RAW_FILE, "w", encoding="utf-8") as f:

        for project in all_projects.values():

            f.write(
                json.dumps(
                    project,
                    ensure_ascii=False
                )
                + "\n"
            )

    print("\n" + "=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)

    print(f"Unique projects: {len(all_projects)}")
    print(f"Saved to: {RAW_FILE}")


if __name__ == "__main__":
    main()