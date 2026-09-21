# Implementation Plan: Reach the network map through public paths only

**Branch**: `002-public-network-map-path` | **Date**: 2026-09-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-public-network-map-path/spec.md`

## Summary

Close the one internal import feature 001 introduced
(`cuemsutils.config.network_map.CuemsNetworkMapType`) by keeping the document
`ConfigManager.load_network_map()` already produces and refilling its `node_list` from the
index before every save and refresh, instead of constructing documents. When no map file
exists at start-up, write the empty map `cuems-common` ships and load it through the same
path (option A), so a document is always available.

Phase 0 ([research.md](research.md)) measured three things that shape this plan:

- **R1** — 04a's design as written fails **28 of 95** tests, because they reach save/refresh
  without start-up. Giving each instance an empty document makes all 95 pass, so the
  test change is setup-only.
- **R3** — was a blocker; **fixed upstream** (`cuems-utils` `e363d03`, inside `0.1.0rc16`) and
  verified here without a monkeypatch. Option A is implementable and needs no nodeconf change.
- **R6** — their answer asks for an **empty-map fixture** here: no fixture in `tests/fixtures/`
  is empty, so nothing exercises the boot path a fresh install takes.

## Technical Context

**Language/Version**: Python 3.11 (`python3 (>= 3.11)` in `debian/control`)

**Primary Dependencies**: `cuemsutils (>= 0.1.0rc16, << 0.1.1~)` — public surface only
(`cuemsutils.tools.*`, `cuemsutils.log`, `cuemsutils.errors`); `python3-zeroconf`, `python3-dbus`,
`python3-systemd`, `avahi-daemon`. **Requires a `cuemsutils` build at `e363d03` or later**; the
version string cannot express that (the fix ships inside `rc16`), so the venv and any packaging
run must be rebuilt from the fixed checkout. Pins do **not** move.

**Storage**: `/etc/cuems/network_map.xml` — an XML document shipped as a conffile by
`cuems-common`, written by this daemon as root, read by engines running as `User=cuems`.

**Testing**: `pytest` via `./run-tests.sh` — the suite (95) plus the vendored yardstick (15),
two separate invocations.

**Target Platform**: Debian bookworm nodes; `cuems-nodeconf.service`, `Type=notify`,
`Restart=on-failure`, `RestartSec=10`, running as **root**.

**Project Type**: single Python package (a systemd daemon), no frontend in this repository.

**Performance Goals**: none specific. The seed write happens once at start-up, inside systemd's
`TimeoutStartSec=60` window, where `run()` already spends up to 35 s before `notify_systemd()`.

**Constraints**: no new internal imports; the RPC response shape is a UI contract; the map must
stay readable by non-root services; the write-only-if-changed gate must be preserved.

**Scale/Scope**: one class touched (`CuemsNodeConf`), 4 call sites, 1 import removed, ~28 test
setup lines, 1 new fixture, 3 new tests.

## Constitution Check

*GATE: checked before Phase 0, re-checked after Phase 1 design.*

| Principle | Gate | Verdict |
|---|---|---|
| **I. Root privilege is correctness** | The seed is a **new filesystem object created by a root process and read by `User=cuems` engines**. Its mode must be decided deliberately, stated, and tested | **PASS with an explicit requirement.** R4 measured `0600` under umask `0077`, so the seed is written and then `chmod 0644` — the mode `cuems-common` installs. Pinned by a test, not left to systemd's default umask |
| **II. The output is a file other services read** | Writes complete or absent; never write when nothing changed | **PASS.** The seed is written atomically (temp file in the same directory, then `os.replace`), so a crash mid-write cannot leave a partial map. The signature gate is untouched: `refresh` still decides, and `_map_write_pending` still owes a retry. Refilling `node_list` wholesale before each use preserves "the index is the single source of truth" |
| **III. Identity is keyed by UUID** | No name-derived identity key | **PASS — not touched.** The seed contains **no nodes**, so it introduces no identity at all. Merge and adoption paths are unchanged |
| **IV. RPC responses are a UI contract** | `{'OK': bool, 'error'?: str}` unchanged; every request answered | **PASS, with verification owed.** `adopt_node`/`unadopt_node` keep their shape; only the document they save through changes. The 28 affected tests include the operator outcome-table tests, which must pass **unmodified in intent**. Real-hardware check recorded as not performed (see quickstart) |
| **V. No eleventh responsibility** | Nothing added beyond the ten | **PASS.** This *narrows* row 5: the daemon stops constructing documents. The seed helper belongs to the same network-map responsibility; it is ~6 lines, not a new concern. The atomization basis stays valid |
| **VI. Boot ordering is product behaviour** | Reason explicitly about ordering and races | **PASS, and it constrains the design.** R2: `set_comms()` runs **before** `run()`, so adopt RPCs can arrive before the map is read. `read_network_map` MUST keep the document **before** installing the populated index, or an RPC in between could adopt a node and save through a missing document. Today's behaviour (empty index → "not found") is preserved |
| **Domain logic lives in `cuemsutils`** | No ad-hoc reimplementation | **PASS.** `refresh`'s orchestration stays in the library; this feature removes a construction, not logic |
| **Public import paths only** | | **This is the feature.** 1 → 0 internal imports in shipped code |
| **Dependency pins are bounded** | Floor + ceiling, both files agreeing | **PASS — unchanged.** `>= 0.1.0rc16, << 0.1.1~` in `debian/control` and `pyproject.toml`. The upstream fix landed inside `rc16`, so nothing moves |
| **Characterization tests are a measurement** | Yardstick run, never edited | **PASS.** The yardstick is untouched and must stay byte-identical to the library's copy — diffed, not assumed |

**Post-Phase-1 re-check**: no new violations. The design adds no module, no dependency and no
responsibility; the only new filesystem behaviour is the seed, which principles I and II govern
and which the plan pins with tests.

## Project Structure

### Documentation (this feature)

```text
specs/002-public-network-map-path/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 — R1..R6, including the upstream blocker and its fix
├── data-model.md        # Phase 1 — the kept document, the index, the seed
├── quickstart.md        # Phase 1 — how to validate this feature
├── contracts/
│   ├── library-surface.md   # what the daemon may import, and how it obtains a document
│   └── empty-map-seed.md    # the bytes, the mode, and the write discipline
├── checklists/
│   └── requirements.md  # spec quality checklist (all items pass)
└── tasks.md             # Phase 2 — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
cuemsnodeconf/
├── CuemsNodeConf.py     # the only shipped file this feature edits:
│                        #   :21  the internal import          -> deleted
│                        #   __init__                          -> self._document = None
│                        #   run()          first-run branch   -> seed, then the normal read
│                        #   read_network_map()                -> keep the document (before the index)
│                        #   _network_map_document()           -> refill and return the kept one
│                        #   _seed_empty_map()                 -> new, ~6 lines
├── CuemsAvahiListener.py, AvahiTool.py, AliasPublisher.py, communicate.py,
└── CuemsConfServer.py, run_nodeconf.py     # untouched

tests/
├── fixtures/etc_cuems/
│   ├── settings.xml, network_map.xml       # existing (populated)
│   └── network_map_empty.xml               # NEW — byte-identical to what cuems-common ships
├── conftest.py                             # cuems_conf_dir fixture gains an empty-map variant
├── test_node_adoption.py, test_adoption_flow.py, test_integration.py,
│   test_engine_callback.py, test_missing_nodes.py, test_network_map.py,
│   test_phase1_changes.py                  # 28 setup lines added; no subject or assertion changes
└── test_fresh_node_boot.py                 # NEW — the empty-map boot path and the seed

specs/planning/yardstick/                   # run, never edited
```

**Structure Decision**: single Python package, unchanged. This feature edits exactly one shipped
module and adds no module, matching FR-024/FR-025's scope rules inherited from feature 001 and
constitution V.

## Design decisions

| | Decision | Why, and what was rejected |
|---|---|---|
| **D1** | `__init__` sets `self._document = None`; `_network_map_document()` refills and returns the kept document, and raises a clear `RuntimeError` if none is loaded | The alternative — lazily loading a document on first use — would read `/etc/cuems` from tests that never asked for it, and needs `settings.xml` beside the map (R1). A clear error beats `AttributeError` |
| **D2** | `read_network_map()` assigns `self._document` **before** `self.network_map` | R2/constitution VI: the IPC thread is live before the map is read |
| **D3** | `run()`: when the map file is absent, seed it, then take the **same** `read_network_map()` path as an existing map | One code path for both cases. The seeded map does not list this node, so the load raises `ValueError`, which feature 001's catch already handles — measured end to end |
| **D4** | `_seed_empty_map()` writes the shipped bytes atomically (temp file in the same directory + `os.replace`), then `chmod 0644`; on failure, log and `sys.exit(-1)` as the other start-up failures do | Constitution I and II. R4: a plain create is `0600` under umask `0077`. R6: a bare `<CuemsNetworkMap/>` root breaks `refresh`/`save` upstream, so the seed must carry `<node_list/>` |
| **D5** | Tests get the document in setup, through the import §4 keeps: one line per affected test | R1 measured this is sufficient (95/95 with an empty document). Subjects and assertions stay untouched, per SC-002 |
| **D6** | Add `network_map_empty.xml` and a fresh-node boot test | R6, asked for by `cuems-utils`; this is the path every fresh install takes and nothing here covers it |

## Complexity Tracking

> No constitution violations. Nothing to justify.

The one judgement call worth recording: **D4 writes a file in order to read it back**, which
04a itself called "a little indirect". It is accepted because it keeps a single load path
(D3), it costs ~6 lines, and the alternative that avoids the write — keeping the internal
import for that branch — is what this feature exists to remove.
