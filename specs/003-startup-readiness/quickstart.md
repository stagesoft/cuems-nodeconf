<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Quickstart — validating feature 003

## Prerequisites

```
export PYENV_ROOT=$HOME/.pyenv; export PATH="$PYENV_ROOT/bin:$PATH"; eval "$(pyenv init -)"
# .venv is a 3.11.9 venv with pytest pytest-mock zeroconf and
#   pip install -e ../cuems-utils          # at 73daab6 or later (NodeIndex.ensure)
.venv/bin/python -c "from cuemsutils.tools.NodeList import NodeIndex; assert hasattr(NodeIndex, 'ensure')"
```

If the assertion fails, the library predates `73daab6`; `tests/test_library_prerequisite.py` fails the
same way, on purpose.

## The gates

```
./run-tests.sh                                   # suite, then the yardstick, as two invocations
cmp specs/planning/yardstick/test_nodeindex_characterization.py \
    ../cuems-utils/tests/contract/test_nodeindex_characterization.py && echo yardstick identical
ls *.md                                          # expect exactly: CLAUDE.md README.md
```

Baseline before this feature: 119 passed, yardstick 15 passed.

## The window, by hand

```
.venv/bin/python - <<'PY'
from unittest.mock import MagicMock, patch
import tests.conftest   # stubs dbus, systemd and netifaces, as the suite does on a dev checkout
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
n = CuemsNodeConf(); n.communications_thread = MagicMock()
# respond_to_engine is a MagicMock here, not a coroutine, so the scheduling call is
# patched out — the same pattern tests/test_engine_callback.py uses.
with patch('asyncio.run_coroutine_threadsafe'):
    n.engine_callback({'action': 'nodelist_modify', 'modify_action': 'ADD', 'value': 'any-uuid'}, MagicMock())
print(n.communications_thread.respond_to_engine.call_args[0][0])
PY
```

Expected: `{'OK': False, 'error': 'nodeconf is still starting up'}` — never `Node any-uuid not found`.

## Targeted tests

| What | Command |
|---|---|
| the refusal, the half-built state, the guard | `.venv/bin/python -m pytest tests/test_startup_readiness.py -q` |
| the render, the refusals, the ordering before the socket | `.venv/bin/python -m pytest tests/test_service_record.py -q` |
| the own-row seed | `.venv/bin/python -m pytest tests/test_self_seed.py -q` |
| the configured waits and the pre-flight | `.venv/bin/python -m pytest tests/test_startup_config.py -q` |
| nothing regressed in the operator chain | `.venv/bin/python -m pytest tests/test_engine_callback.py -q` (16, unchanged) |

## On a node (hardware ledger)

Entries §5 and §6 of `specs/002-public-network-map-path/checklists/hardware-verification.md`. In
short:

1. `systemctl unmask cuems-nodeconf.service && systemctl enable --now cuems-nodeconf.service`
2. `journalctl -u cuems-nodeconf -b` — the pre-flight lines, the render line, no `NOT PROVISIONED`
3. `cuems-init-node --check` → exit 0; from another node `avahi-browse -rtp _cuems_nodeconf._tcp`
   lists this host once with the `settings.xml` uuid
4. `systemctl restart cuems-nodeconf` and click "add node" in the UI within a few seconds → the page
   shows *nodeconf is still starting up*; retry after `systemctl status` says active → adopted
5. Reboot; 2–4 hold

Record date, host, node class and the outputs in the ledger, or leave "Not performed" — never blank.

## Release steps (maintainer)

1. Two bullets added to the `0.1.0-8 UNRELEASED` changelog entry; no version bump.
2. Merge the feature branch into `feat/xml-refactor` locally (fast-forward, never pushed as a branch).
3. Re-cut `xml-refactor-merge-candidate` on the merge commit (annotated, signed) and announce it to
   the `cuems-common`, `cuems-power-bridge` and `cuems-utils` flows in one message; 011's T080 records it.
