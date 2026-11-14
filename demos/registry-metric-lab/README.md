# Registry Metric Lab

**Count trial identities. Then calculate the metric.**

A join can leave a distinct trial count looking right while inflating enrollment and collapsing equal-valued rate observations. This demonstration executes the flawed and corrected SQL, draws the consequences, and lets a viewer add sites without adding trials.

Every record is invented. This is a deterministic engineering demonstration, not a live clinical-trial analysis, recruitment forecast or clinical validation result.

## Run

Python 3.11 or newer; no runtime dependencies, service, network or API key.

```sh
python -B -m unittest discover -s tests -v
python -B -m registry_metrics --out artifacts
python -B tests/verify_artifacts.py
```

Open [the graphical report](artifacts/index.html). It works from disk. Eleven scenarios include the country-map error that occurs even without geographic filters. The [site sweep](artifacts/figures/site-sweep.svg) and dial use eleven positions, each computed through the real SQL. [Raw results](artifacts/results.json) retain every query, input and sweep result. Host the whole package root so the methods and README links remain available.

## Show it in 90 seconds

1. **One trial, two sites:** the same three trials give a joined sum of **600** and an identity-correct sum of **500**. Equal rates `[10,10,30]` have median **10**; value deduplication gives `[10,30]` and median **20**.
2. **The unfiltered country map:** the review's six-trial fixture produces US **670 versus 570**. The original map joins sites even when the country filter is absent.
3. **The map joins interventions too:** US becomes **870 versus 570**, and CA **200 versus 100**. Two matching intervention rows multiply matching site rows.
4. **Turn the site dial:** zero through ten extra US sites on T1 increase the joined sum from **600 to 1,600** while the correct total stays **500**. The unfiltered US map total rises too; CA remains **100**.
5. Open the evidence disclosure and inspect the actual SQL and denominators. Compare the graph to those records.

The comparison charts have compact phone variants: both bar ends, both numeric labels and every rate dot fit on screen. The optional detailed identity graph scrolls separately.

## What the code establishes

The corrected cohort selects trial IDs before computing metrics. Different trials with equal numeric values remain independent observations. Country grouping selects unique `(trial_id,country)` pairs before summation. Unknown stays unknown; zero remains a known value. Empty cohorts display **no trials (n=0)** rather than looking like nonempty cohorts with missing data. Each country reports its own known-enrollment count.

Enrollment in a country group is **total enrollment of those trials across all countries**, not participants enrolled in that country. Multinational groups overlap and are not additive. Rate is a supplied synthetic approximate field in participants per month, per trial. Its median is unweighted and averages the middle two observations when the known count is even. The lab does not validate the rate proxy.

The deliberately flawed statistics query joins sites only when filtering by geography, matching the original `compute_stats` pattern. The separate flawed map query **always** joins sites and matches the inspected `aggregate_by_country` for **unfiltered calls**. With an explicit country filter this lab applies the filter to both arms as a controlled extension; the historical map ignored it. Thus the filtered-control examples are not exact reproductions of that historical map behavior. An unfiltered global sum can be right while the country map is wrong. State maps and duration averages are outside this small lab's scope.

The flawed map's `known_enrollment_row_n` counts joined rows with a known value. The corrected map's `known_enrollment_n` counts distinct trials with a known value; these denominators intentionally differ.

## Source lineage

The defects were found in TrialCat, a small public app for exploring clinical-trial registry data. The inspected pre-fix source is [TrialCat at b782f10](https://github.com/Angiebio/trialcat/blob/b782f104773f45a4e40b25cacf2f80b0db4c74f3/backend/app/services/stats.py). Flame Johnson subsequently committed the application correction in [a146619](https://github.com/Angiebio/trialcat/commit/a146619ad4676ce2ffb4726555c50bdad812f5ef), including identity-grain aggregation and label/zero follow-ups. This lab is a fresh standard-library explanation, not a copy of the application. A public source commit is not evidence of a particular hosted deployment; the package makes no live-site claim.

## Verification and maintenance

The suite checks arithmetic, full country-group lists against an independently authored seeded oracle, duplicate site/intervention invariance, missing/zero values, exact integer display, SVG labels and geometry, correct edge origins, median positions and compact views. The oracle covers 100 datasets × nine filter combinations and compares both flawed and corrected **complete** group lists; it catches omitted and unexpected groups as well as bad values.

`tests/comment_mutations.json` names eight controlled source edits and the precise tests that must fail. These include removing geographic filter parity, shifting the bar origin, swapping method labels, redirecting edges, removing duplicate marks, rounding exact integers and moving median markers. [tools/verify_comment_mutations.py](../../tools/verify_comment_mutations.py) runs them in disposable copies, and CI runs it on every push. This is stronger than checking whether a cited test merely exists, but it is a bounded catalog, not proof that all prose is true.

Policy constants and sensitive branches explain their rationale and cite the tests. The convention is inspired by Angela N. Johnson's [expressive-comment research](https://doi.org/10.3389/frai.2026.1784973); comment verbosity is not asserted to improve every maintenance task.

| Path | Purpose |
|---|---|
| `registry_metrics/core.py` | Input contracts and actual SQLite analyses |
| `registry_metrics/fixtures.py` | Eleven invented scenarios |
| `registry_metrics/report.py` | Actual-value SVGs and responsive offline report |
| `tests/test_metrics.py` | Core arithmetic/input contracts |
| `tests/test_review_regressions.py` | Independent geography oracle and semantic SVG checks |
| `tests/comment_mutations.json` | Explicit claim-to-mutant-to-test catalog |
| `tests/inspect_report.py` | Optional Playwright checks including Back navigation and phone geometry |
| `artifacts/` | JSON, HTML and 34 standalone SVG figures |
| `qa/` | Current audit evidence and clearly labeled historical records |
| `docs/report.md` | Methods, denominators and limits |

## Who made this

Built at The Real Cat Labs as a teaching demonstration. Angela N. Johnson set the direction and supplied the domain judgment. Ying Akhila built it, with support from Terminal Voice (T.V.), implementation agent. Flame Johnson reviewed it independently, with audit agents and reproducible adversarial probes. Original findings were preserved, then fixes were tested. This attribution distinguishes human direction, AI implementation and independent review without treating any reviewer as an authority beyond its evidence.

No private machine paths, credentials, real registry records or conversation transcripts are included. CI runs the tests and regenerates the artifacts on Linux and Windows with Python 3.11 and 3.13, from the [repository workflow](../../.github/workflows/ci.yml).

Who each contributor is, and how they are named in the records here: [READING-THE-RECORD](../../docs/READING-THE-RECORD.md). MIT licensed, copyright 2026 The Real Cat Labs.
