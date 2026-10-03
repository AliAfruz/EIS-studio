# Contributing

Contributions that improve scientific correctness, reproducibility, file-format support, numerical robustness, tests, accessibility, or documentation are welcome.

## Development setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

For headless testing on Linux or macOS, set `QT_QPA_PLATFORM=offscreen` before running:

```bash
python -m pytest
```

## Scientific contribution requirements

- State the equation, parameter units, bounds, limiting behavior, and literature basis for every new circuit element.
- Add synthetic recovery tests and at least one edge-case test.
- Do not label a heuristic as a formal statistical test.
- Keep mechanisms distinct from equivalent-circuit hypotheses.
- Preserve the canonical convention `Z = Z' + jZ''` and record every sign conversion.
- Update `CHANGELOG.md`, `docs/SCIENTIFIC_METHODS.md`, and citation metadata when a scientific method changes.

## Pull requests

Keep each pull request focused, explain the scientific or software motivation, list validation commands, and describe any user-visible or backward-incompatible change. By submitting a contribution, you agree that it may be distributed under the repository's MIT License.
