"""Authored coverage fixtures; no real registry records or measured trial data.

Purpose: expose aggregation grain with hand-calculable expected answers.
Contract: return fresh independent dictionaries, never shared mutable fixtures.
Invariant: all scenarios are development examples, not held-out validation data.
Evidence: test_all_scenarios_match_independent_oracle checks every scenario.
"""
from copy import deepcopy


def base() -> dict:
    return {"trials": [{"id": "T1", "enrollment": 100, "rate": 10},
                       {"id": "T2", "enrollment": 100, "rate": 10},
                       {"id": "T3", "enrollment": 300, "rate": 30}],
            "sites": [{"id": "S1", "trial_id": "T1", "country": "US"},
                      {"id": "S2", "trial_id": "T1", "country": "US"},
                      {"id": "S3", "trial_id": "T2", "country": "US"},
                      {"id": "S4", "trial_id": "T3", "country": "US"}],
            "interventions": [{"id": "I1", "trial_id": "T1", "kind": "DRUG"},
                              {"id": "I2", "trial_id": "T2", "kind": "DRUG"},
                              {"id": "I3", "trial_id": "T3", "kind": "DEVICE"}]}


def scenarios() -> list[dict]:
    result = []
    def add(key, title, description, data, country="US", kind=None):
        result.append({"id": key, "title": title, "description": description,
                       "data": deepcopy(data), "country": country, "kind": kind})
    add("join-inflation", "One trial, two sites", "Four matching site rows represent three trials. Summing joined rows counts T1 twice; numeric DISTINCT erases one of the equal rates.", base())
    data = base()
    data["sites"].append({"id": "S5", "trial_id": "T1", "country": "US"})
    add("extra-site", "Add a site, keep the cohort", "An extra matching site changes the flawed total, but contributes no new trial or trial-level enrollment.", data)
    data = base()
    data["interventions"].append({"id": "I4", "trial_id": "T1", "kind": "DRUG"})
    add("join-multiplication", "Sites times interventions", "Two sites and two matching interventions multiply T1 into four rows. DRUG filters select T1 and T2; they do not weight T1 four times.", data, kind="DRUG")
    data = base()
    data["trials"][0]["enrollment"] = None
    data["trials"][1]["rate"] = None
    add("missing-values", "Unknown is not zero", "Unknown enrollment is excluded from the sum, and unknown rate from its denominator. Trial membership remains three.", data)
    data = base()
    data["sites"].append({"id": "S5", "trial_id": "T1", "country": "CA"})
    add("multinational", "Countries overlap", "T1 belongs to the US and Canadian site groups. Both groups contain trial-wide enrollment; group totals cannot be added into a global total.", data, country=None)
    add("country-filter", "Filter membership, not arithmetic", "The Canadian group contains T1 once, regardless of its two US sites. The trial-wide total does not tell us where its participants enrolled.", data, country="CA")
    data = base()
    data["trials"].append({"id": "T4", "enrollment": 200, "rate": None})
    data["sites"].append({"id": "S5", "trial_id": "T4", "country": None})
    add("unknown-geography", "A trial without known geography", "The overall cohort includes T4; known-country groups do not. Every denominator shows its own membership.", data, country=None)
    add("empty-cohort", "No matching trials", "The selected country has no matching site. Missing aggregate values remain null, with an explicit zero-trial denominator.", base(), country="GB")
    data = base()
    for row in data["trials"]:
        row["enrollment"] = None
        row["rate"] = None
    add("all-missing", "Three trials, no known values", "Three eligible trials have no enrollment or rate values. The report must not invent a zero mean, zero sum, or three measured rates.", data)
    data = review_map_fixture()
    add("review-map", "The unfiltered country map", "The map always joins sites. Two US sites for T1 inflate its US trial-wide total to 670 instead of 570, even with no country filter. A site-free trial remains in the overall cohort.", data, country=None)
    add("review-map-drug", "The map joins interventions too", "Two DRUG records for T1 multiply its three site rows. The flawed US total becomes 870 instead of 570; CA becomes 200 instead of 100.", data, country=None, kind="DRUG")
    return result


def review_map_fixture() -> dict:
    """Reproduce the review's six invented trials, never a clinical data sample."""
    data = base()
    data['trials'].extend([{'id': 'T4', 'enrollment': 50, 'rate': 5},
                           {'id': 'T5', 'enrollment': 70, 'rate': 7},
                           {'id': 'T6', 'enrollment': 100, 'rate': 10}])
    data['sites'].extend([{'id': 'S5', 'trial_id': 'T1', 'country': 'CA'},
                          {'id': 'S6', 'trial_id': 'T5', 'country': 'US'},
                          {'id': 'S7', 'trial_id': 'T6', 'country': 'DE'}])
    data['interventions'] = [{'id': f'I{i}', 'trial_id': trial, 'kind': 'DRUG'}
                             for i, trial in enumerate(('T1', 'T1', 'T2', 'T3', 'T5', 'T6'), 1)]
    return data
