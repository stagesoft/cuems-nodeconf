#!/bin/bash
# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
#
# run-tests.sh — the repository's test entry point (feature 001, T048).
#
# There is no CI in this repository: no .github/workflows, no GitLab, Drone or
# Jenkins configuration. T048 asked for the yardstick to be added to "this
# repository's CI"; there is none to add it to, so this script is the thing a CI
# job would call, and the thing a developer calls by hand until one exists.
#
# TWO INVOCATIONS, DELIBERATELY SEPARATE (research D-H):
#
#   1. pytest                      — this repository's own suite (testpaths = tests).
#   2. pytest specs/planning/yardstick/  — feature 001's equivalence gate.
#
# The yardstick is NOT in pyproject.toml's testpaths and must not be. It is
# cuems-utils' file, vendored here and run unmodified; keeping it a separate
# invocation keeps its provenance visible and stops it being mistaken for a local
# test that may be edited. If it ever fails, the port is wrong — fix the port, or
# fix the test in cuems-utils and re-vendor it. Editing it here destroys the
# guarantee it exists to provide.
#
# The packaging demonstration (tests/packaging/release-gate-demo.sh) is NOT run
# here: it builds .debs in throwaway chroots, needs network and takes minutes.
# Run it directly when the packaging relationships change.
#
# Usage:  ./run-tests.sh [extra pytest args...]
# Exit:   0 only if both invocations pass.

set -uo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
    if [ -x .venv/bin/python ]; then PYTHON=.venv/bin/python; else PYTHON=python3; fi
fi

status=0

echo "=== 1/2  suite ==============================================="
"$PYTHON" -m pytest -q "$@" || status=1

echo
echo "=== 2/2  yardstick (feature 001's equivalence gate) =========="
echo "    specs/planning/yardstick/ — vendored from cuems-utils; run, never edited."
"$PYTHON" -m pytest specs/planning/yardstick/ -q "$@" || status=1

echo
if [ "$status" -eq 0 ]; then
    echo "both green"
else
    echo "FAILED — see above"
fi
exit "$status"
