#!/bin/bash
# Launcher for the Command Center. Run:  ./cc   or   ./cc news
cd "$(dirname "$0")" || exit 1
exec python3 command_center.py "$@"
