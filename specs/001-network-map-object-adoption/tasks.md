---
description: Task breakdown for the network-map object adoption and the Avahi vocabulary cutover
---

# Tasks: Network-map object adoption and the Avahi vocabulary cutover

**Input**: Design documents from `/specs/001-network-map-object-adoption/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: This feature adds no new test suites. It **updates** existing tests whose
fixtures carry the retired vocabulary, and **deletes** tests for methods being removed.
Per FR-025, no node-model test may be added here. The equivalence gate is the vendored
yardstick, which is run and never edited.

**Organization**: grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable — different file, no dependency on an incomplete task
- **[US1] / [US2] / [US3]**: the user story from `spec.md` the task serves

## Path Conventions

Single flat Python package at the repository root: `cuemsnodeconf/`, `tests/`,
`specs/planning/yardstick/`, plus packaging metadata. No new directories.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: establish a trustworthy baseline before anything moves.

- [X] T001 Re-run `.venv/bin/pip install -e /home/stagelab/cuems-utils` so the installed metadata reports `0.1.0rc16` instead of the stale `0.1.0rc15`; confirm with `.venv/bin/pip show cuemsutils`
- [X] T002 Record the baseline: `.venv/bin/python -m pytest -q` (expect 80 passed) and `.venv/bin/python -m pytest specs/planning/yardstick/ -q` (expect 15 passed); note both numbers in the PR description
- [X] T003 Re-measure every coordinate in `plan.md`'s per-file scope table against the current `cuemsnodeconf/CuemsNodeConf.py` and correct the table in place if anything has moved

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the import block at `cuemsnodeconf/CuemsNodeConf.py:19-28` is edited by every
story. Settle it once, first, so the three stories do not collide in it.

**⚠️ CRITICAL**: no user story work begins until this phase is complete.

- [ ] T004 Replace `from cuemsutils.xml.settings import NetworkMap as _NetworkMapReader` with `from cuemsutils.tools.ConfigManager import ConfigManager` in `cuemsnodeconf/CuemsNodeConf.py:23` (FR-013)
- [X] T005 Delete `from cuemsutils.xml.mapper import Mapper, read_config_document` from `cuemsnodeconf/CuemsNodeConf.py:22` outright — measured to have no call site beyond the import line (FR-013)
- [X] T006 Replace `from cuemsutils.timeoutloop import Timeoutloop` with `from cuemsutils.tools.TimeoutLoop import TimeoutLoop` in `cuemsnodeconf/CuemsNodeConf.py:26` and update all three call sites (`:327`, `:653`, `:665` — re-measured; the plan's `:635`/`:647` were stale) (FR-014)
- [ ] T007 Confirm SC-008's **two** halves: `grep -n 'cuemsutils\.xml\|cuemsutils\.timeoutloop' cuemsnodeconf/*.py` produces no output (no internal or deprecated import paths remain), **and** `.venv/bin/python -m pytest -q 2>&1 | grep -i deprecat` produces no output (all three `TimeoutLoop` call sites moved, not just one)

**Checkpoint**: imports are on public, current paths; the file compiles; the suite still passes.

---

## Phase 3: User Story 1 - The operator adopts and unadopts nodes (Priority: P1) 🎯 MVP

**Goal**: the daemon computes adoption using `cuemsutils`' network-map object instead of
its own copy, and the operator cannot tell the difference — including when the answer is "no".

**Independent Test**: the yardstick passes unchanged against the new API, and all six rows
of `contracts/engine-rpc.md`'s outcome table are driven through the real dispatch path on
the controller, with the persistence check.

> ⚠️ **Coordinates below are start-of-phase only.** Nine of these tasks edit
> `cuemsnodeconf/CuemsNodeConf.py`, and T014–T016 and T021 *delete* methods — so every line
> number after the first deletion shifts. **Locate targets by name, not by line.** The line
> numbers are an aid to finding them the first time, not an address to edit at.

### State ownership (research D-A — do this before anything that uses the map)

- [ ] T008 [US1] Change `self.network_map` to hold a `CuemsNetworkMapType` rather than a `NodeIndex` in `cuemsnodeconf/CuemsNodeConf.py:__init__` (`:50`), initialising it as an empty document (FR-005)
- [ ] T009 [US1] Rewrite `read_network_map` (`:598`) to load through `ConfigManager(config_dir=CUEMS_CONF_PATH).load_network_map()` then `.network_map`, assigning the returned `CuemsNetworkMapType` to `self.network_map` (FR-005)
- [ ] T010 [US1] Add a private helper in `cuemsnodeconf/CuemsNodeConf.py` that derives a `NodeIndex` from `self.network_map["node_list"]` keyed by `item["node"]["mac"]`, mirroring what `CuemsNetworkMapType.refresh` does internally (FR-005)
- [ ] T011 [US1] Add its counterpart that writes an index back as `self.network_map["node_list"] = [{"node": n} for n in index.values()]` and calls `self.network_map.save(self.map_path)` (FR-005)

### The refresh path

- [X] T012 [US1] Replace `refresh_network_map`'s four-step body (`:247`) with a single `self.network_map.refresh(self.listener.nodes, self.map_path)` call, keeping its existing `PermissionError` and general exception handling around it (FR-002, FR-006)
- [X] T013 [US1] Add an explicit `missing_adopted(self.listener.nodes)` call in `refresh_network_map` on a derived index, re-emitting today's `Missing adopted nodes: [...]` warning and its `All adopted nodes are present` debug counterpart (FR-007)
- [X] T014 [US1] Delete `_map_signature` (`:299`), `merge_discovered_nodes` (`:458`), `set_master_always_adopted` (`:508`) and `check_missing_adopted_nodes` (`:537`) from `cuemsnodeconf/CuemsNodeConf.py` (FR-001, FR-004)
- [ ] T015 [US1] Delete `write_network_map` (`:431`) from `cuemsnodeconf/CuemsNodeConf.py`, including its `required_fields` pre-check — an artifact the schema already enforces on the same write (FR-008)
- [X] T016 [US1] Delete `self._last_map_sig` from `__init__` (`:57`) — `refresh` owns the write decision now and compares the signature itself

### Adopt and unadopt

- [ ] T017 [US1] Rewrite `adopt_node` (`:552`) in `cuemsnodeconf/CuemsNodeConf.py` to derive an index, call `NodeIndex.adopt(node_uuid)`, and **on success write back and save** (research D-D) (FR-003)
- [ ] T018 [US1] Rewrite `unadopt_node` (`:573`) the same way against `NodeIndex.unadopt(node_uuid)`, preserving today's "unadopting offline node" info log (FR-003)
- [ ] T019 [US1] Implement the failure discrimination in both: on `False`, look the uuid up in the derived index and select `Node {uuid} not found` (absent), `Cannot adopt node {uuid}: node is offline` (present and offline) or `Cannot unadopt master node` (present and controller), per `contracts/engine-rpc.md` (FR-010)
- [ ] T020 [US1] Verify `engine_callback` (`:113-161`) still forwards only `OK` and `error`, still answers the unknown-action branch and still answers from its exception handler — no change expected, but FR-009 and FR-011 make it a checked invariant rather than an assumption

### The dead method

- [X] T021 [US1] Delete `cleanup` (`:615`) from `cuemsnodeconf/CuemsNodeConf.py` — it has no callers, and repairing it would make `/etc/cuems/settings.xml` a construction-time requirement of the daemon (research D-C) (FR-012)

### Tests

- [X] T022 [P] [US1] Update `tests/test_network_map.py` — remove tests of the deleted methods, and add one asserting the write-only-on-change invariant (constitution II): a second `refresh` with identical discovery returns `False` and leaves the file's mtime untouched. This behaviour moves *inside* `refresh` during the swap, which is exactly when it could be lost without anything failing
- [ ] T023 [P] [US1] Update `tests/test_node_adoption.py` and `tests/test_adoption_flow.py` for the new adopt/unadopt internals, asserting the response shape and all three error strings
- [ ] T024 [P] [US1] Update `tests/test_engine_callback.py` to assert the full outcome table in `contracts/engine-rpc.md`, including that a successful adopt **persisted** before the response was produced
- [X] T025 [P] [US1] Update `tests/test_missing_nodes.py` for the explicit `missing_adopted` call
- [ ] T026 [US1] Run `.venv/bin/python -m pytest specs/planning/yardstick/ -q` — must be 15 passed, **unchanged**. If it fails, the port is wrong; do not edit the yardstick (SC-001)
- [ ] T027 [US1] Run `.venv/bin/python -m pytest -q` — all pass, nothing skipped (SC-005)
- [ ] T028 [US1] Confirm SC-002 by grep: none of the nine replaced method definitions remain except `refresh_network_map` as a thin caller

**Checkpoint**: User Story 1 is complete and mergeable on its own. `quickstart.md` §3 can now be walked on the controller.

---

## Phase 4: User Story 2 - The cluster still discovers itself (Priority: P2)

**Goal**: the discovery TXT key becomes `node_role` with `controller`/`node`/`firstrun`
values, in lockstep with `cuems-common`.

**Independent Test**: with both halves applied, a controller and a node discover each other
and resolve roles; with one half applied, the mismatch is logged rather than silently
absorbed.

**⚠️ Merge constraint**: developed here, **merged simultaneously with flow 03**. A
half-renamed state must never ship (FR-019).

- [ ] T029 [P] [US2] Change the published TXT record to `{'node_role': 'node'}` in `cuemsnodeconf/CuemsSettings.py:27` and rewrite the comment above it — a rename only, keeping "the non-controller role" as the pre-election self-announcement (FR-015)
- [ ] T030 [US2] Rewrite the `add_service` and `update_service` blocks in `cuemsnodeconf/CuemsAvahiListener.py:96-155` to read `b'node_role'` and resolve the value through `NodeRole` directly (FR-015)
- [ ] T031 [US2] Delete `_AVAHI_NODE_TYPE_TO_ROLE` from `cuemsnodeconf/CuemsAvahiListener.py:26-30`, preserving the unrecognised-value log that names the offending value and the accepted set (FR-017)
- [ ] T032 [P] [US2] Delete the second, identical `_AVAHI_NODE_TYPE_TO_ROLE` copy from `cuemsnodeconf/AvahiTool.py:19-23` — a table the consumer audit never named — and make its three decode sites (`:88`, `:100`, `:104`) read `info.properties[b'node_role']` **by name**. They currently read `properties[list(properties.keys())[0]]`, i.e. whichever TXT key happens to come first; a key that is never read by name cannot be renamed correctly, so reading by name is part of the rename rather than beyond it (FR-017)
- [ ] T033 [P] [US2] Correct the stale "deferred to feature 008" comment in `cuemsnodeconf/AvahiTool.py:10-18` (FR-020)
- [ ] T034 [US2] Correct the stale "deferred to feature 008" comment in `cuemsnodeconf/CuemsAvahiListener.py:18-25` (FR-020)
- [ ] T035 [US2] Update the template path construction in `cuemsnodeconf/CuemsNodeConf.py:381` and `:419` from `+ '.master'` / `+ '.slave'` to `+ '.controller'` / `+ '.node'` (FR-016)
- [ ] T036 [P] [US2] Delete `cuems.service.firstrun`, `cuems.service.master` and `cuems.service.slave` from the repository root — unshipped duplicates of the files `cuems-common` installs (FR-018)
- [ ] T037 [P] [US2] Update the non-shipped dev script `test_run_nodeconfig.py` — the published key (`:69`) **and** the two values and the local variable carrying them (`:58`, `:61`: `node_type = 'master'` / `'slave'` become `node_role = 'controller'` / `'node'`)
- [ ] T038 [P] [US2] Update the TXT fixtures in `tests/test_avahi_listener.py:37-43,95-104,124` to the new key and values
- [ ] T039 [P] [US2] Rename `tests/test_node_type.py` and its test at `:21` to the current vocabulary. Note this file asserts that **this repository defines no NodeType module of its own** — it is feature 007's structural check, not a TXT fixture, so rename it without changing what it asserts (FR-025: it stays a check on this repository's structure, not a test of the model)
- [ ] T040 [US2] Confirm SC-004: `grep -rn 'node_type' --exclude-dir=.git --exclude-dir=.venv . | grep -v '^\./specs/'` produces no output
- [ ] T041 [US2] Cross-check the pinned vocabulary against `cuems-common`'s half in `/home/stagelab/cuems-common` — key, all three values and all three filenames must agree exactly before either side merges
- [ ] T042 [US2] 🚧 **MERGE GATE (FR-019) — blocking, do not clear early.** Confirm in `/home/stagelab/cuems-common` that flow 03's counterpart rename exists on a branch, is reviewed, and is ready to merge in the same window as this one; record that branch and commit in this PR's description, and agree the simultaneous-merge window with flow 03's owner. **US2 and US3 do not merge until this task is checked.** A publisher and a listener disagreeing about the TXT key discover nothing, and the failure is silent — no error, no exception, nodes simply never appear

**Checkpoint**: this repository's half is complete, verified against the counterpart's, and held at the merge gate. `quickstart.md` §4 can be walked.

---

## Phase 5: User Story 3 - Upgrading cannot produce a broken combination (Priority: P3)

**Goal**: the package metadata makes a half-renamed installation impossible.

**Independent Test**: an out-of-order `dpkg -i` is refused.

- [ ] T043 [US3] Add a `0.1.0-8` entry to `debian/changelog` summarising the object adoption and the vocabulary cutover, satisfying `cuems-common`'s existing `Breaks: cuems-nodeconf (<< 0.1.0-8)` (FR-021)
- [ ] T044 [P] [US3] Move the `cuemsutils` floor to `>=0.1.0rc16` and add an upper bound in `pyproject.toml:28` (FR-022)
- [ ] T045 [P] [US3] Move the `cuems-utils` constraint to match exactly in `debian/control:18` — currently `>= 0.1.0rc5`, disagreeing with `pyproject.toml` — and add the upper bound or a `Breaks:`, following the pattern `cuems-common` already uses
- [ ] T046 [US3] Correct the network-plumbing claim in `CLAUDE.md`: the daemon **does** rewrite `/etc/network/interfaces` and restart `networking.service` on the controller-promotion path (`CuemsNodeConf.py:396` → `:724` → `:766`); `cuems-common`'s CLAUDE.md and the atomization basis both already record this (FR-023)
- [ ] T047 [US3] Build both packages and demonstrate the refusal per `quickstart.md` §4 (SC-007) — a gate that has never been demonstrated is a claim

**Checkpoint**: all three stories complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T048 [P] Add the yardstick to this repository's CI as a separate invocation, `pytest specs/planning/yardstick/`, kept out of `testpaths` so it is not mistaken for a local test (research D-H)
- [ ] T049 [P] Report the two stale docstrings upstream in `cuems-utils` — `NodeIndex.set_controller_always_adopted` still says "on a first run, nothing else is", and `CuemsNetworkMapType.refresh` still describes the un-ported branch as an open item. **Report, do not patch**: the yardstick's guarantee depends on that file not being edited from this side
- [ ] T050 Walk `quickstart.md` §3 on the controller and record the result of every row, including the persistence check (SC-003)
- [ ] T051 Walk `quickstart.md` §4 with both halves present, including the deliberate half-renamed check (SC-006)
- [ ] T052 Re-check the permissions surface (constitution I): confirm nothing in the changed write path alters the ownership or mode of `/etc/cuems/network_map.xml`, and that `/tmp/nodeconf.ipc` is still `chmod 0666` after binding in `cuemsnodeconf/communicate.py`. The plan asserts this is satisfied by inspection — this task is that inspection
- [ ] T053 Re-check the scope boundaries (FR-024, FR-025): `git diff main...HEAD --stat` shows no module added to `cuemsnodeconf/`, no responsibility added to `CuemsNodeConf`, and no new test of the node model in `tests/`. Confirm `specs/planning/01-atomization-basis.md` still describes the class accurately apart from row 5's removal
- [ ] T054 Record in the PR description which manual verifications were performed and which were not — the constitution accepts "verified" and "not verified", and treats silence as a failure

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)** → no dependencies
- **Phase 2 (Foundational)** → after Phase 1. **Blocks all stories** — every story edits the same import block
- **Phase 3 (US1)** → after Phase 2. Independent of US2 and US3
- **Phase 4 (US2)** → after Phase 2. Independent of US1. **Ends at a blocking merge gate (T042)**
- **Phase 5 (US3)** → after Phase 2. Its content is independent, but T047's demonstration needs US2 complete
- **Phase 6 (Polish)** → after the stories it verifies

### User Story Dependencies

None between stories *for development*. US1 is fully mergeable alone.

**For merging, US2 and US3 are gated on T042.** FR-019 is enforced by that task, not by
review convention: neither story merges until flow 03's counterpart is confirmed ready and
a simultaneous window is agreed. T047's package-refusal demonstration is the second line of
defence — it proves an installation cannot end up half-renamed even if the merge discipline
fails — but it is not a substitute for the gate, because it only protects nodes that install
both packages, not a repository that merges one half and releases from it.

### Within User Story 1

T008–T011 (state ownership) **block** T012–T019 — every one of those uses the derived
index. T014–T016 (the deletions) come after T012–T013, so the replacement is in place
before the original is removed. T022–T025 follow their implementation tasks. T026–T028 are
the gates and come last.

### Parallel Opportunities

- **Phase 4** is highly parallel: T029, T032, T033, T036, T037, T038, T039 touch different
  files with no ordering between them. T030 → T031 are the same file, in order.
- **Phase 5**: T044 and T045 are different files; T043 and T046 are independent again.
- **Phase 3** is mostly sequential — nine of its tasks edit `CuemsNodeConf.py`. Only the
  four test updates (T022–T025) parallelise.

## Parallel Example: User Story 2

```bash
# these seven touch seven different files and can be done in any order
T029  cuemsnodeconf/CuemsSettings.py
T032  cuemsnodeconf/AvahiTool.py           (table)
T033  cuemsnodeconf/AvahiTool.py           (comment — same file as T032, do together)
T036  cuems.service.{firstrun,master,slave}
T037  test_run_nodeconfig.py
T038  tests/test_avahi_listener.py
T039  tests/test_node_type.py
```

## Implementation Strategy

**MVP = User Story 1 alone.** It removes the responsibility this feature exists to remove,
it is verifiable by the yardstick plus the controller walkthrough, and it merges without
waiting for another repository. Ship it first.

Then US2 and US3 together, **held at T042 until flow 03 is ready** — their merge is the
coordination point, not their development. Nothing releases before every feature-010 flow
lands.
