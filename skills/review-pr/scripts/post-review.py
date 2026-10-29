#!/usr/bin/env python3
"""Post one pull request review after checking it against the live PR.

Exits 3 when the head has moved from --sha, 2 when an inline comment sits outside the
PR's diff hunks, and 4 when an APPROVE meets armed auto-merge. Adds the attribution note
to the body and every inline comment. Does nothing when the same review is already
posted. Prints the review id.

Payload (a file path, or - for stdin):
  {"body": "...", "comments": [{"path": "...", "line": 12, "side": "RIGHT",
                                "start_line": 10, "body": "..."}]}
"""

import argparse
import json
import re
import subprocess
import sys

HUNK = re.compile(r'^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@')
NOTE_START = '> [!NOTE]\n> 🤖'


def gh(*args, stdin=None):
    result = subprocess.run(['gh', *args], input=stdin, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f'gh {" ".join(args[:2])} failed: {result.stderr.strip()}')
    return result.stdout


def gh_pages(path):
    return [item for page in json.loads(gh('api', '--paginate', '--slurp', path)) for item in page]


def commentable_lines(files):
    """Map (path, side) to {line: hunk index} for every line GitHub accepts a comment on."""
    index = {}
    for file in files:
        left = index.setdefault((file['filename'], 'LEFT'), {})
        right = index.setdefault((file['filename'], 'RIGHT'), {})
        hunk = -1
        for raw in (file.get('patch') or '').split('\n'):
            match = HUNK.match(raw)
            if match:
                hunk += 1
                old, new = int(match[1]), int(match[2])
            elif hunk < 0 or raw == '' or raw.startswith('\\'):
                continue
            elif raw[0] == '-':
                left[old] = hunk
                old += 1
            elif raw[0] == '+':
                right[new] = hunk
                new += 1
            else:
                left[old] = right[new] = hunk
                old += 1
                new += 1
    return index


def misplaced(comment, index):
    side = comment.get('side', 'RIGHT')
    lines = index.get((comment['path'], side), {})
    if comment['line'] not in lines:
        return f"{comment['path']}:{comment['line']} ({side}) is outside the diff"
    if 'start_line' in comment:
        start_lines = index.get((comment['path'], comment.get('start_side', side)), {})
        if start_lines.get(comment['start_line']) != lines[comment['line']] or comment['start_line'] >= comment['line']:
            return f"{comment['path']}:{comment['start_line']}-{comment['line']} is not an ascending range inside one hunk"
    return None


def attributed(text, note):
    return text if text.startswith(NOTE_START) else note + text


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', required=True, help='owner/name')
    parser.add_argument('--pr', required=True, type=int)
    parser.add_argument('--sha', required=True, help='the head SHA the review covers')
    parser.add_argument('--model', required=True, help='model name for the attribution note')
    parser.add_argument('--event', choices=['COMMENT', 'APPROVE'], default='COMMENT')
    parser.add_argument('--dry-run', action='store_true', help='print the final payload instead of posting')
    parser.add_argument('payload')
    args = parser.parse_args()

    with (sys.stdin if args.payload == '-' else open(args.payload)) as source:
        payload = json.load(source)
    comments = payload.get('comments', [])
    if args.event == 'APPROVE' and comments:
        sys.exit('An APPROVE review carries no inline comments; post findings as COMMENT.')

    pull = f'repos/{args.repo}/pulls/{args.pr}'
    pull_request = json.loads(gh('api', pull))
    head = pull_request['head']['sha']
    if head != args.sha:
        print(f'Head moved from {args.sha} to {head}. Restart the review at the new head.', file=sys.stderr)
        sys.exit(3)
    if args.event == 'APPROVE' and pull_request.get('auto_merge'):
        print('Auto-merge is armed, so this approval could merge the PR. Pause for the operator.', file=sys.stderr)
        sys.exit(4)

    index = commentable_lines(gh_pages(f'{pull}/files'))
    problems = [problem for problem in (misplaced(c, index) for c in comments) if problem]
    if problems:
        print('\n'.join(problems + ['Move these findings into the review body, citing path:line.']), file=sys.stderr)
        sys.exit(2)

    note = f'{NOTE_START} **{args.model} responding on behalf of the repository operator**\n\n'
    review = {
        'commit_id': args.sha,
        'event': args.event,
        'body': attributed(payload.get('body', ''), note),
        'comments': [{**c, 'body': attributed(c['body'], note)} for c in comments],
    }
    if args.dry_run:
        print(json.dumps(review, indent=2, ensure_ascii=False))
        return

    me = gh('api', 'user', '-q', '.login').strip()
    for existing in gh_pages(f'{pull}/reviews'):
        if existing['user']['login'] != me or existing['commit_id'] != args.sha:
            continue
        approved = args.event == 'APPROVE' and existing['state'] == 'APPROVED'
        same = args.event == 'COMMENT' and (existing['body'] or '').strip() == review['body'].strip()
        if approved or same:
            print(f'Already posted as review {existing["id"]}.', file=sys.stderr)
            print(existing['id'])
            return

    posted = json.loads(gh('api', f'{pull}/reviews', '--method', 'POST', '--input', '-', stdin=json.dumps(review)))
    print(posted['id'])


if __name__ == '__main__':
    main()
