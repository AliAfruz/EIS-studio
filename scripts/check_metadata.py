"""Check agreement between publication metadata; CFF schema is checked by cffconvert."""
from __future__ import annotations

import ast
from datetime import date
import json
from pathlib import Path
import re

import bibtexparser
from bibtexparser.bparser import BibTexParser
import yaml

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def orcid_id(value: str) -> str:
    if not value:
        return ""
    identifier = value.removeprefix("https://orcid.org/")
    require(bool(re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", identifier)),
            f"Invalid ORCID format: {value}")
    digits = identifier.replace("-", "")
    total = 0
    for digit in digits[:-1]:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    require(digits[-1] == ("X" if check == 10 else str(check)),
            f"Invalid ORCID checksum: {value}")
    return identifier


def main() -> None:
    cff = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    zenodo = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    codemeta = json.loads((ROOT / "codemeta.json").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    entries = bibtexparser.loads((ROOT / "CITATION.bib").read_text(encoding="utf-8"),
                                parser=parser).entries
    require(len(entries) == 1, "CITATION.bib must contain one software citation.")
    bib = entries[0]
    require(bib["ENTRYTYPE"] == "software", "BibTeX resource type must be software.")
    require(cff["type"] == zenodo["upload_type"] == "software", "Resource types differ.")
    require(codemeta["@type"] == "SoftwareSourceCode", "CodeMeta resource type differs.")
    require(cff["title"] == zenodo["title"] == codemeta["name"] == bib["title"],
            "Software titles differ.")
    require(cff["abstract"] == zenodo["description"] == codemeta["description"],
            "Full software descriptions differ.")
    version = str(cff["version"])
    require(all(str(value) == version for value in
                (zenodo["version"], codemeta["version"], project["version"], bib["version"])),
            "Software versions differ.")
    version_nodes = [node for node in ast.parse((ROOT / "eis_studio" / "__init__.py")
                                               .read_text(encoding="utf-8")).body
                     if isinstance(node, ast.Assign) and any(
                         isinstance(target, ast.Name) and target.id == "__version__"
                         for target in node.targets)]
    require(len(version_nodes) == 1 and ast.literal_eval(version_nodes[0].value) == version,
            "Application version differs from citation metadata.")
    release_date = str(cff["date-released"])
    date.fromisoformat(release_date)
    require(zenodo["publication_date"] == codemeta["datePublished"] == release_date,
            "Publication dates differ.")
    require(bib["year"] == release_date[:4], "BibTeX publication year differs.")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", cff["commit"])), "Invalid release commit.")
    require(all(value == cff["keywords"] for value in
                (zenodo["keywords"], codemeta["keywords"], project["keywords"])),
            "Software keywords differ.")
    require(len(set(cff["keywords"])) == len(cff["keywords"]), "Duplicate keywords.")
    require(cff["license"].lower() == zenodo["license"].lower() == bib["license"].lower(),
            "Licenses differ.")
    require(codemeta["license"] == f'https://spdx.org/licenses/{cff["license"]}',
            "CodeMeta SPDX license differs.")
    require(zenodo["access_right"] == "open", "Archive visibility must be open.")
    require(project["license"]["file"] == "LICENSE", "Package license file differs.")
    require(cff["repository-code"] == codemeta["codeRepository"] == project["urls"]["Homepage"]
            == project["urls"]["Repository"].removesuffix(".git"), "Repository URLs differ.")
    authors = cff["authors"]
    require(len(authors) == len(zenodo["creators"]) == len(codemeta["author"])
            == len(project["authors"]), "Creator counts differ.")
    bib_names = []
    author_text = (ROOT / "AUTHORS.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    for index, author in enumerate(authors):
        given, family = author["given-names"], author["family-names"]
        full_name = f"{given} {family}"
        bib_names.append(f"{family}, {given}")
        creator, person, package_author = (zenodo["creators"][index], codemeta["author"][index],
                                           project["authors"][index])
        require(creator["name"] == f"{family}, {given}" and person["givenName"] == given
                and person["familyName"] == family and package_author["name"] == full_name,
                f"Creator name/order differs at position {index + 1}.")
        require(full_name in author_text and full_name in readme and full_name in license_text,
                f"Creator missing from authors, README, or copyright: {full_name}.")
        require(author.get("affiliation", "") == creator.get("affiliation", "")
                == person.get("affiliation", {}).get("name", ""),
                f"Affiliation differs for {full_name}.")
        require(author.get("email", "") == person.get("email", "")
                == package_author.get("email", ""), f"Contact email differs for {full_name}.")
        orcid = orcid_id(author.get("orcid", ""))
        require(orcid == orcid_id(creator.get("orcid", "")) == orcid_id(person.get("@id", "")),
                f"ORCID differs for {full_name}.")
        if orcid:
            uri = f"https://orcid.org/{orcid}"
            require(author["orcid"] == person["@id"] == uri and creator["orcid"] == orcid,
                    f"ORCID representation is incorrect for {full_name}.")
            require(uri in author_text and uri in readme
                    and project["urls"].get(f"{full_name} ORCID") == uri,
                    f"Public ORCID links differ for {full_name}.")
    require(bib["author"] == " and ".join(bib_names), "BibTeX author order differs.")
    doi = cff["doi"]
    uri = f"https://doi.org/{doi}"
    require(doi == bib["doi"] and uri == bib["url"] == codemeta["identifier"]
            == project["urls"]["Version DOI"], "Version DOI links differ.")
    concept_ids = [item["value"] for item in cff["identifiers"] if item["type"] == "doi"]
    require(len(concept_ids) == 1 and concept_ids[0] != doi, "Concept and version DOI differ incorrectly.")
    concept = concept_ids[0]
    require(project["urls"]["All versions DOI"] == f"https://doi.org/{concept}",
            "Concept DOI link differs.")
    require(uri in readme and f"https://doi.org/{concept}" in readme
            and f"https://zenodo.org/badge/DOI/{concept}.svg" in readme, "README DOI links differ.")
    require(not zenodo.get("doi"), "Do not pin an existing version DOI in future-release imports.")
    print(f"PASS: citation, archive, package and author metadata agree for version {version}.")


if __name__ == "__main__":
    main()
