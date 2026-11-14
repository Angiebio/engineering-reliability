"""Purpose: preserve trial identity while calculating registry metrics.

Contract: validated synthetic records only; an isolated in-memory SQLite database.
Enrollment is trial-wide. Rate is a supplied synthetic approximate-rate field,
not a measured recruitment speed. Missing values remain missing.
Invariant: adding a matching site or intervention cannot add another trial-level
observation; independently equal values must remain independent observations.
Rationale: joins select membership, while trial identity determines metric grain.
Failure: malformed records, unknown references and invalid filters raise.
Evidence: tests/test_metrics.py exercises cardinality and equal-value controls.
"""
from __future__ import annotations

import math
import re
import sqlite3
import statistics
from typing import Any

# Fixture identifiers are labels, not SQL: bind filter values instead of building
# expressions from them. Evidence: test_invalid_identity_and_reference.
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
# Development-only resource ceiling, not a registry-scale performance claim.
# At most 1M inner-join rows keep worst-case totals below SQLite's int64 limit.
# Evidence: test_record_and_value_bounds.
MAX_RECORDS = 1000
# Per-trial bound chosen for inspectable synthetic inputs, not clinical validity.
# Evidence: test_record_and_value_bounds, test_invalid_numeric_values.
MAX_VALUE = 1_000_000_000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(data: dict) -> None:
    require(type(data) is dict and set(data) == {"trials", "sites", "interventions"}, "Invalid fixture fields")
    for table in data:
        require(type(data[table]) is list and len(data[table]) <= MAX_RECORDS, "Expected bounded record lists")
    ids: dict[str, set[str]] = {}
    for table, fields in (("trials", {"id", "enrollment", "rate"}),
                          ("sites", {"id", "trial_id", "country"}),
                          ("interventions", {"id", "trial_id", "kind"})):
        ids[table] = set()
        for row in data[table]:
            require(type(row) is dict and set(row) == fields, f"Invalid {table} record")
            key = row["id"]
            require(type(key) is str and IDENTIFIER.fullmatch(key) is not None, "Invalid identity")
            require(key not in ids[table], f"Duplicate {table} identity")
            ids[table].add(key)
            if table == "trials":
                # bool is numerically int in Python but never an enrollment;
                # missing stays None, while zero is a measured value.
                # Evidence: test_invalid_numeric_values, test_zero_values_are_known.
                n, rate = row["enrollment"], row["rate"]
                require(n is None or (type(n) is int and 0 <= n <= MAX_VALUE), "Invalid enrollment")
                require(rate is None or (type(rate) in (int, float) and 0 <= rate <= MAX_VALUE
                                        and math.isfinite(rate)), "Invalid rate")
            else:
                require(type(row["trial_id"]) is str and row["trial_id"] in ids["trials"], "Unknown trial reference")
                field = "country" if table == "sites" else "kind"
                value = row[field]
                if field == "country":
                    # Unknown country is not a fabricated group label. Exact
                    # case and whitespace matter for the explicit filter contract.
                    # Evidence: test_unknown_geography_keeps_overall_membership.
                    require(value is None or (type(value) is str and re.fullmatch(r"[A-Z]{2}", value) is not None), "Invalid country")
                else:
                    require(value in ("DRUG", "DEVICE", "BEHAVIORAL"), "Invalid intervention kind")


def connect(data: dict) -> sqlite3.Connection:
    validate(data)
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE trial(id TEXT PRIMARY KEY, enrollment INTEGER, rate REAL);
        CREATE TABLE site(id TEXT PRIMARY KEY, trial_id TEXT REFERENCES trial(id), country TEXT);
        CREATE TABLE intervention(id TEXT PRIMARY KEY, trial_id TEXT REFERENCES trial(id), kind TEXT);
    """)
    connection.executemany("INSERT INTO trial VALUES (:id,:enrollment,:rate)", data["trials"])
    connection.executemany("INSERT INTO site VALUES (:id,:trial_id,:country)", data["sites"])
    connection.executemany("INSERT INTO intervention VALUES (:id,:trial_id,:kind)", data["interventions"])
    return connection


def filters(country: str | None, kind: str | None) -> tuple[str, dict]:
    require(country is None or (type(country) is str and re.fullmatch(r"[A-Z]{2}", country) is not None), "Invalid country filter")
    require(kind is None or kind in ("DRUG", "DEVICE", "BEHAVIORAL"), "Invalid intervention filter")
    joins, predicates, values = [], [], {}
    if country is not None:
        # A matching site selects a trial; a duplicate site must not add a trial.
        # Evidence: test_duplicate_site_invariance.
        joins.append("JOIN site s ON s.trial_id=t.id")
        predicates.append("s.country=:country")
        values["country"] = country
    if kind is not None:
        # Multiple matching interventions select membership without weighting
        # corrected metrics. Evidence: test_duplicate_intervention_invariance.
        joins.append("JOIN intervention i ON i.trial_id=t.id")
        predicates.append("i.kind=:kind")
        values["kind"] = kind
    where = " WHERE " + " AND ".join(predicates) if predicates else ""
    return " FROM trial t " + " ".join(joins) + where, values


def summarize(rows: list[dict], *, distinct_values: bool = False) -> dict:
    # Missing values leave their own denominator, not trial membership. The
    # deliberately flawed arm deduplicates rate values only; the corrected arm
    # preserves equal-valued independent trials. Evidence: test_missing_values_reported,
    # test_equal_values_are_independent, test_all_missing_is_not_zero.
    enrollments = [row["enrollment"] for row in rows if row["enrollment"] is not None]
    rates = [row["rate"] for row in rows if row["rate"] is not None]
    if distinct_values:
        rates = sorted(set(rates))
    return {"trial_count": len({row["id"] for row in rows}),
            "observation_rows": len(rows), "enrollment_sum": sum(enrollments) if enrollments else None,
            "rate_n": len(rates), "rate_values": rates,
            "rate_median": statistics.median(rates) if rates else None,
            "known_enrollment_n": len(enrollments),
            "missing_enrollment_n": len(rows) - len(enrollments),
            "missing_rate_n": sum(row["rate"] is None for row in rows)}


def analyze(data: dict, country: str | None = "US", kind: str | None = None) -> dict:
    """Execute flawed and corrected queries on the same selected cohort.

    Purpose: make two independently verifiable failure mechanisms visible.
    Contract: flawed SQL sums joined observations and SELECT DISTINCT rate;
    corrected SQL selects distinct trial IDs before measuring any value.
    Invariant: equal rate/enrollment values never identify a trial.
    Rationale: SUM(DISTINCT enrollment) masks some inflation but loses equal trials.
    Failure: invalid fixture or filters raises before report generation.
    Evidence: test_original_failure, test_duplicate_site_invariance,
    test_duplicate_intervention_invariance, test_equal_values_are_independent.
    """
    clause, params = filters(country, kind)
    connection = connect(data)
    try:
        site_col = "s.id" if country is not None else "NULL"
        intervention_col = "i.id" if kind is not None else "NULL"
        joined_sql = f"SELECT t.id,t.enrollment,t.rate,{site_col} AS site_id,{intervention_col} AS intervention_id" + clause + " ORDER BY t.id,site_id,intervention_id"
        joined = [dict(row) for row in connection.execute(joined_sql, params)]
        # Membership is an identity set, so joined multiplicity never weights it.
        # Mutation: RM-IDENTITY. Evidence: test_duplicate_site_invariance.
        cohort_sql = "SELECT t.id,t.enrollment,t.rate FROM trial t WHERE t.id IN (SELECT DISTINCT t.id" + clause + ") ORDER BY t.id"
        cohort = [dict(row) for row in connection.execute(cohort_sql, params)]
        flawed_sql = "SELECT COUNT(DISTINCT t.id) AS trial_count, SUM(t.enrollment) AS enrollment_sum, SUM(DISTINCT t.enrollment) AS misleading_distinct_sum" + clause
        flawed_summary = dict(connection.execute(flawed_sql, params).fetchone())
        flawed_rates_sql = "SELECT DISTINCT t.rate" + clause + (" AND" if params else " WHERE") + " t.rate IS NOT NULL ORDER BY t.rate"
        flawed_rates = [row[0] for row in connection.execute(flawed_rates_sql, params)]
        corrected_sql = "WITH cohort AS (" + cohort_sql + ") SELECT COUNT(*) AS trial_count,SUM(enrollment) AS enrollment_sum FROM cohort"
        corrected_summary = dict(connection.execute(corrected_sql, params).fetchone())
        corrected = summarize(cohort)
        require(corrected["enrollment_sum"] == corrected_summary["enrollment_sum"] and corrected["trial_count"] == corrected_summary["trial_count"], "SQL/Python arithmetic disagreement")
        wrong = summarize(joined, distinct_values=True)
        wrong.update(flawed_summary, rate_n=len(flawed_rates), rate_values=flawed_rates,
                     rate_median=statistics.median(flawed_rates) if flawed_rates else None)
        # Group membership is a unique (trial, geography) pair. Group sums remain
        # trial-wide enrollment and cannot be added into a global person count.
        # Evidence: test_multinational_groups_nonadditive and test_country_filter.
        # Country filtering limits the emitted groups as well as cohort selection.
        # Mutation: RM-GEO-FILTER. Evidence: test_country_filter.
        geographic_filter = " AND s.country=:country" if country is not None else ""
        geography_sql = ("WITH cohort AS (" + cohort_sql + "), pairs AS ("
                         "SELECT DISTINCT c.id,s.country,c.enrollment FROM cohort c JOIN site s ON s.trial_id=c.id "
                         "WHERE s.country IS NOT NULL" + geographic_filter + ") "
                         "SELECT country,COUNT(*) AS trial_count,COUNT(enrollment) AS known_enrollment_n,SUM(enrollment) AS trial_enrollment_sum FROM pairs GROUP BY country ORDER BY country")
        geography = [dict(row) for row in connection.execute(geography_sql, params)]
        # TrialCat's map joins sites even when the caller supplies no country.
        # This deliberately wrong comparison preserves that source failure; the
        # identity-correct pairs above are the repair. Intervention joins multiply
        # site rows too. Historical fidelity is limited to unfiltered calls:
        # this lab deliberately applies explicit country filters to both arms,
        # whereas the old map ignored them. Evidence: test_always_joined_geography,
        # test_review_map_fixture, test_filtered_map_scope_is_disclosed.
        # The known-value denominator here counts joined rows, not trials.
        flawed_geo_sql = ("SELECT s.country,COUNT(DISTINCT t.id) AS trial_count,"
                          "COUNT(t.enrollment) AS known_enrollment_row_n,SUM(t.enrollment) AS trial_enrollment_sum "
                          "FROM trial t JOIN site s ON s.trial_id=t.id "
                          + ("JOIN intervention i ON i.trial_id=t.id " if kind is not None else "")
                          + "WHERE s.country IS NOT NULL" + geographic_filter
                          + (" AND i.kind=:kind" if kind is not None else "")
                          + " GROUP BY s.country ORDER BY s.country")
        wrong['geography'] = [dict(row) for row in connection.execute(flawed_geo_sql, params)]
        selected = {row["id"] for row in cohort}
        excluded = [row["id"] for row in data["trials"] if row["id"] not in selected]
        return {"filters": {"country": country, "intervention_kind": kind},
                "joined_rows": joined, "cohort": cohort, "incorrect": wrong, "corrected": corrected,
                "geography": geography, "excluded_trial_ids": excluded,
                "missing_enrollment_trial_ids": [row["id"] for row in cohort if row["enrollment"] is None],
                "missing_rate_trial_ids": [row["id"] for row in cohort if row["rate"] is None],
                "sql": {"joined_rows": joined_sql, "incorrect_aggregate": flawed_sql,
                        "incorrect_rates": flawed_rates_sql, "corrected_cohort": cohort_sql,
                        "corrected_aggregate": corrected_sql, "geographic_pairs": geography_sql,
                        "incorrect_geography": flawed_geo_sql},
                "parameters": params}
    finally:
        connection.close()
