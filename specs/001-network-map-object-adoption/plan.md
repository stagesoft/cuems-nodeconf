# Implementation Plan: Network-map object adoption and the Avahi vocabulary cutover

**Branch**: `feat/xml-refactor` (spec directory `001-network-map-object-adoption`; this repository does not branch per feature) | **Date**: 2026-09-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-network-map-object-adoption/spec.md`

## Summary

Replace this daemon's ad hoc network-map logic with `cuemsutils`' network-map object,
rename its half of the Avahi discovery vocabulary in lockstep with `cuems-common`, and
settle the correctness debts that share `CuemsNodeConf.__init__` with the swap.

The technical approach is set by one measured fact that neither planning document
records: **`CuemsNetworkMapType.refresh` rebuilds its `NodeIndex` from `self["node_list"]`
on every call and writes the result back**, while `adopt`/`unadopt` are `NodeIndex`
methods that neither persist nor exist on the document object. There is no public
`NodeIndex` accessor on either class. So the daemon must hold the **document** as its
single source of truth and derive an index at each mutation — not the reverse. Holding a
long-lived `NodeIndex` (what the daemon does today) would have `refresh` silently discard
every operator adoption.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `cuemsutils >= 0.1.0rc16` (measured present: `0.1.0rc16` at
`cuems-utils@d0340fc`), `zeroconf`, `netifaces`, `dbus-python`, `systemd-python`, `pynng`

**Storage**: `/etc/cuems/network_map.xml`, validated against `network_map.xsd`; the
`master.lock` marker file; the `/tmp/nodeconf.ipc` engine socket

**Testing**: `pytest` — 16 files under `tests/`, 80 tests, all passing at plan time. The
vendored yardstick at `specs/planning/yardstick/` runs separately and passes (15).

**Target Platform**: Debian bookworm nodes; `systemd` unit `cuems-nodeconf.service`
(`Type=notify`, `NotifyAccess=main`, `TimeoutStartSec=60`, `PartOf=cuems-node.target`),
running as **root**

**Project Type**: single Python package shipped as a `.deb` via `dh-virtualenv`

**Performance Goals**: not throughput-bound. The binding constraint is the 60 s systemd
start budget, of which `run()` already commits up to ~35 s before `READY`.

**Constraints**: no half-renamed discovery vocabulary may ship; the RPC response shape is
fixed by a live Angular component; writes to `network_map.xml` must stay
write-only-on-change; nothing releases before the sibling flows land.

**Scale/Scope**: a handful of nodes per cluster; one file, ~790 lines, of which this
feature removes nine methods and adds an adapter.

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1. Result: **PASS**, no
unjustified violations.*

| Principle | Bearing on this feature | How it is satisfied |
|---|---|---|
| **I. Root privilege is correctness** | The feature touches the write path of a file the engine reads, and `__init__`, where the IPC socket's permissions are set | No change to socket creation or its `chmod`. The map write moves inside `refresh`/`save`, which writes atomically; ownership and mode of `network_map.xml` are unchanged. Verified by inspection — **T052 is that inspection**, not a promise of one. |
| **II. The output is a file other services read** | Directly. `refresh` now owns the write decision | FR-002 keeps write-only-on-change: `refresh` compares `signature()` before and after and returns whether it wrote. `<online>` semantics are unchanged — still a discovery-pass snapshot, still written only here. Adopt/unadopt must persist explicitly (see Research D-D); losing that would leave an operator's change in memory only. |
| **III. Identity is keyed by UUID** | Directly | `NodeIndex.merge` matches on `uuid` and never clobbers the real key with the discovered one — this is the library's ported form of the duplicate-node fix, and the yardstick pins it. The error-string reconstruction (D-B) also looks up by `uuid`, never by name or MAC. |
| **IV. RPC responses are a contract** | This is the feature's highest-risk surface | FR-009/010/011. The ported methods return a two-way-ambiguous bool, so the daemon re-runs the discriminating check to pick the right string (D-B). SC-003 requires the real dispatch path exercised, not just unit tests. |
| **V. One class doing ten things — no eleventh** | The feature removes row 5 | Nothing else is restructured. The adapter that derives a `NodeIndex` from the document is row 5 *shrinking to a seam*, not a new responsibility: it holds no state of its own and disappears entirely if the library ever exposes an index accessor. `check_first_run()` (row 3, dead) is deliberately left alone. |
| **VI. Shutdown and boot ordering** | `__init__` and `run()` are both touched | Nothing is added to the pre-`READY` phase: the map load already happens at `:176-181` and stays there. `cleanup()` is **deleted** rather than fixed precisely because fixing it would make `/etc/cuems/settings.xml` a construction-time requirement of the daemon (D-C). |
| **Operating constraint — public paths** | FR-013 | Measured: `ConfigManager.load_network_map()` + `.network_map` returns a `CuemsNetworkMapType` **equal in result** to the internal reader (Research D-G). The other two internal names have no call site and are deleted. |
| **Operating constraint — bounded pins** | FR-021/022 | Both metadata files move to the same floor and gain an upper bound, matching the `Breaks:` pattern `cuems-common` already uses. |
| **Operating constraint — atomic wire changes** | FR-019 | The Avahi half is developed here but merges simultaneously with flow 03. Sequencing below. |
| **Testing gate** | SC-001/003/005/006 | The suite must stay green with nothing skipped. **The suite cannot satisfy SC-003 or SC-006** — Avahi behaviour here is characterized against mocks. The manual procedure is written out in `quickstart.md` rather than left implicit, which is what the gate requires. |

**Complexity Tracking**: not required — no violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/001-network-map-object-adoption/
├── plan.md              # This file
├── spec.md              # The specification
├── research.md          # Phase 0 — the eight decisions this plan rests on
├── data-model.md        # Phase 1 — entities and where their state lives
├── quickstart.md        # Phase 1 — how each success criterion is actually verified
├── contracts/
│   ├── engine-rpc.md    # The nodelist_modify request/response contract
│   └── avahi-txt.md     # The discovery TXT-record contract, both halves
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # Phase 2 — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
cuemsnodeconf/
├── CuemsNodeConf.py        # row 5's nine methods; engine_callback; cleanup;
│                           #   imports; the Avahi template installer
├── CuemsAvahiListener.py   # the TXT consumer and its stale comments
├── CuemsSettings.py        # the TXT publisher
├── AvahiTool.py            # a stale comment
├── communicate.py          # unchanged
└── run_nodeconf.py         # unchanged

tests/                      # 16 files; fixtures for the listener and the
                            #   vocabulary need updating with the rename

specs/planning/yardstick/    # the equivalence gate — READ-ONLY, run not edited

cuems.service.firstrun       # DELETED — unshipped duplicates of the files
cuems.service.master         #   cuems-common installs at /usr/share/cuems/
cuems.service.slave          #
test_run_nodeconfig.py       # non-shipped dev script; updated with the rename

pyproject.toml               # cuemsutils floor + upper bound
debian/control               # same constraint, expressed for dpkg
debian/changelog             # 0.1.0-8
CLAUDE.md                    # the network-plumbing correction
```

**Structure Decision**: single flat package, unchanged. This feature adds no module and
no directory; it removes nine methods, three files and two imports. The atomization that
*would* add modules is explicitly out of scope (FR-024), so the layout above is the
existing one with deletions marked.

### Per-file scope

Measured against `feat/xml-refactor` at plan time (`CuemsNodeConf.py` = 792 lines,
**after** the first-run deletion). Re-measure before use.

| File | What changes |
|---|---|
| `cuemsnodeconf/CuemsNodeConf.py` | row 5 (`:247`, `:299`, `:431`, `:458`, `:508`, `:537`, `:552`, `:573`, `:598`); `engine_callback` (`:113-161`); `cleanup` (`:615`, deleted); imports (`:19-28`); the Avahi installer (`:381`, `:419`) |
| `cuemsnodeconf/CuemsSettings.py` | `:27` — the TXT publisher |
| `cuemsnodeconf/CuemsAvahiListener.py` | `:19-24` stale comment; `:96-155` the two consumer blocks; `_AVAHI_NODE_TYPE_TO_ROLE` retired |
| `cuemsnodeconf/AvahiTool.py` | `:12` stale comment; its own role table |
| `cuems.service.{firstrun,master,slave}` | deleted |
| `tests/test_avahi_listener.py`, `tests/test_node_type.py` | fixtures carry the new key |
| `test_run_nodeconfig.py` | `:58, :61, :69` — the dev script's published key |
| `pyproject.toml`, `debian/control`, `debian/changelog` | pins and version |
| `CLAUDE.md` | the network-plumbing correction |

## Sequencing

Three groups, matching the spec's three user stories. **Group A is independent and can
land first**; groups B and C carry the cross-repository constraint.

- **A — the object adoption (P1).** Row 5, the RPC contract, the imports, `cleanup`'s
  deletion. Self-contained, mergeable alone, gated by SC-001/002/003/005/008.
- **B — the Avahi cutover (P2).** Developed here, **merged simultaneously with flow 03**
  (D33). A half-renamed intermediate state is a cluster that cannot discover itself, so
  the merge is the coordination point, not the development.
- **C — packaging and documents (P3).** The version, the pins, the stale comments,
  the CLAUDE.md correction. Rides with B, since the package constraint exists to make
  B's half-renamed state uninstallable.

Nothing releases before every feature-010 flow lands (D27).
