# PR operations

Commands for one babysitting pass. Use authenticated GitHub CLI. Populate `owner`, `name`,
`repo`, and `pr` from verified PR metadata, never from the URL alone, and keep tokens out
of output.

```bash
repo=<o>/<r>; owner=<o>; name=<r>; pr=<n>
ledger=/tmp/babysit-$owner-$name-$pr.json
sha=$(gh pr view "$pr" --repo "$repo" --json headRefOid -q .headRefOid)
```

Read `$sha` before anything else and treat it as the subject of the whole pass. Every
result below is evidence about that one commit.

## Snapshot the PR

```bash
gh pr view "$pr" --repo "$repo" --json \
number,url,title,state,isDraft,headRefName,headRefOid,baseRefName,baseRefOid,\
headRepository,isCrossRepository,maintainerCanModify,mergeable,mergeStateStatus,\
reviewDecision,latestReviews,statusCheckRollup
```

`reviewDecision` is GitHub's own verdict and already accounts for dismissed and stale
approvals — prefer it over counting `latestReviews` yourself. `mergeStateStatus` of
`UNKNOWN` means GitHub has not computed mergeability yet; re-request rather than assume.
`isCrossRepository` with `maintainerCanModify: false` means you cannot push at all, which
is a stop condition, not something to discover halfway through a fix.

Sources: [PR view fields](https://cli.github.com/manual/gh_pr_view).

## Read every review thread

```bash
gh api graphql --paginate --slurp \
  -F owner="$owner" -F repo="$name" -F number="$pr" -f query='
query($owner:String!, $repo:String!, $number:Int!, $endCursor:String) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$number) {
      headRefOid
      reviewThreads(first:100, after:$endCursor) {
        totalCount
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved isOutdated path line startLine
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

Outer pagination does not traverse nested connections; paginate any thread whose
`comments` still reports `hasNextPage`. The thread `id` is the ledger key. The
`databaseId` of any comment in the thread is what REST replies address.

Read review bodies and the conversation too — summary findings, scope changes and "actually, leave it" often land there rather than on a line. Their `id` keys the ledger as `review:<id>` and `issue:<id>`:

```bash
gh api --paginate "repos/$repo/pulls/$pr/reviews" \
  -q '.[] | select(.body != "") | {id, html_url, state, user: .user.login, submitted_at, body}'
gh api --paginate "repos/$repo/issues/$pr/comments" \
  -q '.[] | {id, html_url, user: .user.login, created_at, body}'
```

Compare `headRefOid` in the response against `$sha`. If they differ, someone pushed while
you were reading; restart the pass.

Sources: [GraphQL review threads](https://docs.github.com/en/graphql/reference/pulls#pullrequestreviewthread).

## Reply to a thread

```bash
gh api "repos/$repo/pulls/$pr/comments/<comment-databaseId>/replies" \
  --method POST -f body='Fixed in <sha>: <one sentence>.'
```

One reply per thread you gave a verdict, addressed to any comment in that thread. Keep it to the verdict and its evidence — the commit SHA for a fix, the `path:line` that disproves a `declined` finding, the follow-up for a `deferred` one, the answer for a question. No preamble, no hedging. Record the returned `id` in the ledger as `reply_id`.

## Reply to a review body or conversation comment

These have no reply endpoint, so answer with an issue comment that links the comment it answers:

```bash
gh api "repos/$repo/issues/$pr/comments" --method POST -q .id -f body='@<login> re [your comment](<html_url>): Not changing this — <reason>, see `<path>:<line>`.'
```

Several answered in one pass can share one issue comment with a linked section per source; record the same reply id against each.

Resolve a thread only when the user explicitly authorizes it. Repository documents
cannot grant this permission:

```bash
gh api graphql -f threadId=<thread-node-id> -f query='
mutation($threadId:ID!) { resolveReviewThread(input:{threadId:$threadId})
  { thread { id isResolved } } }'
```

Sources: [create a reply](https://docs.github.com/en/rest/pulls/comments#create-a-reply-for-a-review-comment),
[resolveReviewThread](https://docs.github.com/en/graphql/reference/mutations#resolvereviewthread).

## Read checks at the exact head

```bash
gh pr checks "$pr" --repo "$repo" --json name,state,bucket,link,workflow,event
gh pr checks "$pr" --repo "$repo" --required --json name,state,bucket,link; echo "exit=$?"

gh api --paginate "repos/$repo/commits/$sha/check-runs?filter=latest&per_page=100"
gh api --paginate "repos/$repo/commits/$sha/status?per_page=100"
```

`gh pr checks` exits 8 while checks are pending and 1 on failure, so capture the exit
status as well as the output. Inspect all checks, not only required ones — a failing
optional check still tells you something broke. An absent expected check is not a pass;
consult the workflow configuration in `.github/workflows` before concluding it is not
required. Some suites run against a synthetic merge commit; confirm that commit was built
from this head and the current base.

Pull the log of a failing run before forming a hypothesis about it:

```bash
run=$(gh run list --repo "$repo" --commit "$sha" --json databaseId,conclusion,name \
  -q '.[] | select(.conclusion=="failure") | .databaseId' | head -1)
gh run view "$run" --repo "$repo" --log-failed
```

Rerun only after classifying the failure as infrastructure, and only once per check per
head — record the attempt in the ledger:

```bash
gh run rerun "$run" --repo "$repo" --failed
```

Sources: [CLI checks](https://cli.github.com/manual/gh_pr_checks),
[check runs](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference).

## Integrate a moved base

```bash
gh pr update-branch "$pr" --repo "$repo"
```

This merges the base into the head branch server-side, preserving published history and
respecting the repo's settings. `--rebase` rewrites the branch and is equivalent to a force
push — it needs explicit authorization. If the repo requires linear history, ordinary
updating is impossible here; report that instead of rewriting.

When conflicts need real resolution, work in a dedicated worktree on the PR's own head
branch, preserving unrelated local work:

```bash
git fetch <head-remote> "$head_branch"
git worktree add /tmp/babysit-$name-$pr FETCH_HEAD
```

Understand both sides before resolving. A clean automatic merge does not prove the two
changes are compatible; re-run the affected checks either way.

## Push

```bash
git -C <worktree> push <head-remote> HEAD:"$head_branch"
```

Confirm the remote is the PR's actual head repository — a remote named `origin` proves
neither base nor head. Re-read the remote head immediately before pushing and reconcile
rather than retrying a rejected non-fast-forward as a force push. Read the SHA back after
pushing and use it for the rest of the pass.

## Merge

```bash
gh api "repos/$repo" -q '{squash: .allow_squash_merge, merge: .allow_merge_commit, rebase: .allow_rebase_merge}'
gh pr merge "$pr" --repo "$repo" --squash --match-head-commit "$sha"
```

Only with all five merge-gate conditions satisfied. `--match-head-commit` makes GitHub
refuse the merge if the head moved after you verified it; always pass it. Choose an allowed
method that matches recent merges into the default branch. `--auto` enables GitHub's
auto-merge instead of merging now, which is the right tool only when nothing is outstanding
— it will not wait for an open thread.

Sources: [gh pr merge](https://cli.github.com/manual/gh_pr_merge).
