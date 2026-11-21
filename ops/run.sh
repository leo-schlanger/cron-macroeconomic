#!/usr/bin/env bash
# Healthcheck URL comes from the cron line, read before config.env so each job keeps its own
HC_URL="${HEALTHCHECK_URL:-}"
cd /opt/cron-macroeconomic
set -a; . ./config.env; set +a
/opt/cron-macroeconomic/.venv/bin/python "$@" || exit $?
# Optional ping for monitoring (empty = no-op); only on success
if [ -n "$HC_URL" ]; then curl -fsS -m 10 --retry 3 -o /dev/null "$HC_URL" || true; fi
