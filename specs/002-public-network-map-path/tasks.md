---

description: "Task list for 002 — reach the network map through public paths only"
---

# Tasks: Reach the network map through public paths only

**Input**: Design documents from `specs/002-public-network-map-path/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: included. The spec asks for them — SC-002 (nothing pre-existing changes), SC-004
(an adoption between passes survives), SC-005 (a fresh node boots), and FR-005 (the seed's mode
is pinned by a test, not by systemd's default umask).

**Organization**: one user story (P1). It is the whole feature; §"Minimal path" below says what
the smallest correct increment is.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel — different files, no dependency on an unfinished task
- **[Story]**: the user story a task serves (US1 here)
- Every task names the exact file it touches

## Path Conventions

Single Python package at the repository root: `cuemsnodeconf/` for shipped code, `tests/` for
the suite, `specs/planning/yardstick/` for the vendored equivalence gate (run, never edited).

---

## Phase 1: Setup

**Purpose**: make the environment match what the feature requires, and record the baseline the
"nothing else changed" claims are measured against.

- [ ] T001 Rebuild the library the feature depends on: `.venv/bin/pip install -e ../cuems-utils`, then confirm the installed build is **at or after `e363d03`** by running its discriminator `.venv/bin/python -m pytest -q ../cuems-utils/tests/contract/test_empty_node_list.py` (expect 9 passed). **This cannot be checked by version**: the empty-`node_list` fix shipped *inside* `0.1.0rc16`, so `>= 0.1.0rc16` is satisfied by a build that still crashes on the shipped map. Do not start T003 until this passes. Traces to **FR-011**
- [ ] T002 [P] Capture the baseline **before editing anything**, and carry it into the implementation commit and T017's record (not this file's own commit, which is already made): `./run-tests.sh` (expect `both green`, 95 + 15) and `git rev-parse --short HEAD`, which is the base T016's `git diff -- tests/` compares against

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the fixture and guard that every US1 test depends on.

**⚠️ No US1 task may start until T003 and T005 are done.**

- [ ] T003 Add `tests/fixtures/etc_cuems/network_map_empty.xml`, **byte-identical** to the map `cuems-common` ships (200 bytes, `<node_list/>`, trailing newline) — verify with `diff <(git -C ../cuems-common show f2fc0f5:etc/cuems/network_map.xml) tests/fixtures/etc_cuems/network_map_empty.xml`. This is the shape `cuemsutils` asked this repository to cover (research R6): no existing fixture is empty, which is why the `TypeError` was missed here. The same bytes are the seed's source of truth per [contracts/empty-map-seed.md](contracts/empty-map-seed.md), so the two cannot drift
- [ ] T004 [P] Add a `cuems_conf_dir_empty` fixture to `tests/conftest.py` beside `cuems_conf_dir`: copy `settings.xml` plus `network_map_empty.xml` (as `network_map.xml`) into `tmp_path` and point `CUEMS_CONF_PATH` at it. Tests must never reach the real `/etc/cuems`
- [ ] T005 Add `tests/test_library_prerequisite.py`: loading an empty map through `ConfigManager` raises **`ValueError`**, not `TypeError`. This fails loudly on a stale venv, which is the only way this repository can detect a pre-fix `cuemsutils` — packaging cannot express it (T001). Keep it one short test with a comment naming `cuems-utils` `e363d03`. This is what makes **FR-011/SC-007** true: a stale library fails the suite on a checkout instead of failing a node at boot

**Checkpoint**: the empty-map shape exists as a fixture, and a stale library fails the suite instead of failing a node at boot.

---

## Phase 3: User Story 1 — The daemon reaches the network map only through the library's public surface (Priority: P1) 🎯 MVP

**Goal**: delete the last internal import by keeping the document `ConfigManager` already
returns, and make the first-run branch seed the shipped empty map so a document always exists.

**Independent test**: `grep -rn "from cuemsutils.config" cuemsnodeconf/` returns nothing, and
`./run-tests.sh` is green with the suite's count raised by this story's new tests.

### Tests for User Story 1 (write before the implementation they pin) ⚠️

- [ ] T006 [P] [US1] Add `tests/test_public_surface.py`: no file under `cuemsnodeconf/` imports from `cuemsutils.config` or `cuemsutils.xml` (SC-001, FR-001). **Fails today** — `CuemsNodeConf.py:21` is exactly that import. Enumerate the two exemptions in the test's docstring, not in its assertions: the test files (FR-007) and the vendored yardstick, neither of which is shipped code
- [ ] T007 [P] [US1] Add `tests/test_fresh_node_boot.py` using `cuems_conf_dir_empty` and a `tmp_path` map: (a) with **no** map file, start-up seeds one whose bytes equal `network_map_empty.xml` and whose mode is **`0644`** (FR-004, FR-005); (b) `read_network_map()` over it yields an index of **0 nodes** — the `ValueError` is caught, not raised; (c) the first `_save_network_map()` writes the node, and a second read returns **1 node**. **Fails today** (no seeding). This is the path every fresh install takes. **Also drive `run()` itself** for the seeding branch, with `get_ips` and zeroconf mocked, asserting the seed is written exactly once: measured 2026-09-21, **no existing test covers it** — `test_first_run_becomes_controller_scenario` never calls `run()`, and `test_run_exits_on_no_ip` exits on the IP check before the map branch is reached, so without this T011's edit ships untested
- [ ] T008 [P] [US1] Add to `tests/test_network_map.py` a test that an adoption made **between two refresh passes** is on disk after the next pass (SC-004). It passes before and after the change — that is the point: the kept document is a new opportunity for exactly this staleness, and the guard must exist before the document starts being kept

### Implementation for User Story 1

**All five of T009–T013 edit `cuemsnodeconf/CuemsNodeConf.py`. They are deliberately not `[P]` — same file, and T013 only makes sense once T009–T012 are in place.**

- [ ] T009 [US1] In `CuemsNodeConf.__init__` (`cuemsnodeconf/CuemsNodeConf.py`), add `self._document = None` beside `self.network_map = NodeIndex()`, with a comment that the document is obtained at start-up and kept for the process lifetime (**FR-002**, data-model §2)
- [ ] T010 [US1] Add `_seed_empty_map()` to `cuemsnodeconf/CuemsNodeConf.py`: write the empty map's bytes to a temp file **in `map_path`'s own directory**, `chmod 0644`, then `os.replace` onto `map_path`. Atomic because a partial map is loaded on the next boot and fails validation (constitution II); explicit mode because a plain create is `0600` under umask `0077` and the engines read this file as `User=cuems` (constitution I). On failure log the path and `sys.exit(-1)`, as the other start-up failures do. Keep the bytes in one module-level constant, matching [contracts/empty-map-seed.md](contracts/empty-map-seed.md) — **`<node_list/>` is required**; a bare root decodes to `{}` and breaks `refresh`/`save` upstream
- [ ] T011 [US1] Rewrite `run()`'s first-run branch (`cuemsnodeconf/CuemsNodeConf.py`, the `self.is_first_run = not os.path.isfile(self.map_path)` block) to call `_seed_empty_map()` when the file is absent and then fall through to the **same** `read_network_map()` call both cases now use. The seeded map lists no node, so the load raises `ValueError`, which feature 001's catch already handles — do not add a second catch
- [ ] T012 [US1] In `read_network_map()` (`cuemsnodeconf/CuemsNodeConf.py`), keep the loaded document as `self._document` **before** assigning `self.network_map` (**FR-002**). Order is load-bearing, not style: `set_comms()` starts the IPC listener before `run()`, so an adopt RPC arriving between the two assignments would mutate a populated index and then save through a document that is not there (research R2, constitution VI). Say so in a comment
- [ ] T013 [US1] Make `_network_map_document()` refill and return the kept document — `self._document["node_list"] = [{"node": n} for n in self.network_map.values()]` — raising a clear `RuntimeError` naming the situation if `self._document` is `None`, never `AttributeError`; then **delete the import at `cuemsnodeconf/CuemsNodeConf.py:21`** (`from cuemsutils.config.network_map import CuemsNetworkMapType`). The index stays the single source of truth: `node_list` is overwritten in full on every call (FR-003)
- [ ] T014 [US1] Give the **28 tests that reach save or refresh without start-up** a document in setup — one line each, through the import those files already hold (FR-007): `tests/test_integration.py` (6), `tests/test_network_map.py` (6), `tests/test_node_adoption.py` (4), `tests/test_adoption_flow.py` (4), `tests/test_phase1_changes.py` (4), `tests/test_engine_callback.py` (2), `tests/test_missing_nodes.py` (2). **Setup only**: no test's name, subject or assertion may change (SC-002). Measured in research R1: an empty document makes all 95 pass. ⚠️ **These 28 are NOT FR-007's 28 `patch.object` sites** — two different sets that happen to share a total. FR-007 counts save-patch sites (9/6/5/5/2/1 across **six** files); this task counts tests that reach save or refresh without start-up (the seven above, including `test_phase1_changes.py`, which has no patch sites at all). Do not reconcile the two lists — changing either to match the other breaks something

**Checkpoint**: US1 is complete and independently shippable — the daemon reaches the library only through public paths, and a fresh node boots.

---

## Phase 4: Polish & Cross-Cutting Concerns

- [ ] T015 [P] Run the gate and the equivalence check: `./run-tests.sh` (expect `both green`, 95 + this story's new tests, and 15 — **SC-002**) and, for **FR-008/SC-003**, `diff specs/planning/yardstick/test_nodeindex_characterization.py ../cuems-utils/tests/contract/test_nodeindex_characterization.py` (expect no output). **Diff it, do not assume it** — the yardstick must stay byte-identical and must never be edited from this side. Note while here: the constitution's testing gate still says "16 test files, currently 81 tests" against a suite of 95. Pre-existing drift, **out of scope for this feature** — it is governance text and changes only by an explicit constitution update; record it in T017 rather than editing it
- [ ] T016 [P] Review `git diff <T002 baseline> -- tests/` and confirm SC-002 literally: every change to a pre-existing test is an added setup line: no renamed test, no altered assertion, and all 28 `patch.object(CuemsNetworkMapType, 'save')` sites still present (FR-007's 28 — see T014's warning). In the same pass confirm the requirements no task can automate, and say so in T017: **FR-009** (the library is unchanged from this side, no alias requested, no `type(...)` route, no local reimplementation of `refresh`) and **FR-010/SC-006** (both decisions recorded — already satisfied by the committed spec, plan and contracts)
- [ ] T017 Write `specs/002-public-network-map-path/evidence/verification-record.md` stating what was verified and what was **not**, as feature 001 did: the suite and yardstick counts, the seeded-boot measurement in a temporary directory, and plainly that [quickstart.md](quickstart.md) §4 — the operator adopt/unadopt chain on a controller, and a genuine fresh node installed from the package — **was not performed**. The constitution accepts "verified" and "not verified" and treats silence as a failure

- [ ] T018 Create `specs/002-public-network-map-path/checklists/hardware-verification.md` — **one ledger for every verification that needs hardware or a human**, for this feature and for 001 (FR-012, SC-008). Constitution IV requires the adopt/unadopt chain to be verified against the real dispatch path, and that is **deferred by decision (2026-09-21)**, not waived: a deferral that lives only in prose becomes an implied "later" and then a PR that reads as verified. Each entry carries what to do, what would prove it, why the suite cannot, and its state (all `[ ]` — none performed). Required entries: (a) **feature 001's T050** — `specs/001-network-map-object-adoption/quickstart.md` §3, the six-row adopt/unadopt outcome table driven from the frontend settings view on the controller, including the persistence check that the map on disk changes immediately, since `NodeIndex.adopt` mutates without saving and a dropped save looks correct in the UI; (b) **feature 001's T051** — its quickstart §4 discovery check across the rename, including the deliberate half-renamed pair; (c) **this feature's operator chain** — adopt and unadopt through the UI against the kept document, which is the FR-006/constitution IV deferral; (d) **this feature's fresh node** — a node installed from the package whose map is the shipped empty conffile boots, writes itself in, and leaves the map `0644` for the `User=cuems` engine. Cross-link it from 001's `evidence/verification-record.md` so the debt is discoverable from either feature

---

## Dependencies & Execution Order

```text
T001 ────────────────▶ T003 ──┬─▶ T005 ─────────────▶ T006, T007, T008  (tests, [P])
  (library rebuilt)            └─▶ T004 [P]                    │
T002 [P] (baseline)                                            ▼
                                        T009 ▶ T010 ▶ T011 ▶ T012 ▶ T013   (one file, sequential)
                                                                   │
                                                                   ▼
                                                                 T014  (the 28 setup lines)
                                                                   │
                                                          T015 [P], T016 [P] ▶ T017

T018 (hardware ledger) is independent of the code and can be written at any point
```

- **T001 blocks everything.** Against a pre-fix library the seeded map cannot be read at all, so T007 would fail for a reason that has nothing to do with this feature.
- **T003 blocks T004, T005, T007** — they all use the empty-map bytes.
- **T006–T008 are `[P]`**: three different test files, no shared state.
- **T009–T013 are strictly sequential**: one file, and the import can only be deleted once the last user of the class is gone (T013).
- **T014 after T013**: before it, those 28 tests fail with the `RuntimeError` T013 introduces; after it, they pass.
- **T015–T016 are `[P]`**; T017 records their results, so it is last.
- **T018 depends on nothing** — it records deferred hardware debt, so it may be written before the code is touched, and it must exist before the feature is called done.

## Parallel Opportunities

- **Phase 2**: T004 alongside T005 once T003 exists.
- **Phase 3 tests**: T006, T007 and T008 together.
- **Phase 4**: T015 and T016 together; T018 alongside anything.

Nothing in the implementation phase parallelises — it is five edits to one file, which is what
"scope: one shipped file" buys.

## Implementation Strategy

### Minimal path

The feature is one story, and the smallest correct increment is the whole of Phase 3: the import
cannot be deleted without the kept document, and the kept document is wrong on a fresh node
without the seed. Phase 2 exists because `cuemsutils` asked for the fixture (R6) and because a
stale venv must fail the suite rather than a node at boot.

### Incremental delivery

1. **T001–T005** — environment and fixture. The suite still passes; nothing shipped has changed.
2. **T006–T008** — three failing/guard tests that describe the target.
3. **T009–T014** — the change. The suite goes green again, with the import gone.
4. **T015–T018** — prove it, write down what was not proven, and put the hardware debt of both features on one checklist.

### The one thing this strategy must not permit

Editing `specs/planning/yardstick/test_nodeindex_characterization.py` to make anything pass. It
is `cuems-utils`' file, vendored byte-identically; if it ever needs to change, it changes there
and is re-vendored. The same applies to loosening an existing test's assertion to accommodate
the kept document — the 28 tests get setup lines, nothing else (SC-002).
