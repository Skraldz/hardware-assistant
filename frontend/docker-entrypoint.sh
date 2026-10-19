#!/bin/sh
set -e

# Regenerate config.js from the *current* env on every container start
# (fresh each time, since this runs against the immutable built image) so
# APP_PORT changes in .env take effect on `docker compose up` alone.
sed -i "s/__API_PORT__/${API_PORT:-8000}/" /app/dist/config.js

exec "$@"
