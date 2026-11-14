# Synthetic promotion protocol version 2

Date: 13 November 2026. Status: development and engineering verification protocol. The fixtures and implementation were developed together; this is not a preregistered empirical model comparison or an independent test dataset.

## Question

Does the public admission and release path enforce each specified evidence, lifecycle, and persistence boundary when a synthetic evaluation report violates it?

## Inputs and constants

The baseline and candidate are short original byte strings. Evaluation data is invented and labeled `synthetic_fixture`. The report includes gain, regression, and one Boolean result for each required canary: privacy, schema and tool boundary.

The eligibility policy requires gain at least 0.02, regression at most 0.01, all mandatory canaries present and passing, finite metrics within their declared ranges, and a verified manifest. Evaluation age must be between zero and seven days. The evaluation baseline must match the currently serving artifact. These thresholds are illustrative policy constants; they are not validated clinical or statistical cutoffs.

Every bundle contains candidate, baseline and report bytes. A manifest records their SHA-256 digests and the evaluation time. The caller supplies a separately trusted digest of the manifest. Changing either content or manifest after that review is a rejection. The default demonstration clock is fixed at 2026-11-13 12:00 UTC for replay; the Registry API uses the current UTC clock unless a test injects one.

## Gallery

Twenty-two authored cases isolate valid shadow admission, failed mandatory canary despite high gain, NaN, infinity, Boolean metric, impossible negative regression, empty suite, missing canary, duplicate canary, insufficient gain, excess regression, exact threshold equality, stale evidence, mismatched baseline, artifact tampering, manifest tampering, exhausted capacity, attempted shadow serving, unauthorized approval, the complete approval/serve/rollback cycle, re-serving after rollback, and evidence expiring after approval.

Each rejection compares the entire registry file before and after the denied operation. A changed byte fails the run. The complete lifecycle checks that rollback returns to the original serving record, whose stored bytes are checked against their digest whenever the registry is read.

## Acceptance criteria

1. Every gallery case matches its expected reason or successful state.
2. Every denial preserves the prior registry bytes.
3. A shadow record cannot become serving without explicit approval.
4. Baseline drift and stale evidence prevent release.
5. Failed writes before atomic replacement preserve old state and permit a later retry.
6. Competing writer locks are refused rather than bypassed.
7. Corrupt or missing rollback evidence blocks rollback.
8. Reports escape fixture text and contain no remote assets.
9. Rollback revokes approval; re-release requires a new admission under a new ID.
10. Read and write use the same audit/state validator, clocks are aware UTC, and admission reserves lifecycle storage.
11. Figures read recorded state and reached-check logs; successful gallery outcomes are derived from stored values.

An unexpected exception or mismatched gallery result exits nonzero. Unit tests cover additional malformed inputs, duplicate JSON keys, path traversal, update/retry behavior and HTML escaping.

## Reporting

Count scenarios and observed denials; do not call these counts model accuracy. Publish raw per-case outcomes and audit events, source and test hashes, Python runtime, fixed simulation clock, and the generator. No p-values or confidence intervals are appropriate for these deterministic authored examples. They demonstrate specified behavior, not generalization to unseen model failures.

## Reproduction limits

The report has a Python-version field, so byte-for-byte report equality requires the same runtime. Under the same source and runtime, no randomness or wall-clock timestamp enters the default gallery output. Platform-specific filesystem behavior still needs testing; the CI matrix is configured but its remote results must be reported separately.
