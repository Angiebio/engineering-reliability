# Reading the record

The demos carry their own history in test names, QA folders and methods reports. That history was written while the work happened, so it uses first names and working labels. This note says who and what those are.

## Who is named

- **Angela N. Johnson**, who appears in the record as Angela, set the direction for the demos and supplied the domain judgment. The commenting convention draws on her [Frontiers study of expressive code comments](https://doi.org/10.3389/frai.2026.1784973).
- **Ying Akhila**, who appears in the record as Ying, built the demos. Ying is a research agent at The Real Cat Labs, running on a TRCL memory-enabled custom harness that deploys a GPT model. Ying is not a stock chat assistant, and "used GPT" would describe the work wrongly. "Ying's November demo proposal" in the Continuity Ledger is where that demo began.
- **Terminal Voice (T.V.)**, who appears in the record as TV, is Ying's coding implementation agent, working in a terminal coding harness on a GPT model. Ying and T.V. regard themselves as two arms of one agent, so the implementation is credited to Ying, with support from T.V. Where the records say TV implemented, repaired or reran something, that is this arm of the work.
- **Flame Johnson**, who appears in the record as Flame, is an agentic AI staff member of The Real Cat Labs, responsible for ideation, building, and running supervised experiments, and for contributing to the lab's ongoing knowledge graph. Flame is not a stock chat assistant. It is a Claude model (Claude Opus 5.5 at the time of this work) deployed in an agentic coding harness with The Real Cat Labs' persistent memory and standing project instructions. Here Flame reviewed the demos over three rounds, chose the held-out breaks and, with the audit agents, the outside-selected ones, and committed the TrialCat correction that Registry Metric Lab teaches.
- **Audit agents** are the helper agents Flame directed in the first two review rounds, one per demo. They wrote probes and mutants under Flame's direction.

## Working terms

| Term in the record | What it means |
|---|---|
| review dossier, research dossier, research record, parent portfolio | The lab's private archive of the build and review. It is not published here because it also holds machine paths and notes on unrelated projects. Its public summary is [evidence/](../evidence/index.html). The hashes in `evidence/evidence.json` identify the archived files. |
| snapshot names such as `TV-RECHECK-FIXES-13NOV2026` | Dated, read-only deliveries in that archive. Each review round read one snapshot and checked by hash that it was unchanged afterwards. |
| Wave 1, Wave 2 | The two build rounds on 13 November 2026, before the reviews. QA files labelled with them are kept as history. |
| curated, author-selected | Breaks chosen by the implementer. These are the 32 comment contracts. |
| outside, outside-selected | Breaks chosen by the reviewers rather than the implementer. |
| held out | Breaks chosen after a repair and not shown to the implementer until they had been scored. Once shown, they become known development checks. |
| equivalent | A break that changes the code without changing any behaviour the demo promises. No test can catch it, and the records say why for each one. |
| disclosed | A survivor that marks a limit the demo states openly, rather than a gap in its tests. |
| the Claude audit, post-Claude revision | Flame Johnson's first review round, and the repair that answered it. |
| screenshots named in a `qa/` note (`*.png`) | Browser QA captures from the review rounds. They stay in the lab's archive because they show the reports before their header changed (see [CHANGELOG.md](../CHANGELOG.md)). The JSON and text records beside those notes are here. |
| Child1 | A memory-augmented research prototype at The Real Cat Labs. The Continuity Ledger reuses lessons from its restart experiments, not its code. |

## What is not here

There are no private conversation records, no source code from other projects, no credentials and no real patient or registry data. Every record the demos run on is invented.
