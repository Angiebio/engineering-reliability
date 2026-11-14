# Continuity Ledger methods and results

13 November 2026 · Protocol `continuity-ledger-v2` · Local Python 3.13.5 · Post-audit development demonstration

## Question

After a real process restart, can an administrative agent recover a commitment while respecting a later completion, pause or authorization withdrawal? This release demonstrates an explicit evidence boundary: the remembered proposal and the authoritative eligibility decision are separately recorded.

This is deterministic engineering evidence. No language model was called, no patient data was used, and no action dispatcher exists. The scores below describe original development fixtures, not clinical safety, a held-out benchmark or LLM memory quality.

## Design

The evaluator writes canonical, content-addressed snapshots and retains their expected SHA-256 manifests. A fresh Python process verifies and reads each snapshot, then selects memory. A second fresh process receives only selected context and returns a deterministic proposal. The evaluator independently restores the authoritative snapshot and checks the proposal against its current state. Both parent and worker reject undeclared stdin fields. Labels are excluded from requests and written only after all workers finish. Existing local files are not hidden from the worker by an OS sandbox.

The workers use `python -I -B`, explicit JSON over standard input and output, a nonzero exit on error and a 15-second timeout. Process IDs appear in each result. This establishes separate invocations and explicit input flow; it is not an operating-system sandbox. A worker has normal local filesystem permissions even though its implementation consumes only the declared inputs.

Each event carries an event ID, task ID, sequence, kind, source role, original text and a supersession reference. The validator rejects duplicate IDs, non-increasing order, unknown fields or kinds, invalid transitions, and supersession of another task or a stale head. External notes cannot change state. The `controller` role is a trusted fixture assertion; real integrations must authenticate their input channel.

The proposal reader uses the newest selected authoritative event. Because selected context may be incomplete, that event can be stale. The gate requires exact equality between proposed evidence and its source, the correct task identity, the latest authoritative event ID, and an active current state. Thus an old approval cannot override a later revocation. A proposal to hold or abstain remains visible and cannot count as a successful resumption.

## Fixtures and budgets

The fixture generator authors 24 administrative histories: 12 active, 4 completed, 4 paused and 4 blocked. Task content concerns synthetic referral packets, document inventories, review agendas and scheduling checklists. There are no treatment or patient-specific decisions. Reopening, reauthorization and pause/resume transitions prevent permanently hard-coding completed or blocked tasks as ineligible.

Each final-state category includes four distractor schedules: none, a short quoted instruction, a longer quoted instruction, and two long external notes. A request for an unrelated neighboring task is filtered out by exact identity before packing and cannot affect selection. The schedule distribution is intentionally a coverage matrix, not a model of real-world frequencies. The fixture set and implementation were developed together and changed during implementation; no preregistration or independent test set is claimed.

All memory inputs contain exact event records, without expected labels or precomputed final-state fields. Event kinds are typed metadata, so the timeline selector has a structured signal unavailable in an unstructured conversational corpus.

| Arm | Method | Constraint |
| --- | --- | --- |
| Raw tail | Filter to target task, pack newest complete records first | 640 canonical UTF-8 bytes including context envelope |
| Timeline | Same packing, omit note events using structured kind metadata | Same 640-byte ceiling |
| Full history | All records for the target task | Unbudgeted diagnostic |

Whole-event packing skips a record that will not fit and may retain an older, shorter record. This behavior is transparent in the saved context and is why the authoritative gate is necessary. Budgets smaller than the empty context envelope are rejected. UTF-8 byte counts include non-ASCII text and JSON syntax in the context object; the operation wrapper on worker stdin is excluded. These are not token counts or cost estimates.

Raw tail is a simple recency baseline. It does not implement Ying's recursive-summary baseline, semantic retrieval, ProactMem or FlexA-Mem. Timeline is a structured selector, not NLP memory. A future model-backed comparison must implement and identify those memory policies separately.

## Measured output

The original matrix remains 72 history/strategy combinations and 144 fresh subprocess invocations. The revision adds 36 longer-terminal control rows with 72 invocations, and 12 actual raw-tail gate-off reruns with 24 invocations: **240 real subprocess calls** in total. Controls do not enter the table below. `artifacts/results.json` retains module hashes, original histories/labels hashes, every control context and proposal, manifests and process IDs. Process IDs change across reruns; semantic outcomes and content-addressed snapshots are deterministic for identical code and fixtures.

| Strategy | Correct eligible resumptions | Eligible tasks not resumed | Reader abstentions | Ineligible resumptions before gate | Ineligible resumptions after gate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Raw tail | 9/12 | 3/12 | 6/24 | 0/12 | 0/12 |
| Timeline | 12/12 | 0/12 | 0/24 | 0/12 | 0/12 |
| Full history | 12/12 | 0/12 | 0/24 | 0/12 | 0/12 |

Proposal-level eligible-task F1 is 0.8571 for raw tail and 1.0 for timeline/full history. These scores depend on authored note lengths and the 640-byte choice. Raw tail abstains in the six two-long-note cases because no authoritative record survives; three are eligible. Timeline excludes precisely those note distractors. This does not estimate out-of-distribution performance or superiority over a strong retrieval system. In this original matrix, terminal records cannot be excluded in favor of a shorter older active record; zero unsafe proposals is structural. Zero unsafe final actions is a policy invariant conditional on the trusted ledger and correct checker, not an independent empirical safety estimate.

## Budget sensitivity

The dial selects measured points from 200 to 1000 bytes, including both sides of the important packing transitions. Each point calls the actual `render_memory`, `propose` and `check_proposal` functions in-process. It is explicitly separate from restart evidence; no subprocess calls are attributed to the sweep. `budget-sweep.json` retains every per-case selection, decision and count. `budget-sweep.svg` embeds its scope and fixture-dependence caveat.

Observed raw-tail eligible resumptions are 12/12 at 541 bytes, 9/12 at 542, 10/12 at 735, 11/12 at 741 and 12/12 at 746. The 9/12 interval is 542–734. A second cliff drops from 9/12 at 284 to 6/12 at 285 and 3/12 at 288. The 57 recorded budgets include both sides of those changes. The figure plots discrete measured marks instead of connecting sparsely measured points with a misleading continuous line. Its reference marker and count caption come from the supplied sweep data. Phone cards list observed transition brackets; unmeasured values between samples are not implied. More budget can admit distracting notes before it can fit the current instruction. Timeline is 12/12 from 244 bytes on these fixtures; full history remains a separately labeled unbudgeted diagnostic. No monotonicity or general memory-performance claim is made.

## Deliberate failure controls

The direct stale-request probe supplies an old active request after a later completion. Its input row is now labeled **Proposal before gate (planted)**. It is not called an ablation. The gate returns `hold` with `stale_evidence`; other direct probes assert exact reasons rather than merely checking hold.

The real ablation uses 12 separately labeled histories whose terminal messages contain 200 additional characters of administrative filing detail. This changes record length without changing task state. The actual raw-tail reader naturally cites stale active evidence in `natural-case14`, `natural-case18` and `natural-case22`. The shared runner holds all three with `stale_evidence`. A second restore/propose execution for each history bypasses only the gate and records three unsafe resumptions. Both arms retain real worker outputs and process evidence; no unsafe action is dispatched. The three-strategy control rows are selectable in the explorer but remain outside the original matrix.

The gate-off action must equal the reader's actual action, including hold and abstain; a literal resume is rejected by the tests. The worker transport counts actual completed subprocess invocations. A separate test spy independently sees all 240 calls and confirms disjoint worker IDs for every gated/bypassed twin. This prevents a copied row from being credited as an independent execution. In the longer-terminal family, timeline can also propose stale resumptions at smaller budgets, so its structured selection does not replace the authority gate.

Additional report controls hold fabricated source text (`unbound_evidence`), missing evidence (`missing_evidence`) and a mismatched task (`wrong_task`). Tests additionally cover old approval after revocation, exact latest evidence for a superseded task, external content pretending to authorize, invalid transitions, cross-task references, empty contexts, Unicode byte accounting, long task IDs, report escaping, missing/partial/corrupt snapshots, path traversal in manifests, worker failures and true subprocess replay.

An always-blocking gate cannot pass the end-to-end check: all 12 eligible full-history and timeline proposals must remain eligible. Conversely, the natural stale control traverses the shared `run()` path and fails when its gate call is disconnected. Current-head forgery tests use an eligible task, so stale-state rejection cannot hide a disconnected exact-text check.

## Verification and reproduction

```bash
python -B -m unittest discover -s tests -v
python -B -m continuity --out artifacts
```

The revision has 61 contract, integration and presentation tests. Current local evidence uses `qa/review-*` and `qa/recheck-verification.json`; historical Wave 1 and Wave 2 transcripts are retained separately. Browser QA at 1440px and 390px verifies all 108 selectable outcome/expectation pairs, all 57 recorded budget points, keyboard controls, source expansion, legible timeline labels, phone transition cards and scope, no page errors, no external requests and no page overflow. The repository CI runs the suite on Linux/Windows and Python 3.11/3.13.

The Unicode regression changes actual selection: a 1,577-byte context has 1,396 characters; at a budget of 1,396, byte packing retains three records using 1,280 bytes rather than accepting all four. Worker request-key tests examine the actual `run()` call site, and a mocked same-process reply explicitly checks the PID guard. Child stderr is included in failures. The worker loads its own package explicitly without adding its root before standard-library paths.

`run()` prepares a complete generation in a temporary sibling directory, then renames it into place. On build failure the previous complete generation remains unchanged; it is not a fresh success and the CLI exits with the failure. Successful publication replaces the owned artifact set, pruning orphan snapshots. Unrelated files prevent replacement. This is a single-writer protocol with a brief directory-rename window, not a lock-free or concurrent serving guarantee.

## Graphical evidence views

The explorer reconstructs each target-task source timeline from that case's recorded full-history context, then marks retained event IDs from the selected memory view. It does not reconstruct omitted text from expected labels. The three decision boxes display the recorded proposal, the authoritative gate's current state, and the recorded gate outcome. This makes the gate's full-ledger privilege visible rather than attributing it to the memory strategy.

Outcome marks count eligible tasks and use the actual denominator. The explorer includes expected state and explicit correct-resume, correct-hold, missed-eligible or unsafe-caught verdicts. Missed eligible tasks have warning styling, rather than looking like successful holds. Full history is labeled unbudgeted. Longer-terminal rows and the planted input remain visibly separate from the original matrix. On phones, the timeline scrolls locally to retain 14px detail text; gray outcome marks have dark outlines. JSON escapes HTML delimiters and source strings enter through `textContent`. Tests verify source binding, denominators, verdicts, missing histories and script-termination payloads.

The repository has zero runtime dependencies; there is no dependency lock file because no third-party package resolution occurs. The optional `tests/inspect_report.py` browser QA script uses an already-installed Playwright environment and is not required to reproduce the numerical results.

## Limits that affect interpretation

The controller role is not cryptographic authentication. Hashes do not prevent a privileged adversary replacing both data and the expected manifest. Exclusive content-addressed writes avoid overwriting existing snapshots through the API; they do not provide an append-only filesystem or concurrent transactional event database. Partial writes fail verification rather than recovering automatically. There is no production ingestion service, patient record integration, authorization service, neural model or clinical validation.

All 24 fixtures were authored during implementation. Several share templates. No confidence interval, significance test or claim of generalization is justified by these deliberately constructed cases. The primary engineering contribution is the inspectable source-to-proposal-to-gate path and failure controls.

## Next model experiment

Freeze an independently authored held-out set with unseen wording and additional task-identity collisions. Compare a genuine recursive-summary policy, raw semantic retrieval and source-linked timeline retrieval under the same tokenizer and model budget. Retain every intermediate summary and raw proposal. Pin model revision, prompts and inference settings; use three repeats while treating history, not repeated samples, as the independent unit.

Report inappropriate resumption by category, appropriate-resumption precision/recall/F1, evidence availability, exact citation validity, malformed outputs, paired gains/regressions, actual token use and latency. Keep deterministic checks separate from LLM behavior. A null or adverse result remains publishable evidence.

## Maintenance practice

Architectural comments specify purpose, contract, invariant, rationale, failure behavior and test evidence. Policy constants and guard branches have local rationale and named evidence. Eight curated `Mutation:` claims have exact source mutations and fully qualified named tests in `tests/comment_mutations.json`; the portfolio harness requires their cited tests to fail under each mutation. This checks those claims, not all prose. The convention is inspired by [Johnson's 2026 comment study](https://doi.org/10.3389/frai.2026.1784973), not asserted as a universal benefit of verbosity. Changes to state semantics must update code, fixtures, controls, tests and this report together.

The state vocabulary is deliberately small. Add a new transition only when its previous states, source authority and supersession behavior are defined. Changing the memory renderer must never move final authority into the proposal reader.
