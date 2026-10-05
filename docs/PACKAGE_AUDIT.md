# Publication-package audit

**Package:** EIS Gold Studio v1.13.2  
**Audit date:** 5 October 2026

## Completed checks

- `.zenodo.json` and `codemeta.json` parsed successfully as JSON.
- `pyproject.toml` parsed successfully with Python's standard TOML parser.
- Every Python source and test file compiled successfully with `compileall`.
- The project built successfully as `eis_gold_studio-1.13.2-py3-none-any.whl` without resolving runtime dependencies.
- The wheel contains the packaged PNG/ICO assets, console entry point, and MIT license.
- The source ZIP contains `LICENSE`, `CITATION.cff`, `.zenodo.json`, GitHub Actions, scientific-method documentation, tests, samples, and packaged assets.
- The source ZIP contains no `__pycache__`, `.pyc`, build, `dist`, or `.egg-info` content.
- A text scan found no local absolute paths, private-key headers, GitHub-token patterns, or Zenodo-token patterns in the publication tree.
- SHA-256 checksums are provided for distributable artifacts.

## Runtime-test status

The original v1.13.2 changelog records 40 passing regression tests. During preparation of this publication package, a fresh local test environment was attempted, but the external package download was repeatedly reset while fetching the Matplotlib `fonttools` dependency. Therefore, the complete suite was **not independently re-executed in the packaging environment**.

The released commit `36b3237fcfd6a36b011249294d649b3a493035ce` subsequently passed all regression jobs on Python 3.10, 3.11, and 3.12, plus the distribution build and Twine check, in [GitHub Actions run 37172266192](https://github.com/AliAfruz/EIS-studio/actions/runs/37172266192). The v1.13.2 GitHub release points to that tested commit.

## Confirmed publication metadata

- First creator: **Ali Afruz**, University of Mohaghegh Ardabili.
- Ali Afruz's ORCID: [0000-0002-2969-8428](https://orcid.org/0000-0002-2969-8428), supplied by the creator and matched to the public ORCID record's given name **Ali** and family name **Afruz**.
- Second creator: **Maryam Kaffash Jamshid**.
- Canonical source repository: `https://github.com/AliAfruz/EIS-studio`.
- Published archive: **5 October 2026**, version **1.13.2**, MIT License.
- Version DOI: [10.5281/zenodo.23154102](https://doi.org/10.5281/zenodo.23154102).
- Concept DOI (all versions): [10.5281/zenodo.23154101](https://doi.org/10.5281/zenodo.23154101).

The DOI registration, creator order, Ali Afruz's affiliation, version, issue date, license, and version/concept relationship were verified against the public DataCite registry. The DOI badge and citation metadata were added to `main` after archiving; the published release tag and its archived files retain their original contents.

The ORCID update uses the bare identifier in `.zenodo.json` and the canonical HTTPS URI in `CITATION.cff` and CodeMeta's author `@id`. The title, full software description, creator order, keywords, version, and publication date agree across the structured citation files. The Python package retains a shorter summary description and supplies both DOI links and Ali Afruz's ORCID as project URLs. The published v1.13.2 tag is the release commit recorded in `CITATION.cff`.

The GitHub Actions metadata job validates `CITATION.cff` against its official schema with `cffconvert`, then runs `scripts/check_metadata.py` to check publication metadata agreement, including author order, affiliations, contact email, ORCID format/checksum, application/package versions, keywords, publication dates, SPDX license and version/concept DOI links. These checks do not infer missing creator information.

## Metadata still requiring confirmation

- Add Maryam Kaffash Jamshid's ORCID only if she supplies and verifies the exact identifier.
- Add Maryam Kaffash Jamshid's affiliation only when confirmed.
- Add funding identifiers and Zenodo communities only when verified.
