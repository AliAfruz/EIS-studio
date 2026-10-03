# GitHub and Zenodo release procedure

This repository is prepared for a GitHub release that can be archived automatically by Zenodo.

## 1. Complete metadata before publishing

1. Confirm the author name and email in `CITATION.cff`, `.zenodo.json`, `codemeta.json`, `pyproject.toml`, `AUTHORS.md`, and `LICENSE`.
2. Add an ORCID only after the author has confirmed the exact identifier.
3. Add the final GitHub repository URL to `codemeta.json` after the remote repository exists.
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

Create an empty GitHub repository, then from this project directory run:

```bash
git init -b main
git add .
git commit -m "Release EIS Gold Studio v1.13.2"
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

Protect the `main` branch and require the test workflow if appropriate.

## 4. Connect Zenodo

1. Sign in to Zenodo and connect the intended GitHub account.
2. Open the Zenodo GitHub integration page and synchronize the repository list.
3. Enable the EIS Gold Studio repository.
4. Return to GitHub and draft release tag `v1.13.2` from the tested commit.
5. Use the relevant `CHANGELOG.md` section as release notes and publish the release.
6. Wait for Zenodo to process the release, then inspect the record metadata and files.

## 5. Record the DOI

After Zenodo assigns the DOI:

1. add the DOI to `CITATION.cff`;
2. add a DOI badge and citation example to `README.md`;
3. add the concept DOI or version DOI deliberately—state which one is used;
4. update the repository URL in `codemeta.json`;
5. commit the metadata update for the next release.

Use a version-specific DOI when citing an exact software release. Use the concept DOI when the citation should resolve to the latest archived version.

## Manual Zenodo alternative

If GitHub integration cannot be used, upload **one ZIP archive** of the source tree as a Zenodo Software record. Review Zenodo's current archival requirements before publishing.
