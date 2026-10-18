#!/bin/sh
# The MariaDB image docker-compose.yml pins, handed to the tests as MARIADB_IMAGE (a dotenv report).
set -eu

image=$(sed -n 's/^ *image: *\(mariadb:[^ ]*\) *$/\1/p' docker-compose.yml)
if [ -z "$image" ] || [ "$(printf '%s\n' "$image" | wc -l)" != 1 ]; then
  echo "ERROR: docker-compose.yml must name exactly one mariadb image, with an explicit tag"
  exit 1
fi
echo "MARIADB_IMAGE=$image" > mariadb-image.env
cat mariadb-image.env
