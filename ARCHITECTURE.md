# Architecture

## Purpose

This repository contains portable, independently installable Codex skills.
A fresh clone must be enough to validate and
install every included skill without downloading repository-specific tooling.

## Directory contract

```text
.
├── skills/
│   └── <skill-name>/
│       ├── SKILL.md
│       ├── agents/       # optional agent metadata
│       ├── assets/       # optional static assets
│       ├── references/   # optional supporting instructions
│       └── scripts/      # optional runtime helpers
└── scripts/
    ├── install.sh
    └── validate.sh
```

Each direct child of `skills/` is an independently installable package.
`SKILL.md` is required, and its frontmatter `name` must exactly match the
directory name.

## Ownership boundary

Include user-authored skills and deliberate personal forks only. Exclude:

- Codex-managed `.system` skills and runtime placeholders;
- plugin caches and vendor-distributed skills;
- generated or dangling symlinks;
- secrets, environment files, logs, databases, and operating-system metadata.

If a third-party skill is intentionally forked later, preserve its licence and
document its upstream source and local changes.

## Installation model

`scripts/install.sh` creates one symlink per package in the configured Codex
skills directory. It never overwrites an existing path. This keeps the Git
checkout as the editable source of truth while making each skill discoverable
by Codex.

## Validation model

`scripts/validate.sh` has no third-party dependencies. It validates:

- required package files and matching frontmatter names;
- absence of known local artifacts;
- Bash syntax for shell helpers;
- JavaScript syntax for `.js`, `.mjs`, and `.cjs` helpers;
- Python syntax for `.py` helpers.

