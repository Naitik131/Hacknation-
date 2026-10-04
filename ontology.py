"""Typed ontology lookup with LLM-generated aliases."""

import json
import re
import unicodedata
from pathlib import Path


NAMESPACES = ("gene", "disease", "phenotype")


def norm(s: str) -> str:
    """Normalize text for reliable matching."""

    s = unicodedata.normalize("NFKC", s)

    s = re.sub(
        r"[\u2010-\u2015\u2212]",
        "-",
        s,
    )

    s = re.sub(
        r"[\u2018\u2019\u201c\u201d]",
        "'",
        s,
    )

    return re.sub(
        r"\s+",
        " ",
        s,
    ).strip().lower()


def variants(name: str, etype: str) -> list[str]:
    """
    Generate deterministic variants of an extracted entity name.
    Only apply transformations that are high-confidence.
    """
    n = norm(name)
    out = [n]

    if etype == "gene":
        # CLN3 gene -> CLN3
        if n.endswith(" gene"):
            out.append(n[:-5].strip())

    elif etype == "disease":
        # Neuronal ceroid lipofuscinoses -> neuronal ceroid lipofuscinosis
        if n.endswith("oses"):
            out.append(n[:-3] + "is")

        # CLN3 Batten disease -> CLN3 disease
        if n.endswith(" batten disease"):
            out.append(n[:-14].strip() + " disease")

        # CLN7 neuronal ceroid lipofuscinosis -> CLN7 disease
        m = re.fullmatch(r"(cln\d+)\s+neuronal ceroid lipofuscinosis", n)
        if m:
            out.append(f"{m.group(1)} disease")

        # CLN7 -> CLN7 disease
        m = re.fullmatch(r"(cln\d+)", n)
        if m:
            out.append(f"{m.group(1)} disease")

    else:
        # Simple singular form
        if n.endswith("s") and len(n) > 4:
            out.append(n[:-1])

    return list(dict.fromkeys(out))

def provisional_id(
    etype: str,
    name: str,
) -> str:
    """
    Generate a provisional ID for entity types
    that do not yet have a canonical ontology.
    """

    return (
        f"PROV:{etype}:"
        + re.sub(
            r"[^a-z0-9]+",
            "-",
            norm(name),
        ).strip("-")
    )


class Ontology:

    def __init__(
        self,
        path: str = "data/ontology.json",
        aliases_path: str = "data/entity_aliases.json",
        phenotype_aliases_path: str = "data/phenotype_aliases.json",
    ):

        # --------------------------------------------------
        # Main ontology
        # --------------------------------------------------

        self.maps = json.loads(
            Path(path).read_text()
        )

        # --------------------------------------------------
        # Existing LLM-generated aliases
        # gene / disease / phenotype
        # --------------------------------------------------

        self.aliases = {}

        alias_file = Path(
            aliases_path
        )

        if alias_file.exists():

            for item in json.loads(
                alias_file.read_text()
            ):

                if (
                    item.get("canonical_id")
                    and item.get("surface_form")
                    and item.get("entity_type")
                    and item.get("confidence")
                    in {"high", "medium"}
                ):

                    key = (
                        item["entity_type"],
                        norm(
                            item["surface_form"]
                        ),
                    )

                    self.aliases[key] = (
                        item["canonical_id"]
                    )

        # --------------------------------------------------
        # HPO-specific phenotype aliases
        # --------------------------------------------------

        self.phenotype_aliases = {}

        phenotype_alias_file = Path(
            phenotype_aliases_path
        )

        if phenotype_alias_file.exists():

            for item in json.loads(
                phenotype_alias_file.read_text()
            ):

                if (
                    item.get("canonical_id")
                    and item.get("surface_form")
                    and item.get("confidence")
                    in {"high", "medium"}
                ):

                    key = norm(
                        item["surface_form"]
                    )

                    self.phenotype_aliases[key] = (
                        item["canonical_id"]
                    )

    def resolve(
        self,
        name: str,
        etype: str,
    ):
        """
        Resolve an entity name to a canonical ontology ID.

        Resolution order:

        1. Exact ontology match
        2. Deterministic name variants
        3. LLM-generated aliases
        4. HPO phenotype aliases
        5. None
        """

        m = self.maps.get(
            etype,
            {},
        )

        # --------------------------------------------------
        # 1. Exact ontology match
        # --------------------------------------------------

        for v in variants(
            name,
            etype,
        ):

            if v in m:
                return m[v]

        # --------------------------------------------------
        # 2. Existing LLM-generated aliases
        # --------------------------------------------------

        for v in variants(
            name,
            etype,
        ):

            alias = self.aliases.get(
                (
                    etype,
                    v,
                )
            )

            if alias:
                return alias

        # --------------------------------------------------
        # 3. HPO-specific phenotype aliases
        # --------------------------------------------------

        if etype == "phenotype":

            for v in variants(
                name,
                etype,
            ):

                alias = self.phenotype_aliases.get(
                    v
                )

                if alias:
                    return alias

        # --------------------------------------------------
        # Nothing found
        # --------------------------------------------------

        return None

    def entity_id(self, name, etype):
    # Gene, disease, phenotype must resolve to canonical ontology IDs.
        if etype in NAMESPACES:
            return self.resolve(name, etype)

        # Mechanisms, pathways, molecules, treatments, and other
        # entities can remain evidence-backed provisional nodes.
        return provisional_id(etype, name)

        # Canonical ontology namespaces
        if etype in NAMESPACES:

            return self.resolve(
                name,
                etype,
            )

        # Other entity types currently
        # use provisional IDs.
        return provisional_id(
            etype,
            name,
        )