# GitHub operations

Use authenticated GitHub CLI or equivalent API tools. Keep tokens out of output.
Commands below use shell variables populated from verified repository and PR
metadata. Store snapshots in the run's local scratch directory.

## Inventory all authored open PRs

Prefer the viewer's PR connection over search, which caps results at 1,000.
This query covers drafts and fork contributions and paginates the outer list:

```bash
gh api graphql --paginate --slurp -f query='
query($endCursor: String) {
  viewer {
    login
    pullRequests(
      states: OPEN, first: 100, after: $endCursor,
      orderBy: {field: CREATED_AT, direction: ASC}
    ) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        id number url title isDraft updatedAt
        baseRefName baseRefOid headRefName headRefOid
        isCrossRepository maintainerCanModify
        headRepository { nameWithOwner }
        repository {
          nameWithOwner
          defaultBranchRef { name target { oid } }
        }
      }
    }
  }
}' > "$run_dir/inventory.json"
```

Check the command's exit status and every response's `errors`, null nodes, and
`pageInfo`. Deduplicate by PR node ID or repository plus number and reconcile
against `totalCount` before applying requested scope filters. Changes during
pagination may require a fresh inventory. Organization SSO restrictions can
produce partial data with null PRs even when `totalCount` is larger. Retain the
readable PRs and report the inaccessible count and errors. Authentication only
establishes access to the resources this session can read.

`--slurp` and `--jq` cannot be combined. Parse the saved pages separately. If
GraphQL is unavailable, use REST search with pagination, inspect `total_count`
and `incomplete_results`, and partition by repository or non-overlapping creation
dates when a query exceeds the search cap. Deduplicate across partitions.
`gh search prs --author=@me --state=open --limit=1000` is useful for discovery
but does not by itself prove complete coverage.

Sources: [CLI API and pagination](https://cli.github.com/manual/gh_api),
[GraphQL user](https://docs.github.com/en/graphql/reference/users#user),
[search limits](https://docs.github.com/en/rest/search/search#about-search).

## Snapshot one PR and its review threads

```bash
gh pr view "$pr" --repo "$repo" --json \
number,url,title,body,state,isDraft,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,headRepositoryOwner,isCrossRepository,maintainerCanModify,mergeable,mergeStateStatus,reviewDecision,latestReviews,statusCheckRollup

gh pr diff "$pr" --repo "$repo"

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
          id isResolved isOutdated path line
          comments(first:100) {
            pageInfo { hasNextPage endCursor }
            nodes { url body author { login } }
          }
        }
      }
    }
  }
}'
```

Paginate comments separately for any thread whose comments connection still has
`hasNextPage`. Outer pagination does not traverse nested connections. Read the
PR discussion too when it explains scope or outstanding decisions. An outdated
thread can still contain an unresolved concern. Treat `UNKNOWN` mergeability as
unsettled and refresh it before declaring readiness.

Sources: [PR view fields](https://cli.github.com/manual/gh_pr_view),
[GraphQL review threads](https://docs.github.com/en/graphql/reference/pulls#pullrequestreviewthread).

## Compare immutable commits

Record and fetch the actual target, main, and head commits. After verifying
these objects locally, inspect both sides of their shared history:

```bash
merge_base=$(git merge-base "$target_sha" "$head_sha")
git diff "$merge_base" "$head_sha"
git log --oneline "$merge_base..$target_sha"
git diff "$merge_base" "$target_sha"
```

Repeat the comparison against `main_sha` when it differs from the target. Read
the current implementations and callers for affected contracts, including
changes outside the PR's file list. A previously merged target can hide an
earlier contract change from this interval, so inspect earlier history when
the current code and PR intent disagree. Use the full local diff if GitHub's
diff endpoint is too large or unavailable.

Verify remote URLs against the PR's base and head repositories; a remote named
`origin` is not proof of either. `refs/pull/<number>/head` can supply readable
commits, but it is not the contributor's push destination. Fork write access
must be established independently. Push to the actual head branch only after
the coordinator's concurrency check. A rejected non-fast-forward push requires
reconciliation, not an automatic force retry.

## Confirm checks belong to the delivered head

```bash
gh pr checks "$pr" --repo "$repo" \
  --json name,state,bucket,link,workflow,event
gh pr checks "$pr" --repo "$repo" --required \
  --json name,state,bucket,link

gh api --paginate \
  "repos/$repo/commits/$head_sha/check-runs?filter=latest&per_page=100"
gh api --paginate \
  "repos/$repo/commits/$head_sha/status?per_page=100"
```

Capture exit status as well as output. `gh pr checks` uses exit code 8 for
pending checks. Inspect all reported checks as well as required checks, and
paginate commit status results. Re-read the PR head after collecting evidence;
if it changed, the earlier results cannot establish the new head's readiness.
Some CI runs validate a synthetic merge commit. Record that association and
check that it uses the intended current head and target. Consult repository
workflow configuration when an expected check is absent. Report unavailable
branch rules or provider access instead of assuming no checks are required.

Sources: [CLI checks](https://cli.github.com/manual/gh_pr_checks),
[check runs](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference),
[commit status](https://docs.github.com/en/rest/commits/statuses#get-the-combined-status-for-a-specific-reference).
