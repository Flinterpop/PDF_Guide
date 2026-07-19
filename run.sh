#!/usr/bin/env bash
#
# PDF Sherpa launcher for Linux / macOS.
#
# On first run it creates a local virtual environment (.venv) beside this
# script and installs the dependencies from requirements.txt.  Every run after
# that just launches the app.  Pass a folder to open it directly:
#
#     ./run.sh                 # last-used folder (or ./pdfs)
#     ./run.sh ~/Documents     # open a specific folder
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"
PY="$VENV/bin/python"

# Pick a system Python 3 to build the venv from.
BOOT_PY="$(command -v python3 || command -v python || true)"
if [[ -z "$BOOT_PY" ]]; then
    echo "Error: python3 is not installed." >&2
    exit 1
fi

# Tkinter ships separately from Python on many distros -- check it up front so
# the failure is a clear message rather than an ImportError at launch.
if ! "$BOOT_PY" -c 'import tkinter' >/dev/null 2>&1; then
    echo "Error: Python's tkinter module is missing." >&2
    echo "  Debian/Ubuntu : sudo apt install python3-tk" >&2
    echo "  Fedora        : sudo dnf install python3-tkinter" >&2
    echo "  Arch          : sudo pacman -S tk" >&2
    exit 1
fi

# Create the virtual environment on first run (or if it was deleted).
if [[ ! -x "$PY" ]]; then
    echo "First run: creating virtual environment in .venv ..."
    "$BOOT_PY" -m venv "$VENV"
    "$PY" -m pip install --upgrade pip >/dev/null
    echo "Installing dependencies (PyMuPDF, Pillow) ..."
    "$PY" -m pip install -r "$HERE/requirements.txt"
fi

exec "$PY" "$HERE/app.py" "$@"
