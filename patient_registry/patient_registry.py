import json
import time
from pathlib import Path

import requests


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

RAW_FILE = DATA_DIR / "registry_raw.jsonl"
NORMALIZED_FILE = DATA_DIR / "registries.jsonl"
REJECTED_FILE = DATA_DIR / "registry_rejected.jsonl"


REGISTRIES = [
    {
        "id": "registry:orphanet:311059",
        "name": (
            "Batten Disease Neuronal Ceroid "
            "Lipofuscinosis (NCL) Patient Registry"
        ),
        "source": "Orphanet",
        "source_url": (
            "https://www.orpha.net/en/"
            "research-trials/registry/311059"
        ),
        "disease": (
            "Neuronal Ceroid Lipofuscinosis"
        ),
        "country": "United Kingdom",
    }
]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/149.0 Safari/537.36"
    )
}


# ============================================================
# FETCH SOURCE PAGE
# ============================================================

def verify_registry(registry):

    url = registry["source_url"]

    print()
    print(f"Verifying: {registry['name']}")
    print(f"URL: {url}")

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )

        print(
            f"HTTP status: {response.status_code}"
        )

        # Orphanet may return 403 to automated requests.
        # The registry itself is still a known source-backed
        # candidate, so we preserve the source URL and metadata.
        if response.status_code == 200:

            html = response.text

            registry["retrieval_status"] = (
                "verified_by_http"
            )

            registry["html_length"] = len(html)

        else:

            registry["retrieval_status"] = (
                "source_page_known_but_http_blocked"
            )

            registry["http_status"] = (
                response.status_code
            )

    except Exception as e:

        registry["retrieval_status"] = (
            "source_page_known_but_fetch_failed"
        )

        registry["fetch_error"] = str(e)

    registry["retrieved_at"] = (
        time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        )
    )

    return registry


# ============================================================
# MAIN
# ============================================================

def main():

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 70)
    print("PATIENT REGISTRY EXTRACTION")
    print("=" * 70)

    normalized = []
    rejected = []

    for registry in REGISTRIES:

        result = verify_registry(
            registry.copy()
        )

        normalized.append(result)

        time.sleep(1)

    # --------------------------------------------------------
    # Raw registry records
    # --------------------------------------------------------

    with open(
        RAW_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        for record in normalized:

            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )

    # --------------------------------------------------------
    # Normalized records
    # --------------------------------------------------------

    with open(
        NORMALIZED_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        for record in normalized:

            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )

    # --------------------------------------------------------
    # Rejected records
    # --------------------------------------------------------

    with open(
        REJECTED_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        for record in rejected:

            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("PATIENT REGISTRY EXTRACTION COMPLETE")
    print("=" * 70)

    print(
        f"Registry candidates: {len(normalized)}"
    )

    print(
        f"Rejected: {len(rejected)}"
    )

    print()
    print("Output:")
    print(f"  {RAW_FILE}")
    print(f"  {NORMALIZED_FILE}")
    print(f"  {REJECTED_FILE}")

    print("=" * 70)


if __name__ == "__main__":
    main()