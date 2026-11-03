#!/bin/bash
# Daily entry point (launchd: com.daraz.pipeline). Keeps the Mac awake for the run; all detail
# goes to logs/<date>/ and runs/<date>.json, this file only to logs/pipeline.log.
cd "$(dirname "$0")"
mkdir -p logs
caffeinate -is .venv/bin/python -m pipeline.run "$@" >> logs/pipeline.log 2>&1
