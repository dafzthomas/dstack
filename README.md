# Agent skills

Reusable Codex skills for pull request review and delivery.

## Included skills

| Skill | Purpose |
| --- | --- |
| `review-pr` | Review a GitHub PR for genuine bugs and architectural problems, then post a summary and inline comments, or approve it when clean. |
| `review-pr-watch` | Continuously watch a review of any PR, whoever authored it, until settled: verify pushed fixes and replies, manage its threads, and review new commits. |
| `finish-delivery` | Carry an implementation through appropriate verification and PR handoff, preserving existing explicit merge authorization. |
| `what-in-the-pr` | Audit open PRs with subagents, refresh them against current main, and recommend next steps. |
| `babysit-pr` | Watch your own PR to merge: fix comments and checks, reply to every comment addressed, and ask in the thread when a comment needs your decision. |
| `tenth-man` | Act as a team's designated dissenter: make the strongest case against a consensus, then concede or hold when the team pushes back. |

Codex-managed system skills, plugin-provided skills, vendor skills, and generated
symlinks are intentionally excluded. They should be installed from their
original distributors instead of copied here.

## Install

Clone the repository, then link its skills into Codex:

```bash
./scripts/install.sh
```

The installer is deliberately non-destructive. It refuses to replace an
existing file, directory, or unrelated symlink under `~/.codex/skills`.

To use a different skill directory:

```bash
CODEX_SKILLS_DIR=/path/to/skills ./scripts/install.sh
```

To install only the PR catch-up skill globally with the Skills CLI:

```bash
npx skills add dafzthomas/dstack --skill what-in-the-pr --global
```

Select your agents when prompted.

## Validate

Run the repository checks locally:

```bash
./scripts/validate.sh
python3 scripts/check-public.py
```

The validator checks package structure, frontmatter names, unwanted local
artifacts, shell syntax, and JavaScript syntax. The Python privacy check flags
common email, machine-path, credential, and private-network patterns in tracked
files. Run `python3 scripts/check-public.py --history` to include all reachable
Git history and commit metadata. Use `--denylist /private/path/to/terms.txt` for
private names and project identifiers. Keep that file outside the repository.
These pattern checks supplement a dedicated secret scan and manual review.

## Add a skill

1. Add a self-contained directory at `skills/<skill-name>/`.
2. Put its instructions in `skills/<skill-name>/SKILL.md`.
3. Ensure the frontmatter `name` exactly matches the directory name.
4. Add only files required at runtime; never commit credentials or local state.
5. Run `./scripts/validate.sh`.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the repository contract.
