"""Generate actual SQL outcomes, self-contained HTML and exportable SVG figures.

Purpose: one command reproduces every displayed value and graph from source.
Contract: authored fixtures -> validated SQLite -> report; no external IO except
writing the explicit output directory. No network, model, or production database.
Invariant: graphical nodes and metric values originate from the saved result.
Failure: invalid data or any computation error aborts; no partial success claim.
Evidence: test_cli_reproduces and test_all_scenarios_match_independent_oracle.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sqlite3

from .core import analyze
from .fixtures import scenarios, base
from .report import make_html, provenance_svg, comparisons_svg, geography_svg, sweep_svg


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def site_sweep() -> list[dict]:
    """Measure each dial position with SQL; never draw an assumed straight line.

    The cohort remains three trials while the site table changes. The second
    unfiltered query models the map's always-on site join. Evidence:
    test_site_sweep_reexecutes_sql_and_records_geography.
    """
    points = []
    for extra in range(11):
        data = base()
        data['sites'].append({'id': 'CA1', 'trial_id': 'T1', 'country': 'CA'})
        data['sites'].extend({'id': f'X{i}', 'trial_id': 'T1', 'country': 'US'} for i in range(extra))
        stats, world = analyze(data, 'US'), analyze(data, None)
        points.append({'extra_sites': extra, 'data': data, 'stats': stats, 'world': world})
    return points


def generate(output: Path) -> dict:
    values = scenarios()
    fixture_hash = hashlib.sha256(canonical(values)).hexdigest()
    for scenario in values:
        scenario["result"] = analyze(scenario["data"], scenario["country"], scenario["kind"])
        wrong, correct = scenario['result']['incorrect'], scenario['result']['corrected']
        # A globally correct sum may still conceal a broken country map. Keep
        # both comparisons in the visible tag; evidence:
        # test_generated_failure_tags_include_map_disagreements.
        difference = any(wrong[key] != correct[key] for key in ('enrollment_sum', 'rate_n', 'rate_median'))
        difference |= [(g['country'], g['trial_enrollment_sum']) for g in wrong['geography']] != [(g['country'], g['trial_enrollment_sum']) for g in scenario['result']['geography']]
        scenario['category'] = 'Failure example' if difference else 'Control example'
    source = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob("*.py"))}
    report = {"protocol": "registry-metric-lab-v2", "kind": "synthetic_development_demonstration",
              "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
              "fixture_sha256": fixture_hash, "source_sha256": source,
              "scenario_count": len(values), "model_calls": 0, "scenarios": values, 'site_sweep': site_sweep()}
    (output / "figures").mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline='\n')
    (output / "index.html").write_text(make_html(report), encoding="utf-8", newline='\n')
    (output / 'figures/site-sweep.svg').write_text(sweep_svg(report['site_sweep']), encoding='utf-8', newline='\n')
    for scenario in values:
        for name, render in (("identity", provenance_svg), ("comparison", comparisons_svg), ('geography', geography_svg)):
            (output / "figures" / f"{scenario['id']}-{name}.svg").write_text(render(scenario), encoding="utf-8", newline='\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    report = generate(args.out)
    first = report["scenarios"][0]["result"]
    print(json.dumps({"scenarios": report["scenario_count"],
                      "original_example": {"incorrect": first["incorrect"], "corrected": first["corrected"]},
                      "report": str(args.out / "index.html")}, indent=2))


if __name__ == "__main__":
    main()
