"""Read-only release checks for the generated report and evidence file.

Run from the project root after generating artifacts. This checks source binding
and relative links; it does not substitute for the lifecycle tests or visual QA.
"""

import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            target = dict(attrs).get("href")
            if target:
                self.targets.append(target)


def main():
    root = Path(__file__).resolve().parents[1]
    result = json.loads((root / "artifacts/results.json").read_text(encoding="utf-8"))
    for name, digest in result["source_sha256"].items():
        actual = hashlib.sha256((root / "promotion_gate" / name).read_bytes()).hexdigest()
        if actual != digest:
            raise AssertionError(f"Source changed since report: {name}")
    for name, digest in result['test_sha256'].items():
        if hashlib.sha256((root / 'tests' / name).read_bytes()).hexdigest() != digest:
            raise AssertionError(f'Test changed since report: {name}')
    links = Links()
    links.feed((root / "artifacts/index.html").read_text(encoding="utf-8"))
    for target in links.targets:
        if not (root / "artifacts" / target).is_file():
            raise AssertionError(f"Broken report link: {target}")
    print(f"Verified {len(result['source_sha256'])} source hashes, {len(result['test_sha256'])} test hashes and {len(links.targets)} report links.")


if __name__ == "__main__":
    main()
