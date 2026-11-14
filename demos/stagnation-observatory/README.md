# Stagnation Observatory

**New words can accompany the same unfinished work. Repeated words can accompany real progress.**

This small agent-reliability demonstration compares text repetition with a harness-supplied task specification, separately pinned artifact digests, agent-supplied bytes, and bounded waiting. Its interactive report places those signals on one timeline, then shows when useful work exceeds the monitor's three-event window.

All traces concern invented administrative document packets. The monitor is deterministic, uses no model or API, and proposes investigation rather than taking remediation actions. It does not infer mental states or identify neural mechanisms.

## Run

Python 3.11 or newer. No installation or third-party runtime dependency.

```sh
python -B -m unittest discover -s tests -v
python -B -m observatory --out artifacts
```

Open [artifacts/index.html](artifacts/index.html). The report works directly from disk and contains its data. [artifacts/results.json](artifacts/results.json) preserves decisions, labels, controls, the cadence sweep and code hashes. [artifacts/summary.svg](artifacts/summary.svg) carries its conformance-by-construction caveat; [artifacts/cadence.svg](artifacts/cadence.svg) shows the alert boundary. The report also exports the selected timeline as SVG. For hosting, retain the whole package directory so the relative README and methods links resolve; hosting only `artifacts/` removes those links.

## Show it in 90 seconds

1. Start with **Paraphrase loop**. Scrub to event three: new wording, no text-repetition alert, and no new verified progress.
2. Select **Verified work**. The same text repeats, but each artifact satisfies a new criterion. The text-only baselines alert while the evidence monitor records progress.
3. Select **Expired wait**. Step from tick three to four. A controller wait expires at four; the no-progress window starts again and reaches an alert at six.
4. Inspect the validator ablation. Cosmetic artifacts stop looking like progress when their contents are actually checked.
5. Select **Useful work can lack a checkpoint · outside the matrix**. At tick four, useful work alerts; at tick five, its next artifact is accepted. The same control has a replay button immediately under the conformance figure.
6. Inspect the cadence curve: six completed milestones with three status messages between them produce five alerts. Select **Near-match text · outside the matrix** to see lexical repetition without exact repetition.

## What counts as progress

The harness calls `replay(trace, spec=..., pinned_digests=..., store=...)`. The trace contains only its identity, task identity and events. The protected `spec` supplies criterion item sets and permitted wait declarations; `pinned_digests` supplies expected digests separately. The agent can change artifact bytes in `store`, but an embedded criterion or digest cannot replace a harness input. The checker verifies the separately pinned byte digest, strict JSON, task and criterion identities, and exact item-set equality. A new criterion can be accepted once. Repeating a completed criterion, renaming bytes or claiming “done” in prose does not create a new accepted criterion.

These checks demonstrate a call path, not general artifact quality. The item-ID validator accepts any artifact satisfying its small structural contract and pinned-byte check; recreating the expected pinned bytes is accepted. A digest establishes consistency, not authorship or truthful work. The integration must protect the harness inputs from the monitored agent and use a checker appropriate to real work. A controller role label alone is insufficient: the wait must match a separate harness declaration. This package does not authenticate the harness caller.

The accepted event order supplies the clock: ticks must be contiguous ordinals beginning at one. Integrations assign that ordinal from their accepted event stream; an agent cannot jump to a future controller declaration by claiming a later tick. Fixture wait policy is authored before its trace event and is never copied back from agent fields.

Validation treats the supplied store as one bounded batch: an invalid unused entry also rejects the batch, with a store-specific error. Valid unused pins, waits and store entries are listed under `input_diagnostics` in every replay result. A well-formed pinned artifact whose items disagree with the criterion remains `criterion_not_met`; this interface cannot distinguish a mistaken trusted specification from deliberately failing evidence. The fixture matrix intentionally includes the latter. Protecting and reviewing those harness inputs remains an integration responsibility.

## Monitor policy

Three agent events without a new accepted criterion produce a no-progress alert, except during a valid controller wait, after all criteria are complete, or when the current result has an evidence error. An evidence error takes status priority and independently requires investigation; it does not label work healthy. Its events still accumulate in the no-progress count outside waits. Waits require a future expiry no more than six ticks away and a documented wake condition. At the expiry tick, the wait is expired. The wake condition is descriptive; this package does not implement an external condition watcher or early wake event.

An explicit wait resets the no-progress window. New valid evidence also resets it. Once all declared criteria have been verified, later messages receive `complete` rather than accumulating a stall window. Evidence errors remain visible even during a wait or after completion. A missing or altered artifact is an evidence error, not a successful check or an automatic declaration of stagnation. The controller can declare another bounded wait; production policy must govern who can do that.

The exact baseline normalizes case and whitespace and requires three identical recent agent messages. The lexical baseline requires the current message to match both preceding messages at a `SequenceMatcher` ratio of at least 0.88. Neither baseline sees artifacts or waits. These are interpretable text baselines, not semantic detectors.

Useful work with **three or more agent status events between accepted milestones can alert** even when it later completes. Partial artifacts remain invisible to progress until the whole criterion is satisfied. The cadence sweep records this limitation; it is not a bug that the policy's threshold can cross healthy work. Malformed traces fail closed with `ValueError`; the caller must treat that as requiring investigation, never as a healthy classification.

## Recorded results

The 24 authored development traces contain 152 events across six families. Both text baselines produce 44 true alerts, 36 false alerts and 16 missed expected alerts. The evidence monitor agrees with all 60 expected positive events in this policy-conformance matrix. **That agreement is conformance by construction, not generalization**: the fixtures and policy were developed together, expected labels encode the policy, and the evidence monitor receives additional task structure. The current executed suite and browser evidence are saved under `qa/`.

The separate sparse-checkpoint control shows an alert at tick four followed by legitimate progress at tick five. It sits directly below the conformance figure and is selectable alongside the main traces. A seven-point cadence sweep uses six milestones and five gaps: healthy alerts are **0, 0, 0, 5, 10, 15, 20** for gaps of zero through six status messages. At gap `k`, both healthy and stalled comparators contain `6 + 5k` events; the plotted counts are not failure rates. These controls are outside the 152-event matrix. [Methods and limitations](docs/report.md) give exact scope.

On phones, the summary uses labeled result cards and the cadence plot uses a measured bar pair for every gap. No right-hand result or caveat requires horizontal scrolling. Desktop SVG exports retain the complete figures. Policy labels and denominators are generated from the same measured records used by the marks.

## Repository map

| Path | Responsibility |
|---|---|
| `observatory/core.py` | Trace/schema validation, artifact verification and replay |
| `observatory/fixtures.py` | Authored development traces and separate expected labels |
| `observatory/__main__.py` | Actual evaluation, controls, provenance and artifact generation |
| `observatory/report.py` | Interactive SVG timeline and evidence report |
| `tests/test_core.py` | Contracts, corruption, policy and CLI checks |
| `tests/test_report.py` | Figure caveats, measured cadence and presentation contracts |
| `tests/test_recheck.py` | Outside-review regressions for masked guards, both comparison directions and input limits |
| `qa/inspect_report.py` | Optional browser QA using separately installed Playwright; the former test-path command delegates here |
| `../../.github/workflows/ci.yml` | Repository CI: Linux/Windows and Python 3.11/3.13 checks |
| `docs/report.md` | Scientific/engineering interpretation and observed results |

## Research and maintenance lineage

The problem comes from earlier persistent-agent loop research: surface novelty can conceal repeated stated next steps without completed work. This is fresh implementation using newly authored fixtures; no production agent database or private conversation corpus is included.

Boundary comments explain purpose, contract, invariant, rationale, failure behavior and test evidence. The convention is inspired by Angela N. Johnson's [Frontiers study of expressive code comments](https://doi.org/10.3389/frai.2026.1784973). Its usefulness remains something to evaluate, not a universal benefit asserted from comment length.

Policy constants and guard branches also carry local rationale and named evidence. Seven selected claims have adjacent `Mutation:` IDs and an executable mutation specification in [tests/comment_mutations.json](tests/comment_mutations.json). The repository's [mutation verifier](../../tools/verify_comment_mutations.py) requires the cited test to fail after its corresponding guard is changed. This checks those explicit contracts, not the truth of every comment.

## Who made this

Built at The Real Cat Labs as a teaching demonstration. Angela N. Johnson set the direction and supplied the domain judgment. Ying Akhila built it, with support from Terminal Voice (T.V.), implementation agent. Flame Johnson reviewed it independently, with audit agents and reproducible adversarial probes. The audit exposed the original input-boundary and interpretation defects; the revision separates the trusted inputs and makes cadence limitations visible. Original observations remain preserved in the research record.

CI runs the tests and regenerates the artifacts on Linux and Windows with Python 3.11 and 3.13, from the [repository workflow](../../.github/workflows/ci.yml).

Who each contributor is, and how they are named in the records here: [READING-THE-RECORD](../../docs/READING-THE-RECORD.md). MIT licensed, copyright 2026 The Real Cat Labs.
