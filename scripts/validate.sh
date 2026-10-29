#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
skills_root="$repo_root/skills"
errors=0
skill_count=0

report_error() {
  printf 'ERROR: %s\n' "$1" >&2
  errors=$((errors + 1))
}

if [[ ! -d "$skills_root" ]]; then
  report_error "missing skills directory: $skills_root"
else
  for skill_path in "$skills_root"/*; do
    [[ -d "$skill_path" ]] || continue
    skill_count=$((skill_count + 1))

    skill_name="$(basename "$skill_path")"
    skill_file="$skill_path/SKILL.md"

    if [[ ! -f "$skill_file" ]]; then
      report_error "$skill_name is missing SKILL.md"
      continue
    fi

    declared_name="$(
      awk '
        NR == 1 && $0 != "---" { exit }
        NR > 1 && $0 == "---" { exit }
        NR > 1 && $1 == "name:" {
          sub(/^name:[[:space:]]*/, "")
          gsub(/^["'"'"']|["'"'"']$/, "")
          print
          exit
        }
      ' "$skill_file"
    )"

    if [[ "$declared_name" != "$skill_name" ]]; then
      report_error "$skill_name declares frontmatter name '$declared_name'"
    fi
  done
fi

if [[ "$skill_count" -eq 0 ]]; then
  report_error "no skill packages found"
fi

while IFS= read -r unwanted_path; do
  report_error "unwanted local artifact: ${unwanted_path#"$repo_root/"}"
done < <(find "$repo_root" -name '.DS_Store' -o -name '*.sqlite' -o -name '*.sqlite-*')

while IFS= read -r shell_file; do
  if ! bash -n "$shell_file"; then
    report_error "invalid shell syntax: ${shell_file#"$repo_root/"}"
  fi
done < <(find "$repo_root" -type f -name '*.sh')

if command -v node >/dev/null 2>&1; then
  while IFS= read -r javascript_file; do
    if ! node --check "$javascript_file" >/dev/null; then
      report_error "invalid JavaScript syntax: ${javascript_file#"$repo_root/"}"
    fi
  done < <(find "$repo_root" -type f \( -name '*.js' -o -name '*.mjs' -o -name '*.cjs' \))
else
  printf 'WARN: node is unavailable; JavaScript syntax checks skipped.\n' >&2
fi

if [[ "$errors" -ne 0 ]]; then
  printf 'Validation failed with %d error(s).\n' "$errors" >&2
  exit 1
fi

printf 'Validated %d skill package(s).\n' "$skill_count"

