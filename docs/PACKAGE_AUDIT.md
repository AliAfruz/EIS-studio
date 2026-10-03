# Publication-package audit

**Package:** EIS Gold Studio v1.13.2  
**Audit date:** 4 October 2026

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

The repository includes a clean GitHub Actions matrix for Python 3.10, 3.11, and 3.12. The first GitHub release must not be published until that workflow completes successfully on the exact release commit.

## Metadata still requiring owner confirmation

- Confirm that the public author form should be **Ali Afruz**.
- Add an ORCID only if the author supplies and verifies it.
- Add the final GitHub repository URL after repository creation.
- Add funding identifiers, affiliations, and Zenodo communities only when verified.
- Add the Zenodo DOI only after the first archived release is published.
