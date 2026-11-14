# Registry Metric Lab methods and results

13 November 2026 · Protocol `registry-metric-lab-v2` · Deterministic development demonstration

## Question and scope

Can trial-level metrics preserve trial identity when membership is selected through site and intervention tables? Can the country map preserve the separate unit `(trial,country)`? These are database-contract questions, not estimates of clinical truth or model capability.

All records are invented. Eleven authored scenarios cover joins, value deduplication, missing values, empty cohorts, country overlap and the unfiltered map. Templates deliberately overlap; there is no held-out benchmark, population estimate or confidence interval.

## Computation

An isolated SQLite database stores trial IDs with enrollment and a supplied rate, site IDs with trial/country, and intervention IDs with trial/kind. IDs, references, finite nonnegative values and filters are validated before queries run. Each table is limited to 1,000 records and each trial value to one billion. These are development resource limits, not validated registry-scale capacity. All filtering joins are **inner joins**. Their row bound is `max(trials, sites × interventions)`, not a product plus unmatched trials.

The flawed `compute_stats` path conditionally joins sites/interventions, counts distinct trial IDs, sums joined enrollment rows, and selects DISTINCT numeric rates. The corrected path first selects matching trial IDs, then retrieves one observation per identity. Equal numeric values do not identify a trial.

The map is a separate calculation: its flawed query **always joins sites**, even when no country filter is set. It groups joined enrollment by country; optional intervention joins multiply those site rows again. This output is retained in `incorrect.geography`. The corrected map deduplicates `(trial_id,country)` pairs before aggregation. It retains the geographic filter in the group query, so a CA-filtered cohort does not leak its US groups into the result.

## Recorded examples

The initial three trials have enrollments `[100,100,300]`, supplied rates `[10,10,30]`, and US-site counts `[2,1,1]`.

| Quantity | Flawed | Corrected |
|---|---:|---:|
| Distinct trials | 3 | 3 |
| Contributing rows | 4 | 3 |
| Enrollment | 600 | 500 |
| Rate n | 2 | 3 |
| Median rate | 20 | 10 |

`SUM(DISTINCT enrollment)` gives 400, merging two independent 100-enrollment trials. It is not the repair.

The review fixture adds a Canadian site for T1, a site-free 50-enrollment trial, a 70-enrollment trial with a US site, and a 100-enrollment trial with a German site. T1 has two DRUG intervention records.

| Country-map call | Flawed US | Corrected US | Flawed CA | Corrected CA |
|---|---:|---:|---:|---:|
| Unfiltered | 670 | 570 | 100 | 100 |
| DRUG filter | 870 | 570 | 200 | 100 |

For the simpler multinational three-trial fixture, an unfiltered global sum is correctly 500 even on the flawed statistics path, while its flawed US map sum is 600. The report now displays both paths, preventing the global agreement from concealing the map defect.

Historical fidelity of the flawed map is limited to **unfiltered calls**. The historical `aggregate_by_country` ignored `country_code`; this lab deliberately applies explicit country filters to both arms as a controlled extension. Its `country-filter` and `empty-cohort` examples must therefore be read as controlled filters, not exact historical map reproductions. The same caveat appears beside every map on the page.

The flawed map names its known-value denominator `known_enrollment_row_n`: this counts multiplied joined rows. The corrected map retains `known_enrollment_n`, counting known-valued trial-country pairs. For the review's DRUG-filtered US group these are seven joined rows versus four trial identities.

## Denominators and numeric semantics

Trial count, known-enrollment count and known-rate count are separate. Missing values leave their relevant arithmetic, not cohort membership. Country groups include a known-enrollment `n`; for the missing-value fixture, US has three trials, two known enrollments and sum 400. A real zero is displayed as zero. No-trial cohorts display `no trials (n=0)`; nonempty unknown cohorts display `unknown` with their membership counts.

Country totals are whole-trial enrollments for trials having sites in that country, not participants enrolled in the country. A multinational trial contributes once to each applicable group. These totals overlap and cannot be added to a global participant count. A trial without known-country sites can contribute to a global cohort but appear in no country group.

The rate unit is participants per month, per trial; it is supplied synthetically rather than derived or validated here. Median is unweighted and averages the middle two values for even n. The flawed median 20 is the average of deduplicated values 10 and 30. Integers display exactly with grouping separators; floating-point values use Python's shortest round-trip decimal representation rather than a fixed significant-digit truncation. This preserves integer differences such as 12,345,640 versus 12,345,600.

## Measured site sweep

For each of eleven positions, zero through ten extra US sites are added to T1. No trial/value changes. The generator executes both the filtered statistics query and unfiltered country query at each position and stores every source table, SQL result and group.

Joined enrollment is `600 + 100 × extra_sites`, from 600 to 1,600. Correct enrollment stays 500. The flawed US country total follows the same slope while CA stays 100; corrected US/CA remain 500/100. Those equations summarize the recorded SQL outcomes; the renderer reads the saved values instead of drawing from the equations. This is a controlled multiplicity demonstration, not an empirical performance curve.

## Graphical claims and verification

Desktop bars start at x=210 and share a zero origin and scale. Compact phone bars use x=20 within a 340-unit viewport; both ends, both labels and all five initial rate observations are visible. Browser tests verify actual on-screen boxes and a 1.2 width ratio at 390px. The selected panel is reconciled on initial load and `pageshow`, including Back navigation after following `results.json`.

The graph's edge origin is checked against the corresponding trial-node position. The duplicate marker, method labels, common zero origin, bar ratio, median marker positions and dot lane bounds have semantic SVG tests. Dense equal-rate cases test lane boundaries, not only the outer viewBox. Downloaded figures carry scenario, filters, cohort and query-row counts, and invented/trial-wide labels. Identity-node site labels include country when sites are joined. These connectors are described as connections, not arrows with nonexistent arrowheads.

The second review added full country-map group/method/value/scale checks in both layouts, parsed country-table cells, all sweep coordinates and zero-axis ticks, dynamic legend tests with changed measurements, both directions of graph edges, and duplicate edge/row colors. Non-round integer examples and corrected medians different from the first observation challenge subtler rendering changes. Generated Failure/Control tags are checked explicitly, including the multinational map-only failure.

The hero shows actual first-scenario totals; each scenario is tagged failure/control from its recorded outcomes. The live status announcement is visually hidden. The optional identity graph scrolls on phones, while quantitative comparisons have compact variants.

## Independent oracle and comment mutations

A seeded standard-library oracle authors 100 small datasets and tests nine combinations of country/intervention filters. It constructs expected groups directly from input-list membership, without SQL or production helpers, and compares the **complete** ordered group lists for both corrected and flawed geography. It catches empty-output, missing-country and extra-country mutations that a check of emitted rows alone would miss. Original 270-check peer evidence remains historical and is not promoted to this stronger claim.

Eight mutation catalog entries pair a concrete claim and source edit with named tests. The catalog covers identity membership, full country-filter parity, exact display, bar labels/origin, edge provenance, duplicate marks and measured median markers. The parent research workflow runs each in a disposable copy after checking the named test passes on original source. This checks the selected executable claims; it does not mechanically establish the truth of every comment.

## Source lineage and remaining scope

The pre-fix source is [TrialCat b782f10](https://github.com/Angiebio/trialcat/blob/b782f104773f45a4e40b25cacf2f80b0db4c74f3/backend/app/services/stats.py). Flame Johnson's public correction is [a146619](https://github.com/Angiebio/trialcat/commit/a146619ad4676ce2ffb4726555c50bdad812f5ef). The local explanatory kernel is independent of TrialCat's framework/database; it demonstrates the inspected query failure patterns. State grouping and duration-average errors are not reproduced in this lab. A source correction does not establish hosted deployment or validate real registry data.

## Reproduction

```sh
python -B -m unittest discover -s tests -v
python -B -m registry_metrics --out artifacts
python -B tests/verify_artifacts.py
```

Generation creates eleven scenario records, one HTML report and 34 SVGs, including the site sweep. JSON records Python/SQLite versions and implementation/fixture hashes. Text files use explicit UTF-8 and LF. Identical source/runtime/fixtures regenerate identical bytes; different runtime metadata is expected to change the record. Optional browser verification is `python -B tests/inspect_report.py` with Playwright/Chromium installed.

Current audit evidence uses `qa/audit-*`; historical Wave 2 records remain explicitly labeled under `qa/README.md`. The repository CI runs the suite on Windows/Linux and Python 3.11/3.13. No public hosting of this package, clinical validation or live-site measurement is claimed.
