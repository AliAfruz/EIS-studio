# GitHub and Zenodo release procedure

Version 1.13.2 was published and archived on 5 October 2026:

- [GitHub release v1.13.2](https://github.com/AliAfruz/EIS-studio/releases/tag/v1.13.2), commit `36b3237fcfd6a36b011249294d649b3a493035ce`.
- Version DOI: [10.5281/zenodo.23154102](https://doi.org/10.5281/zenodo.23154102).
- Concept DOI (all versions): [10.5281/zenodo.23154101](https://doi.org/10.5281/zenodo.23154101).

The release commit passed the Python 3.10, 3.11, and 3.12 regression jobs and the package build/check job in [GitHub Actions](https://github.com/AliAfruz/EIS-studio/actions/runs/37172266192). The DOI citation update is a subsequent commit on `main`; the published tag and archived release retain their original contents.

## 1. Complete metadata before publishing

1. Confirm the creator order, names, email, and affiliations in `CITATION.cff`, `.zenodo.json`, `codemeta.json`, `pyproject.toml`, `AUTHORS.md`, and `LICENSE`.
2. Add an ORCID only after the author has confirmed the exact identifier.
3. Confirm the repository URL is `https://github.com/AliAfruz/EIS-studio`.
4. Add funding and community identifiers to `.zenodo.json` only when verified.
5. Do not invent a DOI. Zenodo assigns it after archiving the release.

`CITATION.cff` is used by GitHub's **Cite this repository** interface. When `.zenodo.json` and `CITATION.cff` are both present, Zenodo uses `.zenodo.json` for the archived release metadata, so the two files must remain consistent.

## 2. Validate locally

```bash
python -m pip install -e ".[test,release]"
python -m pytest
python -m build
python -m twine check dist/*
```

Also confirm that `.zenodo.json` and `codemeta.json` are valid JSON and inspect the source archive to ensure that it contains no credentials, private datasets, caches, or local machine paths.

## 3. Publish on GitHub

The configured GitHub repository is `https://github.com/AliAfruz/EIS-studio.git`. It is already initialized and linked to `origin`. Commit and push the reviewed changes for a future version from this project directory:

```bash
git add .
git commit -m "Prepare next release"
git push origin main
```

Protect the `main` branch and require the test workflow if appropriate.

## 4. Connect Zenodo

1. Sign in to Zenodo and connect the intended GitHub account.
2. Open the Zenodo GitHub integration page and synchronize the repository list.
3. Enable the EIS Gold Studio repository.
4. Return to GitHub and draft a new version tag from the tested commit. `v1.13.2` is already published; use a new version number for a future release.
5. Use the relevant `CHANGELOG.md` section as release notes and publish the release.
6. Wait for Zenodo to process the release, then inspect the record metadata and files.

## 5. Record the DOI

After Zenodo assigns the DOI:

1. add the DOI to `CITATION.cff`;
2. add a DOI badge and citation example to `README.md`;
3. add the concept DOI or version DOI deliberately—state which one is used;
4. update the version DOI and release date in `CITATION.bib` and `codemeta.json`;
5. commit the metadata update for the next release.

Use a version-specific DOI when citing an exact software release. Use the concept DOI when the citation should resolve to the latest archived version.

The existing citation files use the v1.13.2 version DOI, while the README badge uses the concept DOI. Before a future release, update the version/date metadata and remove the old version DOI from citation fields until the new archive has its own DOI. Keep the concept DOI as the stable project identifier.

## Manual Zenodo alternative

If GitHub integration cannot be used, upload **one ZIP archive** of the source tree as a Zenodo Software record. Review Zenodo's current archival requirements before publishing.
