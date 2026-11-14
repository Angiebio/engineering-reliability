"""Check generated evidence matches the delivered source and local links."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent.parent

if __name__ == '__main__':
    report = json.loads((ROOT / 'artifacts/results.json').read_text(encoding='utf-8'))
    for name, digest in report['source_sha256'].items():
        assert hashlib.sha256((ROOT / 'registry_metrics' / name).read_bytes()).hexdigest() == digest, name
    files = [ROOT / 'artifacts/index.html', *ROOT.rglob('*.md')]
    for file in files:
        content = file.read_text(encoding='utf-8')
        targets = re.findall(r'href="([^"]+)"', content) if file.suffix == '.html' else re.findall(r'\]\(([^)]+)\)', content)
        for target in targets:
            if target.startswith(('http:', 'https:', '#')):
                continue
            assert (file.parent / target.split('#')[0]).is_file(), f'{file.name}: {target}'
    assert len(list((ROOT / 'artifacts/figures').glob('*.svg'))) == 34
    print(f"{len(report['source_sha256'])} source hashes, 34 SVG figures and local links verified")
