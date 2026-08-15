#!/usr/bin/env bash
#
# publish-docs.sh — one-direction sync of public docs content from
# Fiestaboard/FiestaBoard into the site repo (Fiestaboard/fiestaboard.github.io).
#
# Allowlist (never whole-tree). Each mapped subtree in the target is made
# byte-identical to the source (deletions and renames mirror):
#
#   docs/**  (EXCLUDING docs/internal/**)  ->  docs/**
#   plugin-registry.json                   ->  data/plugin-registry.json
#   plugin-previews.json                   ->  data/plugin-previews.json
#   assets/branding/**                     ->  static/img/branding/**
#   fiestapi-latest-version.txt            ->  data/fiestapi-latest-version.txt
#                                              (only with --with-fiestapi-version)
#
# Also writes docs/.source-sha in the target containing the FiestaBoard
# commit SHA the sync was taken from.
#
# Environment:
#   SYNC_REPO_URL       target repo URL (default: the real site repo). May be a
#                       local path for rehearsals.
#   SYNC_TARGET_BRANCH  target branch (default: sync-test)
#   RELEASE_PAT/GH_TOKEN  token used to clone/push the target repo over HTTPS
#                       (ignored when SYNC_REPO_URL is overridden explicitly)
#
# Exits 0 with NO commit when nothing (other than the source SHA marker)
# changed — no empty-commit churn.
#
# Usage (from the FiestaBoard repo root or anywhere inside it):
#   scripts/publish-docs.sh [--with-fiestapi-version]

set -euo pipefail

WITH_FIESTAPI_VERSION=0
for arg in "$@"; do
  case "$arg" in
    --with-fiestapi-version) WITH_FIESTAPI_VERSION=1 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "error: unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

# --- locate source repo root ------------------------------------------------
SRC_ROOT="$(git rev-parse --show-toplevel)"
cd "$SRC_ROOT"
SRC_SHA="$(git rev-parse HEAD)"

COMMIT_NAME="FiestaBoard CI"
COMMIT_EMAIL="ci@fiestaboard.app"
TARGET_BRANCH="${SYNC_TARGET_BRANCH:-sync-test}"

# --- resolve target repo URL (with token auth for the real repo) ------------
DEFAULT_REPO="github.com/Fiestaboard/fiestaboard.github.io.git"
if [ -n "${SYNC_REPO_URL:-}" ]; then
  REPO_URL="$SYNC_REPO_URL"
else
  TOKEN="${RELEASE_PAT:-${GH_TOKEN:-}}"
  if [ -n "$TOKEN" ]; then
    REPO_URL="https://x-access-token:${TOKEN}@${DEFAULT_REPO}"
  else
    REPO_URL="https://${DEFAULT_REPO}"
  fi
fi

# --- clone target -----------------------------------------------------------
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/publish-docs.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
TARGET_DIR="$WORK_DIR/site"

echo "==> cloning target repo (branch: $TARGET_BRANCH)"
git clone --quiet "$REPO_URL" "$TARGET_DIR"
if git -C "$TARGET_DIR" ls-remote --exit-code --heads origin "$TARGET_BRANCH" >/dev/null 2>&1; then
  git -C "$TARGET_DIR" checkout --quiet "$TARGET_BRANCH"
else
  echo "==> branch $TARGET_BRANCH does not exist on target; creating it"
  git -C "$TARGET_DIR" checkout --quiet -b "$TARGET_BRANCH"
fi

# --- mirror one directory subtree (rsync --delete semantics) ----------------
# mirror_dir <src-dir> <dst-dir> [extra rsync args...]
# If the source dir is absent, the target subtree is removed (true mirror).
mirror_dir() {
  local src="$1" dst="$2"
  shift 2
  if [ -d "$src" ]; then
    mkdir -p "$dst"
    # --checksum: size+mtime quick-check can miss same-size edits when both writes land in the same whole second (mtime granularity)
    rsync -a --checksum --delete "$@" "$src/" "$dst/"
  elif [ -d "$dst" ]; then
    echo "==> source $src absent; removing target subtree $dst"
    rm -rf "$dst"
  fi
}

# copy_file <src-file> <dst-file> — required source file
copy_file() {
  local src="$1" dst="$2"
  if [ ! -f "$src" ]; then
    echo "error: expected source file missing: $src" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
}

echo "==> syncing allowlisted content"
# docs/** minus docs/internal/**. Excluded paths are protected from --delete,
# so .source-sha (rewritten below) and any stray target-side internal/ are
# never copied; internal/ is additionally purged in case it ever leaked.
mirror_dir "$SRC_ROOT/docs" "$TARGET_DIR/docs" \
  --exclude='/internal/' --exclude='/.source-sha'
rm -rf "$TARGET_DIR/docs/internal"

copy_file "$SRC_ROOT/plugin-registry.json" "$TARGET_DIR/data/plugin-registry.json"
copy_file "$SRC_ROOT/plugin-previews.json" "$TARGET_DIR/data/plugin-previews.json"

mirror_dir "$SRC_ROOT/assets/branding" "$TARGET_DIR/static/img/branding"

if [ "$WITH_FIESTAPI_VERSION" -eq 1 ]; then
  copy_file "$SRC_ROOT/fiestapi-latest-version.txt" \
    "$TARGET_DIR/data/fiestapi-latest-version.txt"
fi

mkdir -p "$TARGET_DIR/docs"
printf '%s\n' "$SRC_SHA" > "$TARGET_DIR/docs/.source-sha"

# --- commit + push (skip when only the SHA marker changed) ------------------
cd "$TARGET_DIR"
# Stage only the allowlisted target areas (git add errors on pathspecs that
# match nothing, so only pass paths that exist in worktree or index).
ADD_PATHS=()
for p in docs data static/img/branding; do
  if [ -e "$p" ] || git ls-files --error-unmatch -- "$p" >/dev/null 2>&1; then
    ADD_PATHS+=("$p")
  fi
done
git add -A -- "${ADD_PATHS[@]}"

if git diff --cached --quiet -- . ':(exclude)docs/.source-sha'; then
  echo "==> no content changes; skipping commit"
  exit 0
fi

git -c user.name="$COMMIT_NAME" -c user.email="$COMMIT_EMAIL" \
  commit --quiet -m "docs: sync from Fiestaboard/FiestaBoard@${SRC_SHA}"
echo "==> pushing to $TARGET_BRANCH"
git push --quiet origin "HEAD:$TARGET_BRANCH"
echo "==> done: synced Fiestaboard/FiestaBoard@${SRC_SHA}"
