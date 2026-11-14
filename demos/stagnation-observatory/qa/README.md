# Verification records

The **`audit-*` files describe the 70-test revision after Flame Johnson's second 13 November review**. The current browser entry point is `inspect_report.py`, also reachable through the compatibility command `python -B tests/inspect_report.py`.

- `audit-browser-results.json`: 26 selectable scenarios, 164 event frames checked at each desktop/phone width, local-only execution, keyboard and SVG export, fixed lane labels, adjacent limitation card and first-view geometry.
- `audit-first-view-*.png`, `audit-replay-*.png`, `audit-conformance-*.png`: screenshots of the current revised report.
- `recheck-summary-phone.png`, `recheck-cadence-phone.png`: complete phone figures, including the caveat and every gap. The implementation reviewer inspected these images after the browser assertions passed.
- `audit-timeline-*.svg`: exported timelines from the revised browser checks, including lane labels.
- `audit-test-results.txt`: the current 70-test package execution. Independent clean-copy verification is recorded separately by the portfolio release workflow.

Unprefixed `test-results.txt`, `browser-results.json`, `report-*.png`, `timeline-export-*.svg`, and `review-notes.md` are **historical Wave 2 evidence**. They describe the former 27-test / 24-picker implementation and are retained for comparison, not as the current verification result. The immutable Wave 2 delivery also preserves that entire earlier version.

The source, test and generated-file hashes in the lead's release evidence determine the exact reviewed revision. A screenshot alone establishes neither the scientific claim nor the trusted-input boundary.
