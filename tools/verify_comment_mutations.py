"""Challenge curated comment claims by running their cited tests against a mutant.

Contract: exact, unique source anchors and an adjacent Mutation/Evidence comment
bind each manifest entry to a named test. The pristine cited tests must pass;
the syntactically valid mutant must fail those same tests. All changes occur in
disposable copies. Missing anchors, imports, tests or marker text fail the check.
Scope: this checks sensitivity to listed mutations. It cannot prove arbitrary
prose true, detect every defect or establish benefits for AI maintainability.

Usage, from the repository root:
    python -B tools/verify_comment_mutations.py            # all four demos
    python -B tools/verify_comment_mutations.py registry-metric-lab
Each record is written to build/comment-mutations/<demo>.json, which git ignores.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# Written for the review archive, where packages sat under builds/. In this repository
# they sit under demos/ and the records go to build/; nothing else changed.
ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ('continuity-ledger', 'adapter-promotion-gate', 'registry-metric-lab', 'stagnation-observatory')


def portable_trace(value, checkout):
    """Keep failure evidence while removing machine-specific traceback roots.

    Paths identify the package or runtime; test names, line numbers, messages
    and assertion values retain their original meaning. Evidence: the portable
    traceback tests, including decoded JSON rather than only literal backslashes.
    """
    for root, label in ((Path(checkout), '<package>'), (Path(sys.base_prefix), '<python-runtime>')):
        for spelling in (str(root), root.as_posix()):
            value = value.replace(spelling, label)
    value = re.sub(r'[A-Za-z]:[\\/]+Users[\\/]+[^\\/\r\n"\']+[\\/]+', '<user-home>/', value)
    return value


def execute(checkout, names):
    environment = os.environ.copy()
    environment['PYTHONPATH'] = os.pathsep.join((str(checkout / 'tests'), str(checkout)))
    environment['PYTHONUTF8'] = '1'
    command = [sys.executable, '-B', '-m', 'unittest', '-v', *names]
    run = subprocess.run(command, cwd=checkout, env=environment, capture_output=True,
                         text=True, encoding='utf-8', timeout=180)
    # Unittest's per-test failure header carries the exact qualified test name.
    failed = re.findall(r'^(?:FAIL|ERROR): \w+ \(([^)]+)\)', run.stderr, re.M)
    count = re.search(r'Ran (\d+) tests?', run.stderr)
    return {'command': ['python', '-B', '-m', 'unittest', '-v', *names],
            'exit_code': run.returncode, 'ran': int(count.group(1)) if count else 0,
            'failed_tests': failed, 'stdout': portable_trace(run.stdout, checkout),
            'stderr': portable_trace(run.stderr, checkout)}


def verify(package, *, package_dir=None, output=None):
    directory = Path(package_dir) if package_dir is not None else ROOT / 'demos' / package
    manifest = json.loads((directory / 'tests/comment_mutations.json').read_text(encoding='utf-8'))
    results = []
    identifiers = set()
    for contract in manifest:
        identifier = contract['id']
        if identifier in identifiers:
            raise ValueError('Duplicate mutation ID: ' + identifier)
        identifiers.add(identifier)
        source_path = (directory / contract['source']).resolve()
        if not source_path.is_relative_to(directory.resolve()) or source_path.suffix != '.py':
            raise ValueError('Mutation source must stay inside the package')
        source = source_path.read_text(encoding='utf-8')
        if source.count(contract['old']) != 1:
            raise ValueError(identifier + ': source anchor must occur exactly once')
        position = source.index(contract['old'])
        local_comment = source[max(0, position - 1800):position]
        if 'Mutation: ' + identifier not in local_comment:
            raise ValueError(identifier + ': missing adjacent Mutation marker')
        for name in contract['tests']:
            if not re.fullmatch(r'test_\w+\.\w+\.test_\w+', name):
                raise ValueError(identifier + ': use a full unittest module.Class.method')
            if name.split('.')[-1] not in local_comment:
                raise ValueError(identifier + ': comment does not cite ' + name)
        mutated = source.replace(contract['old'], contract['new'])
        if mutated == source:
            raise ValueError(identifier + ': mutation must change source')
        compile(mutated, contract['source'], 'exec')
        with tempfile.TemporaryDirectory(prefix='comment-contract-') as temporary:
            checkout = Path(temporary) / package
            shutil.copytree(directory, checkout, ignore=shutil.ignore_patterns('artifacts', 'qa', '__pycache__', '.git', '.pytest_cache'))
            baseline = execute(checkout, contract['tests'])
            if baseline['exit_code'] or baseline['ran'] != len(contract['tests']):
                raise RuntimeError(identifier + ': pristine cited test did not pass\n' + baseline['stderr'])
            (checkout / contract['source']).write_text(mutated, encoding='utf-8', newline='\n')
            mutant = execute(checkout, contract['tests'])
        caught = (mutant['exit_code'] != 0 and mutant['ran'] == len(contract['tests'])
                  and set(contract['tests']) <= set(mutant['failed_tests'])
                  and 'ModuleNotFoundError' not in mutant['stderr']
                  and 'ImportError' not in mutant['stderr'])
        results.append({**contract, 'source_sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(),
                        'mutated_source_sha256': hashlib.sha256(mutated.encode('utf-8')).hexdigest(),
                        'baseline': baseline, 'mutant': mutant, 'caught_by_cited_tests': caught})
        print(f'{package}: {identifier}: ' + ('CAUGHT' if caught else 'SURVIVED'), flush=True)
    record = {'package': package, 'scope': 'curated comment contracts; not a completeness claim',
              'manifest_sha256': hashlib.sha256((directory / 'tests/comment_mutations.json').read_bytes()).hexdigest(),
              'source_sha256': {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in directory.rglob('*.py') if '__pycache__' not in p.parts},
              'contracts': results}
    destination = Path(output) if output is not None else ROOT / 'build' / 'comment-mutations' / f'{package}.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    if not all(item['caught_by_cited_tests'] for item in results):
        raise RuntimeError(package + ': an advertised comment contract survived its mutation')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packages', nargs='*', choices=PACKAGES)
    parser.add_argument('--package-dir', type=Path, help='An arbitrary standalone package with tests/comment_mutations.json')
    parser.add_argument('--output', type=Path, help='Evidence destination when using --package-dir')
    args = parser.parse_args()
    if args.package_dir is not None:
        if args.packages or args.output is None:
            parser.error('--package-dir requires --output and cannot combine with named packages')
        verify(args.package_dir.name, package_dir=args.package_dir, output=args.output)
        raise SystemExit(0)
    if args.output is not None:
        parser.error('--output requires --package-dir')
    for package in args.packages or PACKAGES:
        verify(package)
