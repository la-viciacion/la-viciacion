#!/bin/sh
# Builds and pushes one image ($SERVICE) of the tag being released to the project's registry:
# X.Y.Z always, and X.Y and latest unless the tag is a prerelease (vX.Y.Z-rc1).
set -eu

version=${CI_COMMIT_TAG#v}
image="$CI_REGISTRY_IMAGE/laviciacion-$SERVICE"

printf '%s' "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin "$CI_REGISTRY"

set -- -t "$image:$version"
case $version in
  *-*) ;;
  *) set -- "$@" -t "$image:${version%.*}" -t "$image:latest" ;;
esac

docker build \
  --build-arg "APP_VERSION=$version" \
  --label "org.opencontainers.image.source=$CI_PROJECT_URL" \
  --label "org.opencontainers.image.version=$version" \
  --label "org.opencontainers.image.revision=$CI_COMMIT_SHA" \
  "$@" "$SERVICE"

docker push --all-tags "$image"
