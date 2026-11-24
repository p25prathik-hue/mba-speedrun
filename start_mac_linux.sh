#!/usr/bin/env bash
# MBA Speedrun - Mac / Linux launcher. Run:  bash start_mac_linux.sh
# First run: makes a private Python environment in .venv and installs the
# requirements (needs internet, about 1-3 minutes). Later runs start at once.
set -e
cd "$(dirname "$0")"

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "Python 3.9 or newer was not found. Install it from https://www.python.org/downloads/ and run this again."
  echo "To use the roadmap planner without Python, open docs/index.html in your browser."
  exit 1
fi

if [ ! -f .venv/speedrun_ready.txt ]; then
  echo "First run: setting up MBA Speedrun (1-3 minutes, needs internet)..."
  [ -x .venv/bin/python ] || "$PY" -m venv .venv
  .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
  echo "Installing numba to make the solver faster (optional)..."
  .venv/bin/python -m pip install --disable-pip-version-check -q numba >/dev/null 2>&1 \
    || echo "numba could not be installed. That is fine: the tool uses its numpy solver instead."
  echo ready > .venv/speedrun_ready.txt
  echo "Setup finished."
fi

exec .venv/bin/python start.py "$@"
