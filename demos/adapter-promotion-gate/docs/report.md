# Adapter Promotion Gate: engineering report, revision 2

13 November 2026. This revision incorporates the independent cross-model audit. Its claims concern deterministic policy execution on authored fixtures, not adapter performance or clinical safety.

## Observed behavior

The current gallery executes **22 scenarios**: all expectations match, and **19 denied operations preserve the registry bytes**. The local suite has **68 passing tests**. The original Wave 2 gallery had 20 scenarios and 17 denials; two new cases demonstrate revoked approval after rollback and evidence expiring between approval and serving.

All adapter bytes and evaluation reports are invented. Canary outcomes are authored true/false statements in a synthetic report; no canary test was executed. A successful policy block means its declared input was accepted, not that a model passed a measured safety evaluation. The seven-day freshness window, 0.02 minimum gain and 0.01 maximum regression are development policy choices, not validated cutoffs. Thresholds apply after JSON binary64 parsing; decimal strings arbitrarily close to a cutoff can round to that cutoff.

## Evidence boundary

The fixture writer creates candidate, baseline and report files and a manifest of their digests. The gallery captures the manifest's digest in a separate review-anchor file **before** tampering scenarios run. Admission receives that anchor as a separate argument. This makes the sequencing visible but does not authenticate the simulated reviewer; an integration must obtain the anchor independently of the bundle it is admitting.

Actual admission order is registry validation, capacity, trust anchor, manifest schema, freshness, artifact paths/digests, baseline identity, report schema, metric bounds, mandatory canaries, thresholds and validated persistence. Each reached block writes an observation. A failure records its reason and stops execution; downstream blocks are absent, not reported as passing.

The report rejects non-finite or nonnumeric metrics through the **admission path**. The gain and regression ranges are checked before thresholds. The closed canary suite is exactly privacy, schema and tool boundary, with unique IDs and strict boolean values. An empty or incomplete suite cannot become a vacuous pass. Candidate bytes equal to baseline bytes are rejected as unchanged.

Successful admission stores the exact evaluation-report bytes and digest along with the candidate and its evidence summary. The gallery retains presented report bytes in base64 even for malformed JSON so the record stays valid JSON and a reviewer can inspect what was actually supplied. A hash binds bytes; it neither authenticates the evaluator nor establishes the truth of an evaluation claim.

## Lifecycle and storage

Admission reaches `shadow` only. An exact local `release-manager` label is required for explicit approval, serving or rollback. The same caller can supply that string; no identity or authorization service is implemented. Both approval and serving check evidence age and current baseline identity. Approval does not freeze evidence freshness.

Rollback restores the exact stored predecessor and puts the candidate in terminal `rolled_back` state. It cannot be served or approved again under that ID. Re-release requires a new admission and approval under a new ID. Rollback does not require fresh evaluation evidence, but it still requires a valid aware clock and intact predecessor evidence.

Registry schema version 2 stores a state snapshot after each audit event: every record's lifecycle state, the serving key and serving-byte digest. The reader reconstructs the audit and requires it to agree with the recorded snapshots and current state. The figure reads those snapshots directly; it has no copy of the transition rules. This catches a lifecycle edit without matching history. Stored `evaluated_at`, `manifest_sha256` and audit `at` values are trusted metadata, not bound to retained manifest bytes: changing `evaluated_at` alone can change freshness. A limitation regression demonstrates this. Other consistent rewrites also remain outside the trusted-filesystem boundary.

Displacement now sets `superseded`, preventing two candidates from serving repeatedly on reused approvals. Rollback may restore the exact superseded predecessor, and a nested rollback can restore its predecessor in turn. Each admitted ID has at most one explicit admission, approval, serve and rollback; further releases need a new ID. Existing registries from prior demo revisions are not migrated.

Reading and writing use the same `validate_state()` function. Before any temporary file is created, `_write()` serializes, reparses and validates the proposed state. Aware clocks are normalized to UTC; naive clocks fail before writing, including on rollback.

The input limit is **1,000,000 bytes per file**. Registry storage has a separate **8,000,000-byte** bound including base64 copies, stored reports and audit snapshots. Capacity is bounded at 64 records. Admission reserves 32,768 bytes per record for remaining lifecycle history. A regression fills the registry with five one-million-byte candidates, searches for the largest admissible final candidate, then completes approval, serving and rollback. Disconnecting the reservation makes that named regression fail.

The exclusive lock refuses competing writers rather than queueing them. Writes flush a same-directory temporary file and replace the registry. Failures before replacement preserve the old bytes. A hard crash can leave both the lock and a temporary file; neither is silently recovered. Windows readers can prevent replacement while a file is open. Lock cleanup failure after replacement can raise after the new revision was committed, so callers must inspect state before retrying. File fsync and replacement do not prove cross-platform power-loss durability. Version 1 registry migration is not implemented.

## Graphics and observed outcomes

The lifecycle replay starts at the initial registry. Every frame projects an actual before/after operation snapshot, and denied operations show unchanged state. Scenario-level final outcomes are explicitly separate from the selected frame. The gallery derives a successful rollback outcome from the candidate's terminal state, serving key and stored serving-byte hash; a no-op rollback fails the gallery's own check.

The **gate-stage ladder** contains one row per executed operation across all 22 scenarios. A checkmark means a reached policy block passed; a cross marks the block that stopped execution; hatched cells mean not evaluated. Cell numbers show actual execution order. Full registry hashes before and after each operation are in `results.json`, while the selected operation displays them as text. The downloadable SVG carries the authored-canary caveat.

On phones, the lifecycle uses readable labels and the ladder has stacked, expandable rows with each full scenario label beside its ordered checks and explicit unreached list. The downloadable SVG wraps full labels without dropping the authentication limitation. Unknown stages fail both projections. Previous/next buttons use `aria-disabled` and retain keyboard focus at the ends. Each results-table cell derives “Matches expected: yes/no” from its recorded `passed` value.

HTML and the ladder are rendered and validated before a successful result file is written. A rendering error therefore does not leave a new `results.json` claiming success. This is an ordering guarantee, not an atomic transaction across all exported files.

## Executed checks and reproducibility

```sh
python -B -m unittest discover -s tests -v
python -B -m promotion_gate.demo --output artifacts
python -B tests/verify_artifacts.py
```

The artifact verifier checks runtime source hashes, test/fixture-contract hashes and relative report links. CI now includes it. Generated text uses UTF-8 and LF. Runtime/Python metadata remains recorded, so byte equality requires the same source and runtime. The repository CI runs it on Python 3.11/3.13 on Linux/Windows.

Optional Playwright verification, `python -B tests/inspect_visuals.py`, checks all **55 recorded frames** at 1440px and 390px, keyboard changes and retained focus, denial state, reached-check text, no external requests or browser errors, and no page overflow. Current screenshots and observations use `qa/audit-*`. Earlier Wave 2 files remain labeled historical.

Nine comment-mutation contracts cover freshness at serving, closed canary IDs, unchanged candidates, pre-write state validation, audit/state binding, rollback revocation, admission metric wiring, observed gallery outcomes and lifecycle storage reservation. Each identifies the precise line replacement and named regression that must fail. This tests a bounded set of comment claims, not every sentence in the repository.

## Limits and next study

No model training, inference, patient data, clinical deployment or authenticated service is included. The filesystem, process and separately supplied anchor remain trusted. An engineering demonstration of policy checks is not evidence that a proposed model is safe. A next study requires a frozen model/baseline, measured evaluations with provenance and uncertainty, real canary execution, authenticated release decisions, and an external artifact service or stronger transactional storage as needed.
