---

description: "Task list for 003 — start-up readiness"
---

# Tasks: Start-up readiness

**Input**: Design documents from `specs/003-startup-readiness/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: included. The spec asks for them — FR-006 (the window is exercised, not inspected),
FR-016 (a stale library fails here, not on a node), SC-001..SC-005 and SC-011 (each "shown by a test").
Tests for a story are written first and must fail before that story's implementation task.

**Organization**: six user stories, in the spec's priority order. US5 (documents) touches no code and
may run at any point, including before Phase 2. US6 is the polish phase decided under option B and is
**droppable to a maintenance pass** without touching the other stories (FR-025).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel — different files, no dependency on an unfinished task
- **[Story]**: the user story a task serves (US1..US6)
- Every task names the exact file it touches

## Path Conventions

Single Python package at the repository root: `cuemsnodeconf/` for shipped code (this feature edits
**only** `cuemsnodeconf/CuemsNodeConf.py`), `tests/` for the suite, `specs/planning/yardstick/` for the
vendored equivalence gate (run, never edited).

---

## Phase 1: Setup

**Purpose**: confirm the environment carries what the feature depends on, and record the baseline.

- [X] T001 Confirm the library build carries `NodeIndex.ensure`: `.venv/bin/python -c "from cuemsutils.tools.NodeList import NodeIndex; assert hasattr(NodeIndex, 'ensure')"`. If it fails, the sibling `../cuems-utils` checkout is not at **`73daab6`** or later (branch `011-etc-cuems-first-install`); fix the checkout and `.venv/bin/pip install -e ../cuems-utils` — never add a daemon-side fallback (research R6, D2). Do not start Phase 6 until this passes
- [X] T002 [P] Capture the baseline before editing anything: `./run-tests.sh` (expect 119 + 15 green), `cmp specs/planning/yardstick/test_nodeindex_characterization.py ../cuems-utils/tests/contract/test_nodeindex_characterization.py` (expect identical), `git rev-parse --short HEAD`. Carry the three into the implementation commit message
- [X] T003 [P] Re-measure the line numbers research.md cites for `cuemsnodeconf/CuemsNodeConf.py` (`start` :128, `set_comms` :134, `engine_callback` :139, `run` :189, `_install_master_service_template` :480, `set_node_role` :497, `read_network_map` :599, `retreive_local_node` :678, `TimeoutLoop(timeout=10` :428, `time.sleep(5)` :252) with `grep -n`; if any moved, correct research.md in the same commit (constitution: measure, do not transcribe)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the constants, fixtures and library gate every code story builds on.

**⚠️ CRITICAL**: Phases 3, 4, 6 and 8 depend on this phase. Phase 5 and Phase 7 do not.

- [X] T004 Add the module constants to `cuemsnodeconf/CuemsNodeConf.py` beside `TEMPLATES_PATH`: `AVAHI_SERVICES_PATH = '/etc/avahi/services/'`, `SENTINEL_UUID = '00000000-0000-0000-0000-000000000000'`, `SENTINEL_MAC = '000000000000'`, `IFACE_TIMEOUT_ENV = 'CUEMS_NODECONF_IFACE_TIMEOUT'`, `IFACE_TIMEOUT_DEFAULT = 10`, `CONTROLLER_PAUSE_ENV = 'CUEMS_NODECONF_CONTROLLER_PAUSE'`, `CONTROLLER_PAUSE_DEFAULT = 5`, each with a comment naming its contract (research R3, R4, R7). Replace the three inline `'/etc/avahi/services/'` strings (:483, :521 and the resume path) with the constant. Suite still 119 green
- [X] T005 [P] Create `tests/fixtures/etc_cuems/settings_sentinel.xml`: a copy of `tests/fixtures/etc_cuems/settings.xml` whose `<node><uuid>` is `00000000-0000-0000-0000-000000000000` and `<node><mac>` is `000000000000`, with a header comment stating it is the unprovisioned shape 011 ships (research R3)
- [X] T006 [P] Create `tests/fixtures/avahi/cuems.service.controller`, `tests/fixtures/avahi/cuems.service.node`, `tests/fixtures/avahi/cuems.service.firstrun`: copies of `../cuems-common/usr/share/cuems/cuems.service.{controller,node,firstrun}` with both `uuid=…` TXT records set to the sentinel (two occurrences per file), plus a `README.md` in that directory stating they mirror `cuems-common 1.3.0-23`'s handover shape and must be refreshed from there, never hand-edited (contract service-record-render.md)
- [X] T007 Add two fixtures to `tests/conftest.py`: `avahi_dirs(tmp_path, monkeypatch)` — copies the three T006 templates into `tmp_path/'share'`, creates `tmp_path/'services'`, and `monkeypatch.setattr` `cuemsnodeconf.CuemsNodeConf.TEMPLATES_PATH` / `AVAHI_SERVICES_PATH` to those paths (with trailing slash), returning `(share, services)`; and `cuems_conf_dir_sentinel(tmp_path, monkeypatch)` — like `cuems_conf_dir` but copying `settings_sentinel.xml` as `settings.xml`. Docstrings in the style of the existing fixtures
- [X] T008 Add `test_node_index_ensure_is_present_and_inserts_by_reference` to `tests/test_library_prerequisite.py`: `hasattr(NodeIndex, 'ensure')`; insert a node dict, mutate it through the caller's reference, assert the index sees the mutation; a second `ensure` with the same uuid returns `False` and leaves the row untouched. Module docstring gains a paragraph: the method landed in `cuems-utils` **`73daab6`** inside `0.1.0rc16`, which the pin cannot express (FR-016, research R6)

**Checkpoint**: constants in place, fixtures available, library gate green.

---

## Phase 3: User Story 1 — An operator's adopt during start-up is refused for the right reason (Priority: P1) 🎯 MVP

**Goal**: between binding the socket and loading the map, adopt/unadopt answer
`{'OK': False, 'error': 'nodeconf is still starting up'}`; everything else is unchanged.

**Independent Test**: `.venv/bin/python -m pytest tests/test_startup_readiness.py tests/test_engine_callback.py -q`
— the new file green, the 16 existing tests untouched and green.

### Tests for User Story 1

- [X] T009 [P] [US1] Create `tests/test_startup_readiness.py` with class `TestTheWindow`: construct `CuemsNodeConf()` with `communications_thread = MagicMock()` (the pattern of `tests/test_engine_callback.py:16`); before any map load, send `{'action': 'nodelist_modify', 'modify_action': 'ADD', 'value': <uuid from the fixture map>}` and `REMOVE`; assert the captured response is exactly `{'OK': False, 'error': 'nodeconf is still starting up'}` and that `'not found' not in error` (SC-001, FR-001). Must fail before T012
- [X] T010 [P] [US1] Add class `TestOtherRequestsDuringTheWindow` to `tests/test_startup_readiness.py`: unknown action, missing action and a non-dict body sent before the load receive today's answers (`unknown action: …` / the exception path) — the gate narrows nothing (FR-003, Story 1 scenario 2)
- [X] T011 [P] [US1] Add class `TestReadinessIsSetOnlyAfterBothHalves` to `tests/test_startup_readiness.py` using `cuems_conf_dir`: (a) `_ready is False` after construction; (b) `patch.object(nodeconf, '_index_from_document', side_effect=…)` that, from inside `read_network_map()`, sends an adopt and records the answer — it must be the start-up refusal (Story 1 scenario 4, FR-002); (c) after `read_network_map()` returns, `_ready is True` and the same adopt gets the pre-feature answer (`OK: True` for an online node; `Node … not found` for an unknown uuid); (d) a load that raises (`patch.object(ConfigManager, 'load_network_map', side_effect=RuntimeError)`) leaves `_ready` `False`

### Implementation for User Story 1

- [X] T012 [US1] In `cuemsnodeconf/CuemsNodeConf.py`: `__init__` sets `self._ready = False` with a comment naming the window (research R1/R2); `read_network_map()` sets `self._ready = True` as its **last statement**, after both `self._document` and `self.network_map` assignments, with a comment that the order is the contract (FR-002); `engine_callback()` checks `if not self._ready:` at the top of the `nodelist_modify` branch and responds `{'OK': False, 'error': 'nodeconf is still starting up'}` through the same `respond_to_engine` path, logging at INFO with the uuid. Then the **setup-only** lines the measured suite needs (research R8): `nodeconf._ready = True` in `tests/test_engine_callback.py`'s two `_nodeconf` helpers (:140, :190) and in its four standalone tests (:14, :53, :78, :103), and in every `tests/test_adoption_flow.py` test that calls `engine_callback` — one line each, with the comment `# feature 003: these tests skip start-up`, no subject or assertion changed, each file listed in the commit message (FR-004). T009–T011 pass; `tests/test_engine_callback.py` 16 green
- [X] T013 [US1] Add `## Start-up window` to `CLAUDE.md` under "Field notes / gotchas": the window's bounds, the refusal string, decision D (consumers relay verbatim), and that a mutex is not the fix (spec FR-007), five lines at most

**Checkpoint**: US1 is the MVP. An operator can never again be told a present node is not found during start-up.

---

## Phase 4: User Story 2 — The daemon announces only the identity the node was provisioned with (Priority: P2)

**Goal**: before the socket exists, render `/etc/avahi/services/cuems.service` from `settings.xml` and the
role template; refuse to start when unprovisioned; render the same way at the role sites; refuse a
discovered self with the wrong uuid.

**Independent Test**: `.venv/bin/python -m pytest tests/test_service_record.py tests/test_startup_readiness.py::TestSelfGuard tests/test_node_role.py tests/test_integration.py -q`.

### Tests for User Story 2

- [X] T014 [P] [US2] Create `tests/test_service_record.py` with class `TestRender` using `cuems_conf_dir` + `avahi_dirs` and a `reload` counter (`patch.object(nodeconf, '_reload_avahi')`): rendering `NodeRole.node` writes `services/cuems.service` equal to the node template with both sentinels replaced by the fixture uuid `0367f391-ebf4-48b2-9f26-000000000001`; returns `True`; reload called once; mode is `0644` even under `os.umask(0o077)` (constitution I); no temp file left; rendering again returns `False`, writes nothing (mtime unchanged) and does not reload (FR-010, SC-005)
- [X] T015 [P] [US2] Add class `TestRenderRefusals` to `tests/test_service_record.py`: a template with zero sentinels (write a real uuid into the fixture copy) → `SystemExit`, live file untouched, log contains the template path (research R4 step 2); a missing template → `SystemExit` naming it
- [X] T016 [P] [US2] Add class `TestUnprovisionedRefusesToStart` to `tests/test_service_record.py`: for each of (a) `settings.xml` deleted, (b) `patch('cuemsnodeconf.CuemsNodeConf.ConfigManager', side_effect=PermissionError(13, 'Permission denied'))` — no chmod, no skip (FR-019), (c) `settings.xml` replaced by `<broken/>`, (d) `cuems_conf_dir_sentinel`: `patch.object(nodeconf, 'set_comms')` and `patch.object(nodeconf, 'run')`, call `start()`, assert `SystemExit` with non-zero code, `set_comms` **not called**, no file under `services/`, and the log's critical line starts with `NOT PROVISIONED` (FR-011, SC-004)
- [X] T017 [P] [US2] Add class `TestRenderHappensBeforeTheSocket` to `tests/test_service_record.py`: a shared `calls` list appended to by `patch.object(nodeconf, '_render_service_record', side_effect=…)` and `patch.object(nodeconf, 'set_comms', side_effect=…)`, `run` patched out; after `start()`, `calls == ['render', 'set_comms']` (contract startup-order.md steps 3–4)
- [X] T018 [P] [US2] Add class `TestStartupRenderKeepsTheLiveRole` to `tests/test_service_record.py`: a live file rendered from the controller template → the start-up render picks `NodeRole.controller`; a live file with `node_role=node` → `node`; no live file → `firstrun`; a live file with garbage → `firstrun` (research R4 "which role at start-up")
- [X] T019 [P] [US2] Add class `TestSelfGuard` to `tests/test_startup_readiness.py`: listener pre-filled (`CuemsAvahiListener(ip=…)` then `.nodes[...] = Node(...)`) with a node at our IP carrying a **foreign** uuid; `retreive_local_node()` with `TimeoutLoop` patched to two iterations: (a) when a matching-uuid node appears on the second iteration it is returned and a WARNING named both uuids; (b) when none appears, `TimeoutError` propagates and `run()`'s handler exits with a critical line naming both uuids and the words `restart cuems-nodeconf` (FR-013, research R5)
- [X] T020 [US2] Retarget the four `patch('shutil.copy2')` sites — `tests/test_node_role.py:47`, `tests/test_node_role.py:79`, `tests/test_integration.py:39` — to `patch.object(CuemsNodeConf, '_render_service_record', return_value=False)` and delete the comment at `tests/test_node_role.py:78`. **Setup only**: no test's subject or assertion changes; record that in the commit message (constitution testing gate). These fail until T022

### Implementation for User Story 2

- [X] T021 [US2] In `cuemsnodeconf/CuemsNodeConf.py` add `_load_identity()` → sets `self.settings_uuid`, `self.settings_mac` from `ConfigManager(config_dir=os.path.dirname(self.map_path), load_all=False).node_conf`; on `FileNotFoundError`, `PermissionError`, `SchemaError` (`from cuemsutils.errors import SchemaError` — public, measured) or either value equal to its sentinel: `Logger.critical('NOT PROVISIONED: …')` with the research R3 wording per case, then `sys.exit(-1)`. Add `_reload_avahi()` → `dbus.SystemBus()` → systemd manager `ReloadUnit('avahi-daemon.service', 'fail')`, `DBusException` logged at ERROR and swallowed. Add `_live_record_role()` → parse the first `node_role=` TXT value of `AVAHI_SERVICES_PATH + CUEMS_SERVICE_FILE` into `NodeRole`, `NodeRole.firstrun` on absence or `ValueError`
- [X] T022 [US2] In `cuemsnodeconf/CuemsNodeConf.py` add `_render_service_record(self, role) -> bool` per research R4: read `TEMPLATES_PATH + CUEMS_SERVICE_FILE + '.' + role.value` (`FileNotFoundError` → critical + exit); `count = template.count(SENTINEL_UUID.encode())`, zero → critical naming the path + exit; `rendered = template.replace(...)`; if the live file exists and `read_bytes() == rendered` → `return False`; else `tempfile.mkstemp(dir=AVAHI_SERVICES_PATH, prefix='.cuems.service.', suffix='.tmp')`, write, `os.chmod(0o644)`, `os.replace`, `Logger.info` naming role and uuid, `_reload_avahi()`, `return True`. Replace the bodies of `_install_master_service_template()` and the node branch of `set_node_role()` with one call each (`shutil` import stays for `change_network_settings_to_master`). T014–T015, T018, T020 pass
- [X] T023 [US2] In `cuemsnodeconf/CuemsNodeConf.py` `start()`: call `self._load_identity()` then `self._render_service_record(self._live_record_role())` **before** `self.set_comms()`, with a comment citing contract startup-order.md and why the order matters for the engine's probe. T016–T017 pass
- [X] T024 [US2] In `cuemsnodeconf/CuemsNodeConf.py` `retreive_local_node()`: match `node.get('ip') == self.ip and node.get('uuid') == self.settings_uuid`; when the IP matches but the uuid does not, `Logger.warning` once per iteration naming both; keep the loop's timeout. In `run()`'s `except TimeoutError` for this call, make the critical message name the announced uuid seen (if any), the settings uuid, and `restart cuems-nodeconf after re-provisioning; cuems-init-node --check shows the disagreement`. **Setup only** in `tests/test_service_discovery.py::test_retreive_local_node` (:32): `nodeconf.settings_uuid = <the uuid of the node it pre-fills>` with the feature-003 comment, no subject or assertion changed, listed in the commit. T019 passes; `tests/test_service_discovery.py` green
- [X] T025 [US2] Document the operator consequences in `README.md` under a new `## Node identity and the mDNS service record` heading: the record is rendered from `settings.xml` at every start and role change; after `cuems-init-node --force-new-identity` restart `cuems-nodeconf`; `cuems-init-node --check` exit 1 = live record disagrees, exit 3 = source is the sentinel and the daemon refuses to start with `NOT PROVISIONED`; the unit's restart limit turns that refusal into a settled `failed` unit (FR-014, research R12)

**Checkpoint**: a node announces only its provisioned identity, or nothing.

---

## Phase 5: User Story 4 — The consumers of the refusal know what to do with it (Priority: P2)

**Goal**: decision D and the two prohibitions are recorded where the consumer flows will find them.
No code in this repository or any consumer changes.

**Independent Test**: reviewing `contracts/readiness-response.md` and `plan.md` finds the decision, the
three rejected options and both prohibitions; `grep -rn "still starting up" ../cuems-engine ../cuems-editor` finds no code that interprets it.

- [X] T026 [P] [US4] Verify `specs/003-startup-readiness/contracts/readiness-response.md` states decision D, the three rejected alternatives with their costs, and both consumer prohibitions with their source paths (`cuems-engine` `specs/planning/xml-refactor/04-findings-new-to-this-pass.md` F2a; `cuems-editor` `specs/planning/xml-refactor/00-runnable-flow.md` §0a); correct anything missing (FR-008, FR-009)
- [X] T027 [P] [US4] Confirm neither consumer compensates: `grep -rn "starting up\|nodeconf.ipc" ../cuems-engine/src ../cuems-editor/src` shows only `cf5c4ad`'s existence probe and no string matching or retry; record the grep output and date in `specs/003-startup-readiness/research.md` under a new `## R14. Consumer check` (their T096 gate)
- [X] T028 [US4] Add a line to `CLAUDE.md`'s new "Start-up window" note (T013) naming the two consumer prohibitions and that `cuems-engine`'s `cf5c4ad` must not be reverted

**Checkpoint**: the decision is written down in three places that outlive this conversation.

---

## Phase 6: User Story 3 — The node's own map entry comes from the shared library (Priority: P3)

**Goal**: after discovery, the daemon's own record — carrying the `settings.xml` MAC — is seeded through
`NodeIndex.ensure`, by reference, before the role decision.

**Independent Test**: `.venv/bin/python -m pytest tests/test_self_seed.py tests/test_library_prerequisite.py -q`.

### Tests for User Story 3

- [X] T029 [P] [US3] Create `tests/test_self_seed.py` with class `TestSeedingTheOwnRow` using `cuems_conf_dir_empty` + a listener holding this node (uuid `…000000000001`, ip `169.254.1.1`, name-derived mac `controller._`): after the seeding step, `nodeconf.network_map` has one row keyed `2cf05d21cca3` (the fixture MAC), `row is nodeconf.node` (by reference), `nodeconf.node['mac'] == '2cf05d21cca3'` (Story 3 scenario 1, research R6)
- [X] T030 [P] [US3] Add class `TestNoDuplicateAfterTheFirstMerge` to `tests/test_self_seed.py`: seed, then `network_map.merge(listener.nodes)`; exactly one row carries the uuid, its key is still the settings MAC, `online is True` (research R6 "ordering with the first refresh")
- [X] T031 [P] [US3] Add class `TestSeedingIsANoOpWhenListed` to `tests/test_self_seed.py` using `cuems_conf_dir` (the populated map lists this node): `ensure` returns `False`, the map's row object is unchanged, `_map_write_pending` is not touched by the seed (Story 3 scenario 2)
- [X] T032 [P] [US3] Add `test_run_seeds_the_own_row_after_self_lookup` to `tests/test_self_seed.py` in the style of `tests/test_fresh_node_boot.py::TestRunSeedsExactlyOnce` (patch `get_ips`, `Zeroconf`, `start_avahi_listener`, `wait_for_local_service_registration`, `retreive_local_node` → a node dict, `_render_service_record`, and stop `run()` at `_should_resume_master` via a `_Stop` side effect): the row exists when the role decision is reached (contract startup-order.md step 10 before 11)

### Implementation for User Story 3

- [X] T033 [US3] In `cuemsnodeconf/CuemsNodeConf.py` `run()`, immediately after `self.node = self.retreive_local_node()` succeeds and before the `node_role == NodeRole.firstrun` check: `self.node['mac'] = self.settings_mac` with a comment citing constitution III and research R6, then `if self.network_map.ensure(self.node): Logger.info(...)`. No other insert path; `_seed_empty_map()` unchanged. T029–T032 pass

**Checkpoint**: the map's own-row rule lives in the library; the daemon supplies identity only.

---

## Phase 7: User Story 5 — The repository root carries no stale analysis, and the live backlog is triaged (Priority: P4)

**Goal**: one document relocated and annotated, three deleted, six live items dispositioned. Independent
of every code phase; may be done first.

**Independent Test**: `ls *.md` → `CLAUDE.md README.md`; `specs/planning/11-startup-analysis.md` opens with a
dated status table; `grep -n "write_network_map" cuemsnodeconf/*.py` → nothing.

- [X] T034 [US5] `git mv STARTUP_ANALYSIS.md specs/planning/11-startup-analysis.md` and prepend, after the SPDX header, a block `## Status — re-measured 2026-09-28 against 6f31a7a` containing (a) a table with one row per finding 1–12 and per runtime issue 1–5 with the status and evidence from `specs/planning/10-readiness-window.md` §5.2, and (b) the six dispositions from `specs/003-startup-readiness/spec.md` Story 5's table; leave the original text below unchanged except a one-line note that every line number in it is from 2026-09-17 and has moved (FR-017, FR-018)
- [X] T035 [US5] `git rm BUGFIX_NETWORK_MAP.md BUGFIX_COMPLETE.md DEPLOYMENT_STEPS.md`; the commit message states the measured reason (all three describe `write_network_map()`, which `grep -nE 'write_network_map|ElementTree|getroot' cuemsnodeconf/*.py` no longer finds; replaced by features 001/002 and `cuemsutils` T085–T090) and that `specs/001-network-map-object-adoption/tasks.md:133`'s reference is deliberately left as written (FR-017)
- [X] T036 [P] [US5] Add a row for `specs/planning/11-startup-analysis.md` to the index table in `specs/planning/README.md` (measured: it has one, with rows for 09 and 10 at :26 and :29), and update the "Status" line of `specs/planning/10-readiness-window.md` to `spec, plan and tasks written 2026-09-28 — see specs/003-startup-readiness/`

**Checkpoint**: `ls *.md` returns exactly two names.

---

## Phase 8: User Story 6 — The start-up window is bounded on purpose, and its neighbours are tidied (Priority: P5, polish — droppable)

**Goal**: the interface wait and the controller pause come from configuration with unchanged defaults;
a pre-flight names a missing system bus or avahi before anything else fails.

**Independent Test**: `.venv/bin/python -m pytest tests/test_startup_config.py -q`; with nothing set, the
suite's existing timing-dependent tests behave as before.

### Tests for User Story 6

- [X] T037 [P] [US6] Create `tests/test_startup_config.py` with class `TestConfiguredWaits`: with no env, `nodeconf._iface_timeout() == 10` and `_controller_pause() == 5`; with `monkeypatch.setenv('CUEMS_NODECONF_IFACE_TIMEOUT', '3')` → 3; `'abc'` or `'-1'` → default and a WARNING line; `get_ips()` passes the configured value to `TimeoutLoop` (patch `cuemsnodeconf.CuemsNodeConf.TimeoutLoop` and assert `timeout=` kwarg) (FR-023, SC-011)
- [X] T038 [P] [US6] Add class `TestPreflight` to `tests/test_startup_config.py`: with the `dbus.SystemBus` stub raising, `_preflight()` logs an ERROR containing `system bus` and returns; with the bus fine and the Avahi `Interface(...).GetVersionString` raising `DBusException`, logs an ERROR containing `avahi-daemon` and returns; neither raises; and a separate `test_preflight_runs_before_identity_and_socket` in the same class with its own `calls` list (`['preflight', 'render', 'set_comms']`) — T017's US2 test is not edited (FR-024)

### Implementation for User Story 6

- [X] T039 [US6] In `cuemsnodeconf/CuemsNodeConf.py` add `_iface_timeout()` and `_controller_pause()` (read the env var, `int()`, `>= 0`, else log and default; log the effective value once at start); use them in `get_ips()`'s `TimeoutLoop(timeout=…)` and at the controller `time.sleep(…)` (:252), keeping the existing justification comment. T037 passes
- [X] T040 [US6] In `cuemsnodeconf/CuemsNodeConf.py` add `_preflight()`: `dbus.SystemBus()` in a try (ERROR `pre-flight: system bus unreachable: …`, return); `dbus.Interface(bus.get_object('org.freedesktop.Avahi', '/'), 'org.freedesktop.Avahi.Server').GetVersionString()` in a try (ERROR `pre-flight: avahi-daemon not answering: …`); DEBUG on success with the version string. Call it first in `start()`. Never exits (research R7, R12). T038 passes
- [X] T041 [US6] Document both variables in `README.md` under `## Configuration`: name, default, what each bounds, and a systemd drop-in example (`systemctl edit cuems-nodeconf` → `[Service]` `Environment=CUEMS_NODECONF_IFACE_TIMEOUT=20`)

**Checkpoint**: the polish phase is complete, or explicitly dropped to a maintenance pass with a line in `research.md` R7 saying so.

---

## Phase 9: Polish, verification ledger and release

**Purpose**: the gates the constitution names, the hardware debt recorded, the packaged change announced.

- [X] T042 [P] Add entry `## 6. Feature 003 — the start-up refusal on the real dispatch path (added 2026-09-28)` to `specs/002-public-network-map-path/checklists/hardware-verification.md` before "Related records": `- [ ] **Not performed.**`, why it is here (constitution IV rules out the unit test as evidence), the steps from `specs/003-startup-readiness/quickstart.md` "On a node" item 4 (restart, click "add node" within seconds, expect *nodeconf is still starting up* on the settings page, retry after active → adopted), and the record format (FR-020, research R11)
- [X] T043 [P] Add two bullets to the `cuems-nodeconf (0.1.0-8) UNRELEASED` entry in `debian/changelog` (no new version): the start-up refusal with its exact string and that consumers relay it verbatim; the mDNS service record rendered from `settings.xml` with the `NOT PROVISIONED` refusal and the restart-after-re-mint rule. `dpkg-parsechangelog -l debian/changelog` still reports `0.1.0-8`
- [X] T044 Run the gates and record them in the final commit message: `./run-tests.sh` (expect 119 + ≈25 suite, 15 yardstick, zero skips: `pytest -q -rs` shows none), `cmp specs/planning/yardstick/test_nodeindex_characterization.py ../cuems-utils/tests/contract/test_nodeindex_characterization.py`, `git diff <T002 base> -- tests/test_engine_callback.py tests/test_adoption_flow.py tests/test_service_discovery.py tests/test_node_role.py tests/test_integration.py` (expect only the listed setup lines: `_ready = True`, `settings_uuid = …`, and the four retargeted patches; no `assert` line and no test body changed), `ls *.md` (expect two names), `grep -c "shutil.copy2" cuemsnodeconf/CuemsNodeConf.py` (expect 1: the interfaces copy only) (FR-019, SC-002, SC-003, SC-007)
- [X] T045 Run `specs/003-startup-readiness/quickstart.md` "The window, by hand" and the four targeted test commands; correct the quickstart where it is wrong
- [X] T046 Write `specs/003-startup-readiness/evidence/verification-record.md` in the style of `specs/002-public-network-map-path/evidence/verification-record.md`: what T044/T045 measured, with numbers and the commit; that hardware ledger §5 and §6 are **Not performed** (or performed, with the record); the constitution check re-affirmed post-implementation
- [X] T047 Mark the spec's checklist and this file's boxes; tick `specs/003-startup-readiness/checklists/requirements.md` "Feature Readiness" items only if T044 passed
- [ ] T048 **Maintainer only** — after merging the feature branch into `feat/xml-refactor` locally (fast-forward): re-cut `xml-refactor-merge-candidate` on the merge commit (`git tag -f -a -s`), push the tag, and announce the re-cut in one message to the `cuems-common`, `cuems-power-bridge` and `cuems-utils` flows (011's T080 records it); record the new commit in `specs/003-startup-readiness/evidence/verification-record.md` and in the memory note `xml-refactor-merge-coordination`. Never done by an agent (FR-021, research R10)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none. T001 gates Phase 6 only.
- **Foundational (Phase 2)**: after Phase 1. Blocks Phases 3, 4, 6, 8.
- **US1 (Phase 3)**: after Phase 2. No dependency on other stories. **MVP.**
- **US2 (Phase 4)**: after Phase 2. T017 depends on T023; T020 depends on T022. Independent of US1 (different methods), but both edit `CuemsNodeConf.py`, so sequence the commits.
- **US4 (Phase 5)**: after US1's T013 (it extends that note). Otherwise documents only.
- **US3 (Phase 6)**: after Phase 2 **and** US2's T021 (`settings_mac`) and T024 (the guarded lookup); T001 must have passed.
- **US5 (Phase 7)**: no code dependency; may run before Phase 2.
- **US6 (Phase 8)**: after US2's T023 (extends `start()`); droppable.
- **Release (Phase 9)**: after every story kept; T048 last, by the maintainer.

### Within each story

Tests first (they must fail), then the implementation task, then the documentation task.

### Parallel Opportunities

- Phase 2: T005, T006 in parallel; T007 after T006; T008 any time after T001.
- Phase 3: T009, T010, T011 in parallel, then T012.
- Phase 4: T014–T019 in parallel, then T021 → T022 → T023 → T024; T025 any time.
- Phase 6: T029–T032 in parallel, then T033.
- Phase 7: T034 and T035 in parallel with everything else; T036 after T034.
- Phase 8: T037, T038 in parallel, then T039, T040; T041 any time.
- Phase 9: T042, T043 in parallel.

---

## Parallel Example: User Story 2

```bash
# Tests, all in different classes/files, written together:
Task: "TestRender in tests/test_service_record.py"
Task: "TestRenderRefusals in tests/test_service_record.py"
Task: "TestUnprovisionedRefusesToStart in tests/test_service_record.py"
Task: "TestRenderHappensBeforeTheSocket in tests/test_service_record.py"
Task: "TestStartupRenderKeepsTheLiveRole in tests/test_service_record.py"
Task: "TestSelfGuard in tests/test_startup_readiness.py"
# Then, sequentially in cuemsnodeconf/CuemsNodeConf.py:
Task: "T021 _load_identity / _reload_avahi / _live_record_role"
Task: "T022 _render_service_record and the two role sites"
Task: "T023 start() order"
Task: "T024 retreive_local_node guard"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1, Phase 2 (T004 and T008 suffice for US1; T005–T007 can wait).
2. Phase 3 → `tests/test_startup_readiness.py` green, `tests/test_engine_callback.py` unchanged.
3. **Stop and validate**: the quickstart's "window by hand" prints the refusal.
   This alone closes the operator-visible defect and would be shippable on its own re-cut.

### Incremental Delivery

1. US1 (readiness) → US2 (identity) → US4 (decision recorded) → US3 (own row) → US5 (documents,
   any time) → US6 (polish, or drop) → Phase 9.
2. One packaged file changes across US1, US2, US3, US6, so one re-cut at the end covers all of them;
   shipping US1 alone would cost a second re-cut later (research R10, spec FR-021) — acceptable only
   if the maintainer asks for it.

### Minimal path

T001, T004, T008, T009, T012, T013 — six tasks — deliver US1 completely.

---

## Notes

- Every code task edits `cuemsnodeconf/CuemsNodeConf.py` and nothing else shipped; a task that needs
  a second shipped module is a constitution V question, stop and record it.
- The yardstick is run, never edited. If it fails, the port is wrong.
- Commits are GPG-signed; on `gpg failed to sign`, retry — never `--no-gpg-sign`.
- Hardware verification is stated, performed or not — never blank (ledger §5, §6).
