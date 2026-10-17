#!/bin/sh
# The image holds no secrets, data or configuration files. Usage: image-checks.sh <image>
set -eu
image=$1

# files that must never end up in an image. Only the directories that exist in that image
# are searched (the api and bot have /app, the front has the web root): find exits 1 for a
# missing path, which under `set -e` would end this script silently.
found=$(docker run --rm --entrypoint sh "$image" -c \
  'for dir in /app /usr/share/nginx/html; do
     [ -d "$dir" ] && find "$dir" \( -name ".env" -o -name ".env.*" -o -name "*.sql" -o -name "*.sql.gz" -o -name "*.dump" \)
   done; true')
if [ -n "$found" ]; then
  echo "ERROR: sensitive files inside the image:"; echo "$found"; exit 1
fi

# variables baked in with ENV/ARG: nothing that looks like a credential (GPG_KEY is the
# public key id of the official python image)
baked=$(docker image inspect "$image" --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | cut -d= -f1 | grep -i -E 'PASS|SECRET|TOKEN|KEY' | grep -v -x GPG_KEY || true)
if [ -n "$baked" ]; then
  echo "ERROR: credential-looking variables baked into the image:"; echo "$baked"; exit 1
fi
echo "clean"
