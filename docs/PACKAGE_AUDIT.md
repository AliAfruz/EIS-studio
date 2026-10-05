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
- Second creator: **Maryam Kaffash Jamshid**.
- Canonical source repository: `https://github.com/AliAfruz/EIS-studio`.
- Published archive: **5 October 2026**, version **1.13.2**, MIT License.
- Version DOI: [10.5281/zenodo.23154102](https://doi.org/10.5281/zenodo.23154102).
- Concept DOI (all versions): [10.5281/zenodo.23154101](https://doi.org/10.5281/zenodo.23154101).

The DOI registration, creator order, Ali Afruz's affiliation, version, issue date, license, and version/concept relationship were verified against the public DataCite registry. The DOI badge and citation metadata were added to `main` after archiving; the published release tag and its archived files retain their original contents.

## Metadata still requiring confirmation

- Add creator ORCIDs only if each creator supplies and verifies the exact identifier.
- Add Maryam Kaffash Jamshid's affiliation only when confirmed.
- Add funding identifiers and Zenodo communities only when verified.
