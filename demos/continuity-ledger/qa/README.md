# Verification record

`review-*` files and `recheck-verification.json` describe the latest re-check revision: observed worker counts, protected gate-off actions, all verdicts, 57 measured budget points and readable phone transition cards. The parent portfolio's clean-copy and mutation harness provide final reproduction evidence. Original author-selected cases and independently selected reviewer cases remain distinct in that dossier.

Unprefixed `test-results.txt` and `browser-results.json` describe the original release; `test-results-wave2.txt`, `visual-*` and `wave2-preservation.json` describe the earlier presentation upgrade. They are retained as historical evidence, not substituted for the current revision's checks.

Run `python -B tests/inspect_visuals.py` from the package root for optional Playwright verification. Runtime and unit tests require no third-party packages.
