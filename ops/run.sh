#!/usr/bin/env bash
cd /opt/cron-macroeconomic
set -a; . ./config.env; set +a
exec /opt/cron-macroeconomic/.venv/bin/python "$@"
