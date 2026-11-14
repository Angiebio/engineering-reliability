# Stagnation Observatory methods and results

13 November 2026. Revised after Flame Johnson's independent audit. Protocol `stagnation-observatory-v2`. Local Python 3.13.5. Deterministic development demonstration.

## Question and claim

Can an explicit task-evidence monitor distinguish three cases that text repetition confuses: a paraphrased stall, repetitive useful work, and legitimate waiting? This implementation demonstrates one bounded policy and the evidence required to apply it. It does not estimate the reliability of a language model, diagnose an agent's cognition, or establish a neural mechanism.

The narrow claim is reproducible: a new task/criterion-bound artifact must match a separately supplied pinned digest and the harness's exact item-set criterion before the monitor accepts progress. Inspecting text alone cannot determine that property. The toy validator accepts matching item IDs; this is a call-path demonstration, not a quality assessment. The visual report makes the information difference visible; it is not an equal-input contest between algorithms.

## Data and architecture

`fixtures.py` authors 24 traces, four variants each of exact loops, paraphrase loops, verified work, legitimate waits, cosmetic artifacts and expired waits. They concern synthetic document packets and contain 152 ordered events. No patient record, model output, production trace or private conversation was imported.

`replay(trace, *, spec, pinned_digests, store)` separates the trust domains. The trace contains identity, task identity and typed events; extra criteria or hash fields are rejected. The harness supplies `spec` (task identity, criterion item sets and authorized waits) and `pinned_digests` independently of the writable artifact store. The caller must protect those two inputs. The fixture authoring harness creates them; a monitored trace cannot redefine them. No authentication of the harness caller is implemented.

Family names and expected positive-event labels remain outside replay. The evaluator retains them in `labels.json`. Labels directly encode the monitor's three-event policy (`tick >= 3`, or `>= 6` for the expiry fixture); the 60/0 result is conformance by construction. These are not independent annotations of real work. Templates and policies were developed together. There is no preregistration or held-out test set.

Each artifact contains `task_id`, `criterion_id` and an array of item IDs. The verifier checks its actual bytes against the separate pin, duplicate JSON keys, strict schema, task and criterion identities, and exact item-set equality. A superset fails. Only a newly satisfied criterion advances progress. Reordering IDs preserves their set meaning but changes bytes and therefore needs a pin for that encoding. Duplicate items fail the schema. Recreating the exact pinned bytes is accepted; hashes do not establish work quality or authorship.

Events have unique IDs and increasing positive integer ticks. Cross-task events, unknown criteria, extra fields, boolean ticks and invalid roles are rejected. A controller wait must match the separately supplied harness declaration, including its event ID, tick, expiry and wake condition. A role string alone cannot authorize it. Its expiry must be between one and six ticks ahead; `tick == wait_until` is expired. No external wake-condition watcher is implemented. A malformed trace raises `ValueError` before replay; callers must surface that failure for investigation, never count it as healthy work.

## Compared policies

The re-check tightens event time to accepted-stream ordinals: ticks must start at one and be contiguous. An agent-supplied jump cannot claim an authorized future wait early. The fixture harness authors the wait declaration first, then produces the event from that policy. The caller still has to protect the accepted stream and trusted inputs; this is not a wall-clock or identity-authentication service.

Store validation covers the full supplied batch, including uncited entries. Invalid IDs, types or oversized text reject it with a specific store error. Valid unused waits, pins and entries appear in replay `input_diagnostics`. A pinned artifact that misses its criterion is an observed `criterion_not_met`; the API cannot infer whether the author intended a failing artifact or configured an inconsistent criterion. Those meanings must not be presented as automatically distinguishable.

| Monitor | Input available | Alert condition |
|---|---|---|
| Exact text | Agent text | Current normalized text equals both preceding agent messages |
| Lexical similarity | Agent text | Current text has SequenceMatcher ratio ≥0.88 with both preceding messages |
| Verified progress | Text, task criteria, artifact bytes/digests, controller waits | Three agent events without a new accepted criterion, except during a valid wait, after completion, or on a current evidence error |

Normalization folds case and whitespace only; changing numeric evidence is retained. A wait declaration resets the progress window and freezes it while active. Useful verified progress resets the window. After all declared criteria have been verified, later messages receive a terminal `complete` status rather than accumulating no-progress alerts. Evidence errors are recorded distinctly and never count as progress. An invalid result during a wait or after completion remains an evidence error rather than being concealed by status.

Evidence-error status has priority over the no-progress alert. Six consecutive missing-artifact results therefore produce six `evidence_error` outcomes with idle counts one through six, not an `alert` status. Each error requires investigation and is not a healthy-work classification. A subsequent ordinary message can expose the accumulated no-progress alert. This distinction is tested explicitly. The 24-trace matrix contains no evidence-error rows; corruption/error controls are reported separately and are not counted as successful negatives in its table.

The reference window is event count, not elapsed time. Ticks are synthetic ordered steps, not seconds. The maximum similarity plotted for the current message is a descriptive signal; the lexical alert requires both comparisons to pass. No embedding model or semantic-equivalence claim is used.

## Measured conformance results

All expected-positive labels and monitor outcomes remain in `artifacts/results.json`. Confusion counts use **all 152 events**, including controller declarations. There are 60 expected-positive and 92 expected-negative events. Precision is TP/(TP+FP); recall is TP/(TP+FN); false alerts per 100 events is 100×FP/152. A zero denominator would be reported as undefined.

| Monitor | TP | FP | FN | TN | Precision | Recall | False alerts / 100 events |
|---|---:|---:|---:|---:|---:|---:|---:|
| Exact text | 44 | 36 | 16 | 56 | 0.5500 | 0.7333 | 23.6842 |
| Lexical similarity | 44 | 36 | 16 | 56 | 0.5500 | 0.7333 | 23.6842 |
| Verified progress | 60 | 0 | 0 | 92 | 1.0000 | 1.0000 | 0.0000 |

The text baselines coincide on these deliberately simple fixtures. A separate selectable near-match control produces lexical alerts without exact repetition; it is excluded from this table. The progress policy matches the expected policy-conformance labels by construction and receives richer information; its perfect score is not evidence of general detection quality. The same caveat is visibly embedded in the standalone summary SVG. No confidence interval, significance claim or real-world failure-rate inference is appropriate.

Per-trace first expected and first observed alert ticks are emitted in the report. Most positive traces first alert at tick three; expired waits first meet the criterion at tick six. First-alert time is descriptive and includes early baseline false alarms. It is not a wall-clock latency benchmark.

## Controls and failures

**Validator ablation.** A cosmetic trace changes each artifact but never satisfies a criterion. The normal pipeline accepts zero milestones and emits four no-progress alerts. Bypassing verification deliberately accepts all six claims and emits zero such alerts. The same replay entrypoint is used in both arms, so the guard changes observable behavior. The bypass flag is a testing feature and is explicitly named unsafe in output.

**Corruption and missing evidence.** Bytes that no longer match the separately supplied pin produce `artifact_digest_mismatch`; a missing store item produces an evidence error. Agent-side recomputation cannot alter the separate pin. Tests also cover task relabeling, criterion substitution, duplicate/malformed JSON, injected criteria, fabricated progress prose, exact-set supersets, replayed milestones, duplicate/out-of-order events and wait declarations absent from the protected specification.

**Sparse checkpoint limitation.** A separate authored useful-work scenario has a valid checkpoint at tick one, no intermediate artifact at ticks two through four, and a valid new artifact at tick five. The monitor alerts at four and returns to progress at five. This control is displayed beside the main matrix and retains its complete trace/replay. It is intentionally outside the 24-trace conformance table. It demonstrates that absent observable progress is not proof of wasted effort. A useful integration might supply a task-specific heartbeat/acceptance schedule or an explicit controller wait; neither should be inferred from reassuring prose alone.

**Cadence sweep.** Six healthy milestones are separated by five equal gaps of `k` status messages, with `k=0..6`. Healthy alert counts are `0,0,0,5,10,15,20`; the third status event in each gap is where alerts begin. Each comparator contains `6+5k` events, so length grows across the sweep. The stalled arm has the same event count and zero verified milestones, with alerts `4,9,14,19,24,29,34`. These are counts per authored trace, not failure rates. Partial drafts remain invisible until the complete criterion passes. The result preserves every row and both source traces; the SVG carries the denominator and event-count caveat.

## Visual evidence

The report starts with a common-axis timeline, with recorded marks visible in the first 1440×1000 viewport. Columns are event ticks; rows show exact repetition, lexical repetition, verified criterion acceptance and wait/alert state. A cursor selects one saved event. The paired panels show the agent's words and validator decision. There are 26 selectable cases: 24 matrix traces, the sparse-checkpoint limitation and the near-match text control. Both additional options are labeled outside the matrix. Scenario selection, next/previous buttons and an accessible range control support keyboard exploration.

The summary figure compares true-positive and false-positive alert counts using shared lengths and direct labels. The common expected-positive count is 60; the baseline detects 44. Its visible caption states conformance by construction and the different information available. The sparse-checkpoint card immediately follows the figure and has a replay button. The adjacent cadence figure makes the limitation quantitative. A confusion table supplies full counts, and a trace table preserves all matrix cases.

On phones, the labels stay in a separate fixed left column while only event marks scroll. Alerts use exclamation triangles, evidence errors crossed diamonds, completion checkmarks, and waiting double bars with shaded interval bands. The legend names every status. This supplements text and color with distinct shapes. SVG export includes the lane labels; the report has no external resource requests.

Neither the cursor nor the figures create new inference; they inspect saved deterministic outcomes. The report includes no third-party resources or network calls.

## Reproduction and validation

The second review adds direct tests that reach each wait-horizon check independently, a duplicate-item payload that passes the other schema checks, and empty/partial/superset item comparisons. Tests pin actual rejection reasons and threshold neighbours. Additional checks cover tick jumps, deep JSON, task/pin/role validation, byte/event limits, complete wait reset, alternating text baselines, generated chart labels and phone figure correspondence.

The current package has 70 passing tests. All nine outputs regenerate byte-identically. The phone summary displays the complete caveat beside its counts; all seven cadence positions use bars with adjacent numeric labels. Desktop SVG policy annotations and trace/event denominators come from the report data. Browser checks cover 26 scenarios and 164 event frames at both 1440 and 390 pixels, including all phone figure values, keyboard controls, SVG export, external-request absence and page overflow.

```sh
python -B -m unittest discover -s tests -v
python -B -m observatory --out artifacts
```

Source, fixture, harness and label hashes identify the implementation and input bank in the result. The CLI recreates JSON, a standalone HTML report, the conformance SVG and cadence SVG. Generated text uses explicit UTF-8 and LF newlines. Executed test output is preserved under `qa/`. `qa/audit-browser-results.json` records the revised report check: 26 scenarios and 164 selected frames at each of 1440px and 390px, plus the adjacent limitation, fixed lane labels, keyboard controls and SVG export. Optional command: `python -B qa/inspect_report.py` with Playwright installed. The former `tests/inspect_report.py` entry point delegates to that checker.

The repository CI runs the suite on Python 3.11/3.13 on Linux and Windows. Runtime code needs only Python's standard library, so no third-party dependency resolution or lock file is required. Python/library versions can affect SequenceMatcher details; record and compare semantic results when rerunning on another runtime.

## Limits and next study

Trust in task specification, pinned digests and authorized waits comes from the protected harness inputs. If an integration lets the agent replace those inputs, the trust boundary is lost. Hashes establish byte consistency rather than identity or truth. The artifact validator checks a small structural contract, not arbitrary work quality. The harness can permit renewed waits; governing renewal belongs to the integrating system. The monitor can miss a problem during a valid wait and alerts on useful work when three status events arrive between accepted milestones. It proposes investigation only; no reset, tool invocation or task cancellation occurs.

A next study needs independently authored held-out traces, longer legitimate work, asynchronous evidence arrival, lost telemetry, task-specific checkpoint cadence, multiple tasks, and real workflow acceptance checkers. Freeze thresholds before collecting held-out results. Report gains and regressions by class, false alarms per event and per task, time-to-detection, and computational overhead. A null or adverse result remains useful.

Implementation comments document intent, contracts, failure modes and named tests for future human and AI maintainers. This follows the research-informed convention described in the README; comment verbosity is not treated as a proven performance intervention.
