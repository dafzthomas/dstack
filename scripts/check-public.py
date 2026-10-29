#!/usr/bin/env python3
"""Check tracked files, or all reachable Git history, for common disclosures.

Reports categories and locations without printing matched values. This is a
privacy guard, not a replacement for a dedicated secret scanner or manual review.
"""

import argparse
import re
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--history', action='store_true', help='scan all reachable objects and commit metadata')
parser.add_argument('--denylist', type=Path, help='private file of literal strings, one per line; never commit it')
args = parser.parse_args()
root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
rules = {
    'email': r'\b[A-Z0-9._%+-]+@(?!users\.noreply\.github\.com\b|noreply\.github\.com\b|example\.(?:com|org|net)\b)[A-Z0-9.-]+\.[A-Z]{2,}\b',
    'personal-home-path': r'(?:/Users/|/home/|[A-Z]:\\Users\\)[A-Z0-9._-]+',
    'private-key': r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    'credential': r'\b(?:gh[pousr]_[A-Z0-9]{20,}|github_pat_[A-Z0-9_]{20,}|AKIA[A-Z0-9]{16}|sk-(?:proj-|live_)?[A-Z0-9_-]{20,})\b',
    'url-credentials': r'https?://[^\s/@]+:[^\s/@]+@',
    'private-network': r'\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b',
}
if args.denylist:
    for index, line in enumerate(args.denylist.read_text().splitlines(), 1):
        if line.strip():
            rules[f'private-denylist-{index}'] = re.escape(line.strip())
patterns = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in rules.items()}
items = []
if args.history:
    objects = subprocess.check_output(['git', 'rev-list', '--objects', '--all'], cwd=root, text=True).splitlines()
    for entry in objects:
        oid, _, name = entry.partition(' ')
        kind = subprocess.check_output(['git', 'cat-file', '-t', oid], cwd=root, text=True).strip()
        if kind in ('blob', 'commit', 'tag'):
            content = subprocess.check_output(['git', 'cat-file', kind, oid], cwd=root).decode('utf-8', errors='replace')
            items.append((f'{oid[:12]}:{name or kind}', content))
else:
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    for name in filter(None, paths):
        path = root / name
        if path.is_symlink():
            items.append((name, str(path.readlink())))
        elif path.is_file():
            items.append((name, path.read_text(errors='replace')))
findings = []
for location, content in items:
    for category, pattern in patterns.items():
        if pattern.search(location) or pattern.search(content):
            findings.append(f'{category}: {location}')
    filename = location.split(':', 1)[-1]
    if re.search(r'(?:^|/)(?:\.env(?:\..*)?|\.netrc|\.npmrc|id_rsa|id_ed25519)$|\.(?:pem|key|p12|pfx|sqlite)(?:-.*)?$', filename):
        findings.append(f'sensitive-filename: {location}')
for finding in findings:
    print(finding)
print(f'Scanned {len(items)} items; {len(findings)} potential disclosures.')
raise SystemExit(bool(findings))
