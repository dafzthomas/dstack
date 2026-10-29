# Thread operations

Commands for one watch pass. Use authenticated GitHub CLI, populate `owner`, `name`, and
`pr` from verified PR metadata rather than from the URL alone, and keep tokens out of
output.

```bash
repo=<o>/<r>; owner=<o>; name=<r>; pr=<n>
umask 077
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/review-pr-watch"
mkdir -p "$state_dir"
ledger="$state_dir/$owner-$name-$pr.json"
run_dir=$(mktemp -d "${TMPDIR:-/tmp}/review-watch.XXXXXXXX")
post_review=<review-pr skill directory>/scripts/post-review.py
me=$(gh api user -q .login)
sha=$(gh pr view "$pr" --repo "$repo" --json headRefOid -q .headRefOid)
```

Read `$sha` before anything else and treat it as the subject of the whole pass. Every result
below is evidence about that one commit.

Yours means authored by `$me` and opening with the attribution note. The operator posts
under the same account, so login alone also matches the threads and reviews they wrote
by hand.

## Recover the baseline from posted reviews

```bash
ME="$me" gh api --paginate "repos/$repo/pulls/$pr/reviews" \
  -q '.[] | select(.user.login == env.ME and ((.body // "") | test("^> \\[!NOTE\\]\\r?\\n> 🤖"))) | {id, state, commit_id, submitted_at}'

reviewed=$(ME="$me" gh api --paginate "repos/$repo/pulls/$pr/reviews" \
  -q '.[] | select(.user.login == env.ME and .submitted_at != null and ((.body // "") | test("^> \\[!NOTE\\]\\r?\\n> 🤖"))) | [.submitted_at, .commit_id] | @tsv' \
  | sort | tail -n 1 | cut -f2)
```

Prefer the matching ledger's completed `reviewed_sha` for an active watch. Clean passes
can advance that SHA without posting another review. Use the most recent submitted review
as a conservative recovery baseline when the ledger is missing. Recover owned findings
from that review history and the live threads before approving; a missing ledger does
not mean an empty finding list. Include findings recorded in review bodies as well as
inline threads. For a body-only finding, record the review id and claim without inventing
a thread id or calling thread mutations.

An empty result with no ledger means the first pass needs a full review. Continue polling
after publishing it.

## Poll for changes

Read PR state, head and base branch on every poll, even when the last poll found no changes:

```bash
gh pr view "$pr" --repo "$repo" --json state,headRefOid,baseRefName,autoMergeRequest,url
```

Also refresh reviews, the complete thread query below and issue discussion. A reply,
resolution or changed rationale requires assessment even at an unchanged head. A changed
`baseRefName` means the PR was retargeted and needs a full review. Store the observation
time and processed comment ids in the ledger. Persist each successful mutation before
waiting; after an interrupted request, read GitHub to determine whether it succeeded
before retrying it.

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
The script prints the review id; its comments carry the `databaseId` the thread query
returns:

```bash
review_id=$("$post_review" --repo "$repo" --pr "$pr" --sha "$sha" --model "<model name>" "$run_dir/review.json")
gh api "repos/$repo/pulls/$pr/reviews/$review_id/comments" -q '.[] | {databaseId: .id, path, line}'
```

Re-run the thread query and match each `databaseId` to the thread whose `comments` contain
it. On ledger recovery, rebuild this mapping from threads whose first comment is yours.
Only those threads may be resolved or unresolved later.

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

Compare the PR as you reviewed it with the PR as it stands. Keep one bare clone per
repository in the state directory:

```bash
base_ref=$(gh pr view "$pr" --repo "$repo" --json baseRefName -q .baseRefName)
export GIT_DIR="$state_dir/$owner-$name.git"
[ -d "$GIT_DIR" ] || gh repo clone "$repo" "$GIT_DIR" -- --bare --filter=blob:none
git fetch -q origin "+refs/heads/$base_ref:refs/remotes/origin/$base_ref" \
  "+refs/pull/$pr/head:refs/remotes/origin/pr/$pr"
git cat-file -e "$reviewed^{commit}" 2>/dev/null || git fetch -q origin "$reviewed"
old_base=$(git merge-base "origin/$base_ref" "$reviewed")
new_base=$(git merge-base "origin/$base_ref" "$sha")
git range-diff --diff-merges=remerge "$old_base..$reviewed" "$new_base..$sha"
```

Each line pairs a commit from your last review with one at `$sha`. `>` is new, `!` changed
and shows how, `=` is unchanged, and `<` was dropped. Review each new commit with
`git show --remerge-diff <commit>`, which shows a merge of the base branch only through its
conflict resolutions.

When `$reviewed` cannot be fetched after a force push, or `range-diff` rejects an empty
range, review the full PR diff for that pass and treat every thread anchor as outdated.

Prefer whole files over hunks — most defects live in the interaction between the new code
and the code around it. Confirm any line number you are about to post by numbering from the
file's own input lines; `cat -n` restarts at 1 and hands you an offset instead:

```bash
git show "$sha:<path>" | awk -v a=<a> -v b=<b> 'NR>=a && NR<=b {print NR": "$0}'
```

Sources: [git range-diff](https://git-scm.com/docs/git-range-diff).

## Post the pass review

```bash
# "$run_dir/review.json":
# {"body": "<per-finding verdicts + new findings>",
#  "comments": [{"path": "<path>", "line": <n>, "side": "RIGHT", "body": "<comment>"}]}
"$post_review" --repo "$repo" --pr "$pr" --sha "$sha" --model "<model name>" "$run_dir/review.json"
```

The script exits 3 when the head has moved from `$sha`; restart the pass. It exits 2 naming
each comment outside the PR's diff hunks; move those to the body citing `path:line`. A
deleted line takes `side: "LEFT"` and its old-file line number. `REQUEST_CHANGES` is not
available to this skill.

Skip the review entirely when a pass produced no new findings. Save the completed review
baseline in the ledger even when there is nothing to post. Thread replies carry inline
verdicts; body-only verdicts go to the user and the next authorized review body. Send
polling progress to the user as non-final messages.

## Approve a settled PR

```bash
gh pr view "$pr" --repo "$repo" --json headRefOid,autoMergeRequest \
  -q '{head: .headRefOid, auto_merge: (.autoMergeRequest != null)}'
printf '%s' '{"body": "Re-verified every finding at <sha> and reviewed the changes since <reviewed>. Nothing outstanding.", "comments": []}' \
  | "$post_review" --repo "$repo" --pr "$pr" --sha "$sha" --model "<model name>" --event APPROVE -
```

Only with every ledger finding `fixed` or `withdrawn`, the review complete through the
current head, and `auto_merge` false. With auto-merge armed, pause for the user instead.
The script posts nothing when your approval already stands at `$sha`, so a retry after an
interrupted response cannot create a duplicate. GitHub refuses to let you approve your own
PR; if the call fails for that reason, leave the PR unapproved and tell the user it is
settled.

## Dismiss your approval

```bash
gh api --method PUT "repos/$repo/pulls/$pr/reviews/<approval-review-id>/dismissals" \
  -f event=DISMISS -f message='<attribution note> <finding> at <sha>; approval withdrawn.'
```

Use the id of your `APPROVED` review from the baseline query. A protected branch can
restrict who may dismiss reviews; if the call fails, pause for the user.

Sources: [create a review](https://docs.github.com/en/rest/pulls/reviews#create-a-review-for-a-pull-request),
[dismiss a review](https://docs.github.com/en/rest/pulls/reviews#dismiss-a-review-for-a-pull-request).
