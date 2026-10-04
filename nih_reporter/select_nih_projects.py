import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "data" / "nih_projects_raw.jsonl"
OUTPUT_FILE = BASE_DIR / "data" / "nih_verified_candidates.jsonl"


# Projects whose titles explicitly identify NCL/Batten/CLN disease.
# R13NS151462 is intentionally excluded from the core research-project
# list because it is a conference rather than a disease research program.

VERIFIED_PROJECTS = {
    "U01NS148918",
    "R03NS146860",
    "R01NS146190",
    "F31NS143430",
    "U54HD122210",
    "R01NS140682",
    "R01NS126279",
    "R01NS124655",
    "R44NS120360",
    "R01HD106590",
}


def main():

    projects = {}

    with open(INPUT_FILE, "r", encoding="utf-8") as f:

        for line in f:

            if not line.strip():
                continue

            project = json.loads(line)

            project_id = (
                project.get("core_project_num")
                or project.get("project_num")
            )

            if project_id:
                projects[project_id] = project


    selected = []

    for project_id in VERIFIED_PROJECTS:

        if project_id not in projects:

            print(
                f"WARNING: {project_id} "
                "was not found in raw data."
            )

            continue

        project = projects[project_id]

        selected.append(project)

        print("\n" + "=" * 80)
        print(f"PROJECT: {project_id}")
        print(f"TITLE: {project.get('title')}")

        print("\nPRINCIPAL INVESTIGATORS:")

        pis = project.get(
            "principal_investigators",
            []
        )

        if not pis:
            print("  None returned")

        else:

            for pi in pis:

                if isinstance(pi, dict):

                    name = (
                        pi.get("full_name")
                        or pi.get("name")
                        or str(pi)
                    )

                    print(f"  - {name}")

                else:

                    print(f"  - {pi}")

        print(
            f"\nORGANIZATION: "
            f"{project.get('organization')}"
        )

        print(
            f"AGENCY: "
            f"{project.get('agency')}"
        )

        print(
            f"FUNDING MECHANISM: "
            f"{project.get('funding_mechanism')}"
        )

        print(
            f"ACTIVITY CODE: "
            f"{project.get('activity_code')}"
        )

        print(
            f"AWARD AMOUNT: "
            f"{project.get('award_amount')}"
        )

        print(
            f"START: "
            f"{project.get('project_start_date')}"
        )

        print(
            f"END: "
            f"{project.get('project_end_date')}"
        )

        abstract = project.get("abstract") or ""

        print("\nABSTRACT:")

        if abstract:
            print(abstract)
        else:
            print("No abstract returned by current API response.")


    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        for project in selected:

            f.write(
                json.dumps(
                    project,
                    ensure_ascii=False
                ) + "\n"
            )


    print("\n" + "=" * 80)
    print("VERIFIED NIH CANDIDATES")
    print("=" * 80)

    print(
        f"Selected: {len(selected)}"
    )

    print(
        f"Saved to: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()