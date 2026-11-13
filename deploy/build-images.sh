#!/bin/sh
# Build the four images on the Docker host (the stack uses them as local images).
#   SRC=/path/to/sources ./build-images.sh     (default: the folders next to wehub/)
# After building, redeploy the stack (Portainer: Stacks → family → Update) to use the new images.
set -e
SRC="${SRC:-$(cd "$(dirname "$0")/../.." && pwd)}"
build() { # image folder
  if [ ! -f "$SRC/$2/Dockerfile" ]; then echo "Missing $SRC/$2/Dockerfile" >&2; exit 1; fi
  if [ -d "$SRC/$2/.git" ] && [ ! -f "$SRC/$2/backend/famkit/__init__.py" ]; then
    git -C "$SRC/$2" submodule update --init   # famkit, the shared code
  fi
  echo "== $1 ($SRC/$2)"
  docker build -t "$1:latest" "$SRC/$2"
}
build wehub wehub
build dotrack "${DOTRACK_DIR:-dotrack}"
build eatrack "${EATRACK_DIR:-eatrack}"
build patrack "${PATRACK_DIR:-patrack}"
echo "Done. Images: wehub, dotrack, eatrack, patrack (tag latest)."
