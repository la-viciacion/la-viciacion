#!/bin/sh
# The prod deploy only accepts a release whose pipeline passed every check. The server builds the tag itself, so
# nothing else would notice a release whose checks failed (or never ran). Prints the tag on stdout.
#
# Reading the pipelines of the project needs a token: the job token is tried unless GITLAB_READ_TOKEN (a project
# access token with the read_api scope, Protected) is set. See docs/desarrollo/gitlab.md.
set -eu

fail() { echo "ERROR: $*" >&2; exit 1; }

version=$DEPLOY_VERSION
printf '%s' "$version" | grep -E -q '^(latest|[0-9]+\.[0-9]+\.[0-9]+)$' || fail "version must be 'latest' or X.Y.Z"

git fetch --tags --quiet origin >&2 || fail "could not fetch the tags"
if [ "$version" = latest ]; then
  tag=$(git tag --list 'v[0-9]*.[0-9]*.[0-9]*' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1 || true)
else
  tag="v$version"
fi
[ -n "$tag" ] || fail "there is no release tag"
sha=$(git rev-list -n 1 "refs/tags/$tag" 2>/dev/null) || fail "the tag $tag does not exist"

if [ -n "${GITLAB_READ_TOKEN:-}" ]; then
  auth="PRIVATE-TOKEN: $GITLAB_READ_TOKEN"
else
  auth="JOB-TOKEN: $CI_JOB_TOKEN"
fi
passed=$(curl -fsS --header "$auth" \
  "$CI_API_V4_URL/projects/$CI_PROJECT_ID/pipelines?ref=$tag&sha=$sha&status=success&per_page=1" | jq length) \
  || fail "could not read the pipelines of the project (is GITLAB_READ_TOKEN needed?)"
[ "$passed" != 0 ] || fail "$tag has no passing release pipeline on its commit ($sha). Wait for it, or run a pipeline by hand on the tag."

echo "$tag passed every check ($sha)" >&2
echo "$tag"
