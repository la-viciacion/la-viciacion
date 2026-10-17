#!/bin/sh
# Works out which checks a merge request needs and writes the child pipeline that runs them (child.yml).
# The rules are .github/scripts/ci_scope.py, read from the merge base so the MR cannot change the rules that judge
# it. Anything that goes wrong in here must end in "run everything", never in "run nothing".
set -u

everything() {
  scope=all
  services='["api","front","bot"]'
}

scope_of() {
  base=${CI_MERGE_REQUEST_DIFF_BASE_SHA:-}
  [ -n "$base" ] || return 1
  # --no-renames lists a renamed file at both ends
  files=$(git diff --name-only --no-renames "$base" "$CI_COMMIT_SHA") || return 1
  git show "$base:.github/scripts/ci_scope.py" > /tmp/ci_scope.py 2>/dev/null || return 1
  answer=$(printf '%s\n' "$files" | python3 /tmp/ci_scope.py) || return 1
  scope=$(printf '%s\n' "$answer" | sed -n 's/^scope=//p')
  services=$(printf '%s\n' "$answer" | sed -n 's/^build_services=//p')
  [ -n "$scope" ] && [ -n "$services" ]
}

if ! scope_of; then
  echo "WARNING: could not work out what the MR changes (or the base has no ci_scope.py yet); running every check"
  everything
fi

{
  echo "include:"
  echo "  - local: .gitlab/ci/checks.yml"
  echo "variables:"
  echo "  SCOPE: \"$scope\""
  echo "  BUILD_SERVICES: '$services'"
} > child.yml
cat child.yml
