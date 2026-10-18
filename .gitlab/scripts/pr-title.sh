#!/bin/sh
# Merge requests are squash-merged, so the title becomes the commit message on main.
title=${CI_MERGE_REQUEST_TITLE#Draft: }

if ! printf '%s' "$title" | grep -E -q '^(feat|fix|refactor|docs|style|test|chore|perf|build|ci|revert)(\([a-z0-9._-]+\))?!?: .+'; then
  echo "ERROR: The MR title must look like 'feat(front): add X' (types: feat, fix, refactor, docs, style, test, chore, perf, build, ci, revert)"
  exit 1
fi
