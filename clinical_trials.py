import json
import requests
from pathlib import Path


# =========================================================
# CONFIGURATION
# =========================================================

API_URL = "https://clinicaltrials.gov/api/v2/studies"

SEARCH_TERM = "neuronal ceroid lipofuscinosis"

MAX_STUDIES = 100

# Always save files inside the repository's data folder
OUTPUT_DIR = Path(__file__).resolve().parent / "data"

RAW_OUTPUT = OUTPUT_DIR / "clinical_trials_raw.json"

NORMALIZED_OUTPUT = OUTPUT_DIR / "clinical_trials.jsonl"


# =========================================================
# FETCH STUDIES FROM CLINICALTRIALS.GOV
# =========================================================

def fetch_trials(search_term, max_studies=20):

    params = {
        "query.cond": search_term,
        "pageSize": max_studies,
        "format": "json"
    }

    print(
        f"Searching ClinicalTrials.gov for: "
        f"{search_term}"
    )

    response = requests.get(
        API_URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    return data


# =========================================================
# NORMALIZE ONE CLINICAL TRIAL
# =========================================================

def normalize_trial(study):

    protocol = study.get(
        "protocolSection",
        {}
    )

    identification = protocol.get(
        "identificationModule",
        {}
    )

    status = protocol.get(
        "statusModule",
        {}
    )

    design = protocol.get(
        "designModule",
        {}
    )

    conditions = protocol.get(
        "conditionsModule",
        {}
    )

    arms = protocol.get(
        "armsInterventionsModule",
        {}
    )

    sponsor = protocol.get(
        "sponsorCollaboratorsModule",
        {}
    )

    contacts = protocol.get(
        "contactsLocationsModule",
        {}
    )


    # -----------------------------------------------------
    # Study identification
    # -----------------------------------------------------

    nct_id = identification.get(
        "nctId"
    )

    title = (
        identification.get(
            "briefTitle"
        )
        or identification.get(
            "officialTitle"
        )
    )


    # -----------------------------------------------------
    # Conditions
    # -----------------------------------------------------

    condition_list = conditions.get(
        "conditions",
        []
    )


    # -----------------------------------------------------
    # Interventions
    # -----------------------------------------------------

    interventions = []

    for intervention in arms.get(
        "interventions",
        []
    ):

        interventions.append(
            {
                "type": intervention.get(
                    "type"
                ),

                "name": intervention.get(
                    "name"
                ),

                "description": intervention.get(
                    "description"
                )
            }
        )


    # -----------------------------------------------------
    # Sponsor
    # -----------------------------------------------------

    lead_sponsor = sponsor.get(
        "leadSponsor",
        {}
    )


    # -----------------------------------------------------
    # Locations
    # -----------------------------------------------------

    locations = []

    for location in contacts.get(
        "locations",
        []
    ):

        locations.append(
            {
                "facility": location.get(
                    "facility"
                ),

                "city": location.get(
                    "city"
                ),

                "state": location.get(
                    "state"
                ),

                "country": location.get(
                    "country"
                )
            }
        )


    # -----------------------------------------------------
    # Normalized trial object
    # -----------------------------------------------------

    normalized = {

        "nct_id": nct_id,

        "title": title,

        "status": status.get(
            "overallStatus"
        ),

        "study_type": design.get(
            "studyType"
        ),

        "phase": design.get(
            "phases",
            []
        ),

        "enrollment": design.get(
            "enrollmentInfo",
            {}
        ).get(
            "count"
        ),

        "conditions": condition_list,

        "interventions": interventions,

        "sponsor": {
            "name": lead_sponsor.get(
                "name"
            ),

            "class": lead_sponsor.get(
                "class"
            )
        },

        "start_date": status.get(
            "startDateStruct",
            {}
        ).get(
            "date"
        ),

        "completion_date": status.get(
            "completionDateStruct",
            {}
        ).get(
            "date"
        ),

        "locations": locations,

        "source": {

            "database": "ClinicalTrials.gov",

            "source_id": nct_id,

            "url": (
                f"https://clinicaltrials.gov/study/{nct_id}"
                if nct_id
                else None
            )
        },

        "evidence_type": "observed"
    }

    return normalized


# =========================================================
# NCL RELEVANCE FILTER
# =========================================================

NCL_TERMS = [
    "neuronal ceroid lipofuscinosis",
    "batten disease",
    "cln2",
    "cln3",
    "cln5",
    "cln6",
    "cln7",
    "cln8"
]


def is_ncl_relevant(trial):

    """
    Keep the study only if the title or the structured
    ClinicalTrials.gov condition explicitly mentions
    NCL / Batten disease / a relevant CLN subtype.
    """

    title = trial.get(
        "title",
        ""
    )

    title = title.lower()


    conditions = trial.get(
        "conditions",
        []
    )


    # -----------------------------------------------------
    # Check title
    # -----------------------------------------------------

    for term in NCL_TERMS:

        if term in title:

            return True


    # -----------------------------------------------------
    # Check structured conditions
    # -----------------------------------------------------

    for condition in conditions:

        condition = condition.lower()

        for term in NCL_TERMS:

            if term in condition:

                return True


    # -----------------------------------------------------
    # Nothing matched
    # -----------------------------------------------------

    return False


# =========================================================
# MAIN PIPELINE
# =========================================================

def main():

    # -----------------------------------------------------
    # Create output directory
    # -----------------------------------------------------

    OUTPUT_DIR.mkdir(
        exist_ok=True
    )


    # -----------------------------------------------------
    # STEP 1: FETCH STUDIES
    # -----------------------------------------------------

    data = fetch_trials(
        SEARCH_TERM,
        MAX_STUDIES
    )

    studies = data.get(
        "studies",
        []
    )

    print(
        f"Studies retrieved: "
        f"{len(studies)}"
    )


    # -----------------------------------------------------
    # STEP 2: SAVE RAW RESPONSE
    # -----------------------------------------------------

    with open(
        RAW_OUTPUT,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


    print(
        f"Raw data saved to: "
        f"{RAW_OUTPUT}"
    )


    # -----------------------------------------------------
    # STEP 3: NORMALIZE + FILTER
    # -----------------------------------------------------

    normalized_trials = []

    filtered_count = 0


    for study in studies:

        try:

            trial = normalize_trial(
                study
            )


            # Ignore records without an NCT ID

            if not trial.get(
                "nct_id"
            ):

                continue


            # Check relevance

            if is_ncl_relevant(
                trial
            ):

                normalized_trials.append(
                    trial
                )

            else:

                filtered_count += 1

                print(
                    "Filtered out irrelevant study: "
                    f"{trial['nct_id']} - "
                    f"{trial['title']}"
                )


        except Exception as e:

            print(
                "Could not normalize study:",
                e
            )


    # -----------------------------------------------------
    # STEP 4: SAVE NORMALIZED JSONL
    # -----------------------------------------------------

    with open(
        NORMALIZED_OUTPUT,
        "w",
        encoding="utf-8"
    ) as f:

        for trial in normalized_trials:

            f.write(
                json.dumps(
                    trial,
                    ensure_ascii=False
                )
                + "\n"
            )


    print(
        f"Normalized trials saved to: "
        f"{NORMALIZED_OUTPUT}"
    )


    # -----------------------------------------------------
    # STEP 5: SUMMARY
    # -----------------------------------------------------

    print(
        "\nPipeline completed successfully."
    )

    print(
        f"Retrieved studies: "
        f"{len(studies)}"
    )

    print(
        f"Relevant NCL studies: "
        f"{len(normalized_trials)}"
    )

    print(
        f"Filtered studies: "
        f"{filtered_count}"
    )


    # -----------------------------------------------------
    # STEP 6: DISPLAY RELEVANT STUDIES
    # -----------------------------------------------------

    print(
        "\nRelevant Clinical Trials:"
    )


    for trial in normalized_trials:

        print(
            f"- {trial['nct_id']}: "
            f"{trial['title']}"
        )


# =========================================================
# PROGRAM ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()