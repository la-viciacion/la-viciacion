#!/bin/sh
# Runs the deploy script on the server over SSH. Usage: deploy.sh dev|prod
# Leaves deploy-result.env (RESULT=success|failure, and TAG for prod) for the notify job, whatever happens.
set -eu
target=$1
result=deploy-result.env

echo "RESULT=failure" > "$result"
trap 'echo "TARGET=$target" >> "$result"' EXIT

# The *_SSH_KEY variables are of type File: the variable holds the path of a temporary file.
case $target in
  dev) key_file=$DEPLOY_SSH_KEY_DEV ;;
  prod) key_file=$DEPLOY_SSH_KEY_PROD ;;
  *) echo "ERROR: unknown target"; exit 1 ;;
esac

if [ "$target" = prod ]; then
  tag=$(sh .gitlab/scripts/verify-release.sh)
  echo "TAG=$tag" >> "$result"
fi

install -m 700 -d ~/.ssh
install -m 600 "$key_file" ~/.ssh/deploy_key
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > ~/.ssh/known_hosts

if [ "$target" = prod ]; then
  # The version is the only thing the client sends; the server checks it against a strict pattern.
  ssh -T -i ~/.ssh/deploy_key \
    -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
    "$DEPLOY_USER@$DEPLOY_HOST" "$DEPLOY_VERSION"
else
  # No command is passed: the server runs deploy.sh whatever the client asks for.
  ssh -T -i ~/.ssh/deploy_key \
    -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
    "$DEPLOY_USER@$DEPLOY_HOST"
fi

sed -i 's/^RESULT=.*/RESULT=success/' "$result"
