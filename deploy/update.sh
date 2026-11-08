#!/usr/bin/env bash
# Brings the server up to the latest version on GitHub. Run from anywhere:
#   bash /opt/autoline/deploy/update.sh          # a server of its own
#   bash /root/autoline/deploy/update.sh edge    # beside another system (deploy/edge)
#
# The data is in /srv/autoline, outside the code, so nothing here touches it. A backup is
# still worth taking from Settings before a large update.
set -euo pipefail

cd "$(dirname "$0")/.."
git pull --ff-only
cd "deploy/${1:-}"
docker compose up -d --build
# No `docker image prune`: it acts on the whole server, and the server may hold another
# system whose images are not this script's to remove. Old images of this project can be
# cleared by hand: docker image ls autoline-*
docker compose ps
