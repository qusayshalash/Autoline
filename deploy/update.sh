#!/usr/bin/env bash
# Brings the server up to the latest version on GitHub. Run from anywhere:
#   bash /opt/autoline/deploy/update.sh
#
# The data is in /srv/autoline, outside the code, so nothing here touches it. A backup is
# still worth taking from Settings before a large update.
set -euo pipefail

cd "$(dirname "$0")/.."
git pull --ff-only
cd deploy
docker compose up -d --build
docker image prune -f >/dev/null
docker compose ps
