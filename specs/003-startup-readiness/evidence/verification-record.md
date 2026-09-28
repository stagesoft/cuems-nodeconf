<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Verification record — feature 003 (T046)

**Recorded 2026-09-28**, baseline `2ca7474` (119 + 15 green before any edit; `cuems-utils` `73daab6`
installed editable). The constitution requires a change touching discovery, the identity chain or
boot ordering to "state how it was verified on real hardware, or state plainly that it was not. Both
are acceptable answers; silence is not." This is that statement. Quote it in the PR description.

## Verified, by something that ran

| What | How | Result |
|---|---|---|
| The suite | `./run-tests.sh` (1/2) | **173 passed** (119 baseline + 54 added), `pytest -rs` shows **no skips** |
| The equivalence gate (FR-019, SC-003) | `./run-tests.sh` (2/2) | **15 passed** |
| Yardstick untouched (FR-019) | `cmp` against `../cuems-utils/tests/contract/test_nodeindex_characterization.py` | **identical** — compared, not assumed; `73daab6` did not touch it either |
| The window is exercised, not inspected (FR-001..FR-003, FR-006, SC-001, SC-002) | `tests/test_startup_readiness.py` — 15 tests | a request before the load, and one **between** the document and the index, gets `nodeconf is still starting up`; unknown/missing/non-dict requests answer as before; after the load the pre-feature answers return; a load that raises leaves the daemon not ready; readiness never reverts |
| Nothing pre-existing changed in subject or assertion (FR-004, SC-002) | `git diff 2ca7474 -- tests/test_engine_callback.py tests/test_adoption_flow.py tests/test_service_discovery.py tests/test_node_role.py tests/test_integration.py` | **8** `_ready = True` setup lines (6 + 2), **1** `settings_uuid` setup line, **3** `patch('shutil.copy2')` retargeted to the render helper, one obsolete comment removed. No `assert` line and no test body changed; the 16 engine-callback tests pass |
| The render (FR-010, FR-012, SC-005) | `tests/test_service_record.py` — 22 tests | template with both sentinels replaced; mode **0644** under umask `0077`; atomic, nothing left behind; unchanged bytes → no write, no reload; a role change rewrites and reloads once; templates read from `TEMPLATES_PATH`; a failed reload is logged, not fatal |
| The refusals (FR-011, SC-004) | same file, `TestUnprovisionedRefusesToStart` | absent, unreadable (patched `PermissionError`, no skip), invalid (`SchemaError`), sentinel uuid, sentinel MAC: each exits non-zero, **`set_comms` not called**, no record written, the critical line starts with `NOT PROVISIONED`; a provisioned node starts |
| Ordering before the socket (contract startup-order.md) | same file, `TestRenderHappensBeforeTheSocket`; `tests/test_startup_config.py::TestPreflight::test_preflight_runs_before_identity_and_socket` | `['render', 'set_comms']`; `['preflight', 'identity', 'render', 'set_comms']` |
| The start-up render keeps the live role | same file, `TestStartupRenderKeepsTheLiveRole` | controller → controller, node → node, absent → firstrun, garbage → firstrun |
| The self guard (FR-013) | `tests/test_startup_readiness.py::TestSelfGuard` | a stale uuid at our IP is waited out and warned about naming both uuids; on timeout the error names both and says `restart cuems-nodeconf` |
| The own row through the library (FR-015, FR-016) | `tests/test_self_seed.py` — 5 tests; `tests/test_library_prerequisite.py` — 1 added | inserted by reference, keyed by the settings MAC; a later role change is visible through the row; the first merge refreshes it in place with no duplicate; a listed node is left alone and `_map_write_pending` untouched; `run()` seeds after the self lookup and before the role decision |
| Configured waits and pre-flight (FR-023, FR-024, SC-011) | `tests/test_startup_config.py` — 11 tests | defaults 10 and 5; environment overrides; garbage falls back with a warning naming the variable; `get_ips` passes the configured timeout; an unreachable bus or silent avahi is named at ERROR and never fatal |
| Consumers do not compensate (FR-008, FR-009) | research R14 | engine at `cf5c4ad`: one probe, one timeout, no retry, no string read; editor: no reference |
| Root-level documents (FR-017, SC-007) | `ls *.md` | `CLAUDE.md README.md`; the analysis at `specs/planning/11-startup-analysis.md` with a dated status per finding; three deleted, reason in the commit |
| One shipped file touched (constitution V) | `git diff --stat 2ca7474 -- cuemsnodeconf/` | `CuemsNodeConf.py` only; `grep -c shutil.copy2` → **1** (the interfaces copy) |
| The quickstart's window-by-hand | `specs/003-startup-readiness/quickstart.md` | prints `{'OK': False, 'error': 'nodeconf is still starting up'}` (the snippet gained the conftest stubs import; corrected in place per T045) |
| Package version unchanged (FR-021) | `dpkg-parsechangelog -S Version` | `0.1.0-8`, two bullets added to the `UNRELEASED` entry |

## NOT verified — no hardware was involved

**Recorded, not silent.** Two entries in the shared ledger
**[`specs/002-public-network-map-path/checklists/hardware-verification.md`](../../002-public-network-map-path/checklists/hardware-verification.md)**:

- **§5** — unmask, enable and start the daemon on every node; `cuems-init-node --check` exit 0; a
  second node sees this one exactly once with the `settings.xml` uuid; after a reboot. **Not performed.**
- **§6** — the start-up refusal on the real dispatch path (constitution IV): restart the daemon on a
  controller, click "add node" within seconds, expect *nodeconf is still starting up* on the settings
  page, never *Node not found*. **Not performed.**

What was done instead, and its limit: every path was exercised in temporary directories on a
development checkout with `dbus`, `systemd` and `netifaces` stubbed. That is evidence for the code
paths, not for a node; nothing here proves avahi serves the rendered record or that the operator's
button shows the string.

## Constitution check, re-affirmed after implementation

Unchanged from [plan.md](../plan.md): I (record `0644`, pinned under umask `0077`), II (record written
only on change, atomically; the map's write path untouched), III (self matched by uuid; the seeded row
keyed by the provisioned MAC), IV (shape unchanged; end-to-end owed in ledger §6), V (one file, no new
responsibility; three template copies became one helper), VI (the order is a contract with the answer
at every step; the guard waits out a stale record; the pre-flight never exits). No complexity to justify.

## Noted in passing, not acted on

- The `cuems-common` checkout at `3af31cc` already carries the sentinel in its **node** and
  **firstrun** templates but still the production uuid in **controller**; on such a host the render
  refuses for a controller until the 011 handover lands there. The package `Breaks` and the
  coordinated re-cut are what make both sides true at once.
- `/tmp/nodeconf.ipc` survives a daemon that exits during start-up; the engine's existence probe then
  sees a socket with nobody listening. Pre-existing, engine-side, recorded in the readiness contract.
- The constitution's testing gate still reads "16 test files, currently 81 tests" against a suite of
  173 in 24 files. Governance text changes by its own explicit update, not as a side effect of a feature.
