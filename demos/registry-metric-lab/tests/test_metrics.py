"""Executable contracts on invented cohorts; no network or application DB."""
from copy import deepcopy
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from registry_metrics.core import analyze, validate
from registry_metrics.fixtures import base, scenarios
from registry_metrics.report import make_html, provenance_svg, comparisons_svg, number


def oracle(data, country, kind):
    # Deliberately independent membership implementation, with no SQL, joins,
    # DISTINCT, or production helper calls. Values are aggregated after identity.
    selected = []
    for trial in data["trials"]:
        if country is not None and not any(s["trial_id"] == trial["id"] and s["country"] == country for s in data["sites"]):
            continue
        if kind is not None and not any(i["trial_id"] == trial["id"] and i["kind"] == kind for i in data["interventions"]):
            continue
        selected.append(trial)
    counts = [t["enrollment"] for t in selected if t["enrollment"] is not None]
    rates = [t["rate"] for t in selected if t["rate"] is not None]
    return {"trial_count": len(selected), "enrollment_sum": sum(counts) if counts else None,
            "rate_n": len(rates), "rate_median": statistics.median(rates) if rates else None}


class AggregationTests(unittest.TestCase):
    def test_original_failure(self):
        result = analyze(base())
        self.assertEqual(result["incorrect"]["enrollment_sum"], 600)
        self.assertEqual(result["corrected"]["enrollment_sum"], 500)
        self.assertEqual(result["incorrect"]["rate_median"], 20)
        self.assertEqual(result["corrected"]["rate_median"], 10)
        self.assertEqual(result["incorrect"]["rate_n"], 2)
        self.assertEqual(result["corrected"]["rate_n"], 3)
        self.assertEqual(result["incorrect"]["trial_count"], 3)

    def test_all_scenarios_match_independent_oracle(self):
        for scenario in scenarios():
            with self.subTest(scenario=scenario["id"]):
                result = analyze(scenario["data"], scenario["country"], scenario["kind"])
                expected = oracle(scenario["data"], scenario["country"], scenario["kind"])
                for key, value in expected.items():
                    self.assertEqual(result["corrected"][key], value)

    def test_duplicate_site_invariance(self):
        original = analyze(base())
        for additional in (1, 2, 7):
            data = base()
            data["sites"].extend({"id": f"X{x}", "trial_id": "T1", "country": "US"} for x in range(additional))
            result = analyze(data)
            self.assertEqual(result["corrected"], original["corrected"])
            self.assertEqual(result["incorrect"]["enrollment_sum"], 600 + additional * 100)

    def test_duplicate_intervention_invariance(self):
        data = base()
        expected = analyze(data, kind="DRUG")["corrected"]
        data["interventions"].append({"id": "I4", "trial_id": "T1", "kind": "DRUG"})
        result = analyze(data, kind="DRUG")
        self.assertEqual(result["corrected"], expected)
        self.assertEqual(result["incorrect"]["enrollment_sum"], 500)
        self.assertEqual(result["corrected"]["enrollment_sum"], 200)

    def test_equal_values_are_independent(self):
        result = analyze(base())
        self.assertEqual(result["corrected"]["rate_values"], [10, 10, 30])
        self.assertEqual(result["incorrect"]["misleading_distinct_sum"], 400)
        self.assertNotEqual(result["incorrect"]["misleading_distinct_sum"], result["corrected"]["enrollment_sum"])

    def test_multinational_groups_nonadditive(self):
        scenario = next(s for s in scenarios() if s["id"] == "multinational")
        result = analyze(scenario["data"], country=None)
        self.assertEqual(result["geography"], [{"country": "CA", "trial_count": 1, "known_enrollment_n": 1, "trial_enrollment_sum": 100},
                                              {"country": "US", "trial_count": 3, "known_enrollment_n": 3, "trial_enrollment_sum": 500}])
        self.assertEqual(result["corrected"]["enrollment_sum"], 500)
        self.assertEqual(sum(g["trial_enrollment_sum"] for g in result["geography"]), 600)

    def test_country_filter(self):
        scenario = next(s for s in scenarios() if s["id"] == "country-filter")
        result = analyze(scenario["data"], country="CA")
        self.assertEqual([row["id"] for row in result["cohort"]], ["T1"])
        self.assertEqual(result["geography"], [{"country": "CA", "trial_count": 1, "known_enrollment_n": 1, "trial_enrollment_sum": 100}])
        self.assertEqual(result["excluded_trial_ids"], ["T2", "T3"])

    def test_unknown_geography_keeps_overall_membership(self):
        scenario = next(s for s in scenarios() if s["id"] == "unknown-geography")
        result = analyze(scenario["data"], country=None)
        self.assertEqual(result["corrected"]["trial_count"], 4)
        self.assertEqual(result["geography"][0]["trial_count"], 3)
        self.assertEqual(result["corrected"]["enrollment_sum"], 700)

    def test_missing_values_reported(self):
        scenario = next(s for s in scenarios() if s["id"] == "missing-values")
        result = analyze(scenario["data"])
        self.assertEqual(result["missing_enrollment_trial_ids"], ["T1"])
        self.assertEqual(result["missing_rate_trial_ids"], ["T2"])
        self.assertEqual(result["corrected"]["enrollment_sum"], 400)
        self.assertEqual(result["corrected"]["rate_n"], 2)

    def test_all_missing_is_not_zero(self):
        scenario = next(s for s in scenarios() if s["id"] == "all-missing")
        result = analyze(scenario["data"])["corrected"]
        self.assertEqual(result["trial_count"], 3)
        self.assertEqual(result["rate_n"], 0)
        self.assertIsNone(result["enrollment_sum"])
        self.assertIsNone(result["rate_median"])

    def test_empty_cohort(self):
        result = analyze(base(), country="GB")
        self.assertEqual(result["corrected"]["trial_count"], 0)
        self.assertIsNone(result["corrected"]["enrollment_sum"])
        self.assertEqual(result["geography"], [])

    def test_zero_values_are_known(self):
        data = base()
        for row in data["trials"]:
            row.update(enrollment=0, rate=0)
        result = analyze(data)["corrected"]
        self.assertEqual(result["enrollment_sum"], 0)
        self.assertEqual(result["rate_n"], 3)
        self.assertEqual(result["rate_median"], 0)

    def test_invalid_numeric_values(self):
        for field, bad in (("enrollment", True), ("enrollment", -1), ("rate", float("nan")),
                           ("rate", float("inf")), ("rate", True), ("rate", -1), ("rate", 10**1000)):
            with self.subTest(field=field, value=type(bad).__name__):
                data = base()
                data["trials"][0][field] = bad
                with self.assertRaises(ValueError):
                    analyze(data)

    def test_invalid_identity_and_reference(self):
        for mutation in (lambda d: d["trials"].append(deepcopy(d["trials"][0])),
                         lambda d: d["sites"][0].update(trial_id="missing"),
                         lambda d: d["trials"][0].update(id="<script>"),
                         lambda d: d["sites"][0].update(country="United States")):
            data = base()
            mutation(data)
            with self.assertRaises(ValueError):
                validate(data)

    def test_invalid_filters(self):
        for country, kind in (("US' OR 1=1--", None), ("USA", None), (None, "UNKNOWN")):
            with self.assertRaises(ValueError):
                analyze(base(), country, kind)

    def test_empty_dataset(self):
        result = analyze({"trials": [], "sites": [], "interventions": []}, country=None)
        self.assertEqual(result["corrected"]["trial_count"], 0)
        self.assertIsNone(result["incorrect"]["enrollment_sum"])

    def test_repeat_analysis_does_not_mutate_fixture(self):
        data = base()
        saved = deepcopy(data)
        first = analyze(data)
        self.assertEqual(analyze(data), first)
        self.assertEqual(data, saved)


class PresentationTests(unittest.TestCase):
    def scenario(self):
        scenario = scenarios()[0]
        scenario["result"] = analyze(scenario["data"])
        return scenario

    def test_graph_counts(self):
        scenario = self.scenario()
        svg = provenance_svg(scenario)
        ET.fromstring(svg)
        self.assertEqual(svg.count('class="trial-node"'), 3)
        self.assertEqual(svg.count('class="joined-node"'), 4)
        self.assertEqual(svg.count('class="cohort-node"'), 3)
        self.assertEqual(comparisons_svg(scenario).count('class="rate-observation"'), 5)

    def test_render_escapes_text(self):
        scenario = self.scenario()
        scenario["title"] = '<img src=x onerror="alert(1)">'
        scenario["description"] = "<script>bad()</script>"
        rendered = make_html({"scenarios": [scenario]})
        self.assertNotIn('<img src=x', rendered)
        self.assertNotIn('<script>bad()', rendered)
        self.assertIn('&lt;img', rendered)

    def test_bad_geometry_rejected(self):
        scenario = self.scenario()
        scenario["result"]["incorrect"]["enrollment_sum"] = '<script>x</script>'
        with self.assertRaises(ValueError):
            comparisons_svg(scenario)

    def test_aggregate_geometry_exceeds_single_record_cap(self):
        data = {"trials": [{"id": "T1", "enrollment": 1_000_000_000, "rate": 10},
                           {"id": "T2", "enrollment": 1_000_000_000, "rate": 10}],
                "sites": [], "interventions": []}
        scenario = {"id": "large-values", "title": "Large valid aggregate",
                    "result": analyze(data, country=None)}
        self.assertEqual(scenario["result"]["corrected"]["enrollment_sum"], 2_000_000_000)
        ET.fromstring(comparisons_svg(scenario))
        # Both filters use inner joins: 1000 sites x 1000 interventions is the
        # maximum row count; unmatched site-free trials do not survive that join.
        extreme_sum = 1_000_000 * 1_000_000_000
        self.assertEqual(number(extreme_sum), extreme_sum)

    def test_dense_equal_rates_stay_inside_svg(self):
        for count in (30, 1000):
            data = {"trials": [{"id": f"T{x}", "enrollment": 1, "rate": 10} for x in range(count)],
                    "sites": [], "interventions": []}
            scenario = {"id": "dense-rates", "title": "Equal rates remain independent",
                        "result": analyze(data, country=None)}
            svg = ET.fromstring(comparisons_svg(scenario))
            height = float(svg.attrib["viewBox"].split()[3])
            circles = svg.findall('.//{http://www.w3.org/2000/svg}circle')
            self.assertEqual(len(circles), count + 1)
            for circle in circles:
                y, radius = float(circle.attrib['cy']), float(circle.attrib['r'])
                self.assertGreaterEqual(y - radius, 0)
                self.assertLessEqual(y + radius, height)

    def test_cli_reproduces(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-B", "-m", "registry_metrics", "--out", directory],
                                    capture_output=True, text=True, check=True, timeout=30)
            output = json.loads((Path(directory) / "results.json").read_text(encoding="utf-8"))
            self.assertEqual(output["scenario_count"], 11)
            self.assertEqual(len(list((Path(directory) / "figures").glob("*.svg"))), 34)
            self.assertEqual(output["scenarios"][0]["result"]["corrected"]["enrollment_sum"], 500)
            self.assertIn('"scenarios": 11', result.stdout)
            self.assertTrue((Path(directory) / "index.html").is_file())


if __name__ == '__main__':
    unittest.main()
