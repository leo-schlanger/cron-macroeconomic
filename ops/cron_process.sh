#!/usr/bin/env bash
# Curadoria: só as notícias de maior impacto (ver curator.py). flock impede
# duas rodadas ao mesmo tempo se uma demorar mais que o intervalo do cron.
exec flock -n /tmp/cron-macro-process.lock /opt/cron-macroeconomic/run.sh curator.py run
