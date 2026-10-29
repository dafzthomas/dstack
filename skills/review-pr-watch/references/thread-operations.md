# Thread operations

Commands for one watch pass. Use authenticated GitHub CLI, populate `owner`, `name`, and
`pr` from verified PR metadata rather than from the URL alone, and keep tokens out of
output.

```bash
repo=<o>/<r>; owner=<o>; name=<r>; pr=<n>
ledger=/tmp/review-watch-$owner-$name-$pr.json
me=$(gh api user -q .login)
sha=$(gh pr view "$pr" --repo "$repo" --json headRefOid -q .headRefOid)
```

Read `$sha` before anything else and treat it as the subject of the whole pass. Every result
below is evidence about that one commit.

## Recover the baseline from posted reviews

```bash
gh api --paginate "repos/$repo/pulls/$pr/reviews" \
  -q "map(select(.user.login==\"$me\")) | .[] | {id, state, commit_id, submitted_at}"

reviewed=$(gh api --paginate --slurp "repos/$repo/pulls/$pr/reviews" \
  -q "add | map(select(.user.login==\"$me\" and .submitted_at != null)) | sort_by(.submitted_at) | last | .commit_id")
```

Prefer the matching ledger's completed `reviewed_sha` for an active watch. Clean passes
can advance that SHA without posting another review. Use the most recent submitted review
as a conservative recovery baseline when the ledger is missing. Recover owned findings
from that review history and the live threads before approving; a missing ledger does
not mean an empty finding list. Include findings recorded in review bodies as well as
inline threads. For a body-only finding, record the review id and claim without inventing
a thread id or calling thread mutations.

An empty result with no ledger means the first pass needs a full review. Continue polling
after publishing it while findings remain.

## Poll for changes

Read PR state and both SHAs on every poll, even when the last poll found no changes:

```bash
gh pr view "$pr" --repo "$repo" --json state,headRefOid,baseRefOid,url
```

Also refresh reviews, the complete thread query below and issue discussion. A reply,
resolution or changed rationale requires assessment even at an unchanged head. A base
change requires a full PR review. Store the observation time and processed comment ids
in the ledger. Persist each successful mutation before waiting; after an interrupted
request, read GitHub to determine whether it succeeded before retrying it.

## Confirm the baseline still describes reality

```bash
git fetch origin "pull/$pr/head"
git merge-base --is-ancestor "$reviewed" "$sha" && echo "linear" || echo "history rewritten"
```

Without a checkout, ask GitHub instead — a rewritten history shows up as commits present in
the compare's `base_commit` that no longer appear in the head:

```bash
gh api "repos/$repo/compare/$reviewed...$sha" -q '{status: .status, ahead: .ahead_by, behind: .behind_by}'
```

`status: "diverged"` or a non-zero `behind_by` means the branch was force-pushed or rebased.
`$reviewed..$sha` is then a diff that never existed: review the full PR diff for that pass and
treat every thread anchor as outdated.

Sources: [compare commits](https://docs.github.com/en/rest/commits/commits#compare-two-commits).

## Read every review thread

```bash
gh api graphql --paginate --slurp \
  -F owner="$owner" -F repo="$name" -F number="$pr" -f query='
query($owner:String!, $repo:String!, $number:Int!, $endCursor:String) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$number) {
      headRefOid
      reviewThreads(first:100, after:$endCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved isOutdated path line originalLine
          resolvedBy { login }
          comments(first:100) {
            pageInfo { hasNextPage endCursor }
            nodes { databaseId url body createdAt author { login } }
          }
        }
      }
    }
  }
}'
```

The thread `id` is the ledger key and the argument to both resolve mutations. The
`databaseId` of any comment in the thread is what REST replies address. `resolvedBy` tells
you whether a resolution was yours — a thread resolved by the author is the case step 2 of
the skill exists to catch.

Outer pagination does not traverse nested connections; paginate any thread still reporting
`comments.hasNextPage`. Compare `headRefOid` in the response against `$sha`, and restart the
pass if they differ.

Read the issue-level discussion too. "Actually, leave that one" and scope changes land there
rather than on a line:

```bash
gh api --paginate "repos/$repo/issues/$pr/comments" \
  -q '.[] | {user: .user.login, created_at, body}'
```

Sources: [GraphQL review threads](https://docs.github.com/en/graphql/reference/pulls#pullrequestreviewthread).

## Record which threads are yours

After posting a review, map its comments back to thread ids so the ledger can key on them.
The review response carries its own id; its comments carry the `databaseId` the thread query
returns:

```bash
review_id=$(gh api "repos/$repo/pulls/$pr/reviews" --method POST --input /tmp/review.json -q .id)
gh api "repos/$repo/pulls/$pr/reviews/$review_id/comments" -q '.[] | {databaseId: .id, path, line}'
```

Re-run the thread query and match each `databaseId` to the thread whose `comments` contain
it. On ledger recovery, use comments from your previous reviews to rebuild this mapping.
Only threads whose original finding you posted may be resolved or unresolved later.

## Reply to a thread

```bash
gh api "repos/$repo/pulls/$pr/comments/<comment-databaseId>/replies" \
  --method POST -f body='Fixed in <sha>: <one sentence>.'
```

One reply per thread you acted on, addressed to any comment in that thread. Keep it to the
verdict and its evidence — the commit for a `fixed`, the `path:line` that still breaks for a
`regressed`, the reason for a `withdrawn`. No preamble, no hedging, no restating the original
finding back at them.

## Resolve and unresolve

```bash
gh api graphql -f threadId=<thread-node-id> -f query='
mutation($threadId:ID!) { resolveReviewThread(input:{threadId:$threadId})
  { thread { id isResolved } } }'

gh api graphql -f threadId=<thread-node-id> -f query='
mutation($threadId:ID!) { unresolveReviewThread(input:{threadId:$threadId})
  { thread { id isResolved } } }'
```

Unresolve before replying so the reply lands in an open thread. Both mutations are limited to
threads in the ledger — a thread you did not post is not yours to close, whatever state it is
in.

Sources: [resolveReviewThread](https://docs.github.com/en/graphql/reference/mutations#resolvereviewthread),
[unresolveReviewThread](https://docs.github.com/en/graphql/reference/mutations#unresolvereviewthread).

## Read the incremental change

```bash
gh api "repos/$repo/compare/$reviewed...$sha" -q '.files[] | {filename, status, changes}'
gh api "repos/$repo/compare/$reviewed...$sha" -q '.commits[] | {sha: .sha, message: .commit.message}'
```

With a working tree available, prefer whole files over hunks — most defects live in the
interaction between the new code and the code around it:

```bash
git diff "$reviewed".."$sha"
git show "$sha:<path>"
```

Without one, read files at the exact SHA through the contents API. Remember to url-encode
`[param]` style path segments:

```bash
gh api "repos/$repo/contents/<url-encoded-path>?ref=$sha" -q .content | base64 -d
```

Confirm any line number you are about to post by numbering from the file's own input lines;
`cat -n` restarts at 1 and hands you an offset instead:

```bash
gh api "repos/$repo/contents/<url-encoded-path>?ref=$sha" -q .content \
  | base64 -d | awk -v a=<a> -v b=<b> 'NR>=a && NR<=b {print NR": "$0}'
```

## Post the pass review

```bash
# /tmp/review.json:
# {"commit_id": "<sha>", "event": "COMMENT", "body": "<per-finding verdicts + new findings>",
#  "comments": [{"path": "<path>", "line": <n>, "side": "RIGHT", "body": "<comment>"}]}
gh api "repos/$repo/pulls/$pr/reviews" --method POST --input /tmp/review.json
```

Inline comments are only accepted on lines the compare reports as added or changed. One
off-diff entry 422s the entire review, so anything anchored elsewhere goes in the body citing
`path:line`. `event` is `COMMENT` whenever comments are attached; `REQUEST_CHANGES` is not
available to this skill.

Skip the review entirely when a pass produced no new findings. Save the completed review
baseline in the ledger even when there is nothing to post. Thread replies carry inline
verdicts; body-only verdicts go to the user and the next authorized review body. Send
polling progress to the user as non-final messages.

## Approve a settled PR

```bash
gh api "repos/$repo/pulls/$pr/reviews" --method POST \
  -f commit_id="$sha" -f event=APPROVE \
  -f body="Re-verified every finding at $sha and reviewed the changes since <reviewed>. Nothing outstanding."
```

Only with every ledger finding `fixed` or `withdrawn` and the review complete through the
current head and base. Refresh head, base and discussion immediately before approval.
Skip a non-dismissed approval already posted for that SHA. After any approval attempt, read live
reviews before retrying so an interrupted response cannot create a duplicate.
GitHub refuses to let you approve your own PR; if the call fails for that reason, leave the
PR unapproved and tell the user it is settled.

Sources: [create a review](https://docs.github.com/en/rest/pulls/reviews#create-a-review-for-a-pull-request).
