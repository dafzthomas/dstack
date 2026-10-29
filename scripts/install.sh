#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_root="$repo_root/skills"
target_root="${CODEX_SKILLS_DIR:-$HOME/.codex/skills}"

mkdir -p "$target_root"

installed=0
for skill_path in "$source_root"/*; do
  [[ -d "$skill_path" ]] || continue

  skill_name="$(basename "$skill_path")"
  target_path="$target_root/$skill_name"

  if [[ -L "$target_path" ]] && [[ "$(readlink "$target_path")" == "$skill_path" ]]; then
    printf 'Already installed: %s\n' "$skill_name"
    continue
  fi

  if [[ -e "$target_path" || -L "$target_path" ]]; then
    printf 'Refusing to replace existing path: %s\n' "$target_path" >&2
    printf 'Move or remove it explicitly, then run this installer again.\n' >&2
    exit 1
  fi

  ln -s "$skill_path" "$target_path"
  printf 'Installed: %s -> %s\n' "$skill_name" "$skill_path"
  installed=$((installed + 1))
done

printf 'Installation complete: %d new skill(s).\n' "$installed"

