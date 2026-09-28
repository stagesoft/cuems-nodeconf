<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Implementation Plan: Start-up readiness

**Branch**: `003-startup-readiness` | **Date**: 2026-09-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-startup-readiness/spec.md`

## Summary

Make the daemon say what state it is in. Between binding its request socket and loading the cluster
map it answers adopt and unadopt requests with `nodeconf is still starting up` instead of a false
"Node not found" (R1); the consumers relay that string verbatim (decision D). Before the socket
exists it derives the identity it announces from `settings.xml`, rendering the role template over the
sentinel into `/etc/avahi/services/cuems.service` atomically and reloading avahi only when the bytes
changed, and it refuses to start at all when the node is unprovisioned (R3, R4). After discovery it
insists the entry found at its own IP carries that uuid (R5), then seeds its own row through the
library's `NodeIndex.ensure`, which already exists in `cuems-utils` at **`73daab6`** (R6). The
interface wait and the controller's pause become configured values with unchanged defaults, and a
pre-flight names a missing bus or avahi before anything else fails (R7). The four root-level analysis
documents are resolved: one relocated and annotated, three deleted (R9). One packaged file changes,
so the candidate is re-cut once and announced (R10).

Phase 0 ([research.md](research.md)) measured three things that shape this plan:

- **R6** — `NodeIndex.ensure` is not a future dependency: it is in the sibling checkout, visible to
  `.venv`, and the yardstick file was untouched by the commit that added it. The suite passes (119)
  and the yardstick (15) with it installed.
- **R3** — the sentinel constant lives in an internal library module; the daemon carries the two
  literals itself and pins them by test, keeping the public-paths rule intact.
- **R12** — the unit `Requires=avahi-daemon.service`, so the pre-flight is a diagnostic, not a race
  guard; and `Restart=on-failure` with a five-try limit is what an unprovisioned refusal settles into.

## Technical Context

**Language/Version**: Python 3.11 (`python3 (>= 3.11)` in `debian/control`).

**Primary Dependencies**: `cuemsutils (>= 0.1.0rc16, << 0.1.1~)` through public paths only
(`cuemsutils.tools.ConfigManager`, `cuemsutils.tools.NodeList.NodeIndex`, `cuemsutils.log`);
**requires a build at `73daab6` or later** for `NodeIndex.ensure` — the version string cannot say so,
hence the prerequisite test (R6). `python3-zeroconf`, `python3-dbus`, `python3-systemd`,
`python3-netifaces` from the system; `avahi-daemon`. `cuems-common ≥ 1.3.0-23` for templates carrying
the sentinel (already gated by the existing mutual `Breaks`). Pins do **not** move.

**Storage**: `/etc/cuems/settings.xml` (read; `cuems-init-node`'s), `/etc/cuems/network_map.xml`
(read/written as before), `/etc/avahi/services/cuems.service` (**written**, sole writer, `0644`),
`/usr/share/cuems/cuems.service.{controller,node,firstrun}` (read; `cuems-common` package content).

**Testing**: `pytest` via `./run-tests.sh` — the suite (119 at baseline) and the vendored yardstick
(15), two invocations. Four new test files, one test added to the prerequisite module, setup-only
changes at the four `shutil.copy2` patch sites, in the tests that build a map without start-up
(`_ready = True`) and in the self-lookup test (`settings_uuid`) (R8).

**Target Platform**: Debian bookworm nodes; `cuems-nodeconf.service` (`Type=notify`,
`Requires=avahi-daemon.service`, `TimeoutStartSec=60`, `Restart=on-failure`, start limit 5 in 33 s),
running as **root** (R12).

**Project Type**: single Python package, a systemd daemon; no frontend in this repository.

**Performance Goals**: none specific. Added start-up cost before the socket: one settings load, one
template read, one byte compare, at most one atomic write and one avahi reload; inside the 60 s start
window `run()` already spends up to 35 s of.

**Constraints**: the response shape is a UI contract (constitution IV); readiness only after both
halves of the map (spec FR-002); no lock (FR-007); render before the socket (FR-010); no daemon-side
seed (FR-015); no new responsibility (constitution V); no library change; yardstick untouched.

**Scale/Scope**: one class touched (`CuemsNodeConf`), one new module-level constant block, one new
helper, three call sites replaced, two guards, ≈ 25 new tests, four documents moved or deleted, one
ledger entry added, two changelog bullets, one re-cut.

## Constitution Check

*GATE: checked before Phase 0, re-checked after Phase 1 design.*

| Principle | Gate | Verdict |
|---|---|---|
| **I. Root privilege is correctness** | Every file a root process creates for another process's use has its mode decided, stated and tested | **PASS with two explicit requirements.** The rendered record is read by `avahi-daemon` as user `avahi`: written `0644`, atomically, pinned by a test that sets a `0077` umask first (R4, the discipline `_seed_empty_map` already follows). The socket's `0666` is unchanged. No other filesystem object is created |
| **II. The output is a file other services read** | Complete-or-absent writes; never write when unchanged | **PASS.** Two files, both governed: the record is written only when its bytes differ and always through `os.replace` (R4); the map's write path is untouched — `ensure` inserts into the in-memory index and the existing signature gate decides the next write. The `<online>` semantics are untouched: `ensure` does not set it, `merge` does, as today |
| **III. Identity is keyed by UUID** | No name-derived identity key in merge or adoption | **PASS, and strengthened.** The self guard compares uuids (R5); the seeded row carries the `settings.xml` MAC instead of the listener's name-derived label (R6), which also makes the controller's row findable by key. `ensure` matches by uuid |
| **IV. RPC responses are a UI contract** | Shape unchanged; every request answered; verified end to end | **PASS in shape; end-to-end DEFERRED to the ledger, not silent.** One new error *value*, no new key; only `nodelist_modify` is gated, every other request answers as today (R1, contract). The 16 engine-callback tests pass with no subject or assertion changed — the tests that build a map without running start-up gain one setup line asserting readiness, listed in the commit (spec FR-004). The real-dispatch-path check needs a controller with the UI: ledger **§6** (R11) records it as owed |
| **V. No eleventh responsibility** | Nothing added beyond the ten; atomization basis stays valid | **PASS.** Readiness, the configured waits and the pre-flight are lifecycle; the render replaces three template copies in the existing Avahi-service-template responsibility with one helper; the guard and the seed are node identity, which the daemon owns (R13). The basis' row for templates shrinks; no row is added |
| **VI. Boot ordering is product behaviour** | Ordering reasoned explicitly; correct whether it wins or loses | **PASS — this is the feature.** The order is a contract ([contracts/startup-order.md](contracts/startup-order.md)) with the answer at every step; no timing yields "not found" for a present node (R2). The self guard waits out a stale record rather than exiting on first sight (R5). The pre-flight does not exit, because the unit already orders avahi first (R7, R12). Readiness never reverts |
| **Scope** | No new plumbing; `dhcpd`/`dhclient`/`hostapd` untouched | **PASS.** The `/etc/network/interfaces` path is not touched; writing an mDNS service record is the existing template responsibility, not plumbing |
| **Domain logic lives in `cuemsutils`** | No ad-hoc reimplementation | **PASS.** The own-row rule is `NodeIndex.ensure`, consumed not reimplemented (D2); no daemon-side fallback insert (R6) |
| **Public import paths only** | | **PASS.** `ConfigManager` and `NodeIndex` only; the sentinel is a local literal, not an import from `cuemsutils.xml` (R3) |
| **Dependency pins are bounded** | Floor + ceiling agreeing across both files | **PASS — unchanged.** `>= 0.1.0rc16, << 0.1.1~` in both; `Breaks: cuems-common (<< 1.3.0-23~)` already gates the templates. The `73daab6` requirement is expressed by test (R6), the same way 002 expressed `e363d03` |
| **Coordinated wire changes are atomic** | | **PASS.** No TXT vocabulary change. The sentinel-carrying templates and this render land in one coordinated re-cut with `cuems-common`'s handover (R10) |
| **Testing gate** | Suite green, no unjustified skips, adopt/unadopt coverage not reduced; hardware verification stated | **PASS.** ≈ 25 tests added, none skipped; pre-existing tests change setup only (readiness and `settings_uuid` lines, listed), never subject or assertion; ledger §5 and §6 state what is owed on hardware (R11) |
| **Characterization tests are a measurement** | Yardstick run, never edited | **PASS.** Untouched here and untouched by `73daab6` upstream; the quickstart diffs it |
| **Measure, do not transcribe** | | **PASS.** Every coordinate in research.md was re-measured on 2026-09-28; the one the brief got wrong — the tag being local-only — is corrected (R10) |

**Post-Phase-1 re-check**: no new violations. The design adds no module, no dependency and no
responsibility. Two filesystem behaviours are new (the record write; the environment-variable read)
and both are governed above.

## Project Structure

### Documentation (this feature)

```text
specs/003-startup-readiness/
├── plan.md              # This file
├── spec.md              # Feature specification (clarifications D and B encoded)
├── research.md          # Phase 0 — R1..R13
├── data-model.md        # Phase 1 — readiness state, identity, record, own row, configuration
├── quickstart.md        # Phase 1 — how to validate, by hand and on a node
├── contracts/
│   ├── readiness-response.md    # the refusal over /tmp/nodeconf.ipc and decision D
│   ├── service-record-render.md # settings.xml → /etc/avahi/services/cuems.service
│   └── startup-order.md         # the ordered steps and the answer at each (constitution VI)
├── checklists/
│   └── requirements.md          # spec quality checklist (all items pass)
└── tasks.md             # Phase 2 — NOT created by /speckit-plan

specs/002-public-network-map-path/checklists/hardware-verification.md
                         # §5 exists (identity); §6 added by this feature (readiness, real dispatch path)
specs/planning/11-startup-analysis.md
                         # relocated from STARTUP_ANALYSIS.md, dated, status per finding
```

### Source Code (repository root)

```text
cuemsnodeconf/
├── CuemsNodeConf.py     # the only shipped file this feature edits:
│                        #   constants   -> SENTINEL_UUID, SENTINEL_MAC, AVAHI_SERVICES_PATH,
│                        #                  the two env-var names and defaults
│                        #   __init__    -> self._ready = False
│                        #   start()     -> pre-flight; load identity or refuse; render; then set_comms(); run()
│                        #   engine_callback()   -> the readiness gate on nodelist_modify
│                        #   read_network_map()  -> self._ready = True as its last statement
│                        #   get_ips()   -> timeout from configuration
│                        #   run()       -> controller pause from configuration; guard + ensure after retreive_local_node
│                        #   retreive_local_node() -> match by ip AND provisioned uuid; wait out a stale record
│                        #   _render_service_record(role) -> NEW helper (R4)
│                        #   _install_master_service_template(), set_node_role() node branch
│                        #               -> call the helper instead of shutil.copy2
├── CuemsAvahiListener.py, AliasPublisher.py, communicate.py,
└── AvahiTool.py, CuemsConfServer.py, run_nodeconf.py     # untouched

tests/
├── fixtures/etc_cuems/
│   ├── settings.xml, network_map.xml, network_map_empty.xml   # existing
│   ├── settings_sentinel.xml                                  # NEW — the unprovisioned shape
│   └── avahi/cuems.service.{controller,node,firstrun}         # NEW — templates carrying the sentinel
├── conftest.py                       # a fixture pointing TEMPLATES_PATH / AVAHI_SERVICES_PATH at tmp_path
├── test_startup_readiness.py         # NEW — the window, the half-built state, the self guard
├── test_service_record.py            # NEW — render, refusals, ordering before the socket
├── test_self_seed.py                 # NEW — ensure by reference, no duplicate after merge
├── test_startup_config.py            # NEW — env vars, pre-flight logging
├── test_library_prerequisite.py      # one test added: NodeIndex.ensure present and by-reference
├── test_node_role.py, test_integration.py   # setup only: 4 shutil.copy2 patches retargeted
├── test_engine_callback.py, test_adoption_flow.py   # setup only: `_ready = True` where start-up is bypassed
└── test_service_discovery.py         # setup only: `settings_uuid` set for the guarded self lookup

debian/changelog                      # two bullets inside 0.1.0-8 UNRELEASED
README.md                             # the two environment variables; the restart-after-re-mint rule
specs/planning/yardstick/             # run, never edited

removed:  BUGFIX_NETWORK_MAP.md  BUGFIX_COMPLETE.md  DEPLOYMENT_STEPS.md
moved:    STARTUP_ANALYSIS.md -> specs/planning/11-startup-analysis.md
```

**Structure Decision**: single Python package, unchanged. One shipped module edited, no module added
(constitution V). Tests follow the existing flat `tests/` layout and fixture directory.

## Design decisions

| | Decision | Why, and what was rejected |
|---|---|---|
| **D1** | Readiness is a flag set as the last statement of `read_network_map()`, gating only the adopt/unadopt branch | R1. A lock does not fill an empty index; delaying the socket hands the operator the engine's "enable it" message for a running daemon; a readiness action would change the contract |
| **D2** | `set_comms()` stays first; only the provisioning check and the render move ahead of it | R2/R3. The spec settled "socket exists, daemon answers honestly"; the render must precede the socket so an unprovisioned node never looks available |
| **D3** | Unprovisioned = absent, unreadable, invalid, or either sentinel; `NOT PROVISIONED` leads the message; exit non-zero | R3. Same token as `cuems-init-node --check`; the library's absent-vs-corrupt distinction kept after the token; the unit's restart limit turns the exit into a settled `failed` |
| **D4** | The sentinel literals live in the daemon and are pinned by test | R3. The library's constant is in an internal module; public paths only. A public re-export upstream is welcome, not required |
| **D5** | One render helper: literal substitution, require ≥ 1 sentinel, write-if-changed, atomic `0644`, reload-if-changed via the D-Bus systemd manager | R4. Rejected: regex over any uuid (would launder a real identity); XML re-serialisation (breaks byte equality) |
| **D6** | The start-up render keeps the live record's role (`firstrun` if none); role changes render at the two remaining sites | R4. Role decisions stay where they are; the start-up render only corrects the uuid |
| **D7** | Self lookup matches by IP **and** uuid, waits out a stale record, exits on timeout naming both | R5. Exiting on first sight loses the race against avahi's reload |
| **D8** | Replace the own record's `mac` with `settings.xml`'s, then `ensure` — before the role decision | R6. The listener's MAC is a label (constitution III); `merge` never clobbers the key afterwards; `_should_resume_master` benefits |
| **D9** | The `73daab6` requirement is a test, not a pin | R6. `0.1.0rc16` cannot express it; the pattern 002 set for `e363d03` |
| **D10** | Two environment variables with the current defaults; pre-flight logs and proceeds | R7/R12. `settings.xml` is the library's schema; the unit already `Requires=avahi-daemon` |
| **D11** | Ledger §6 is added for the readiness half; §5 stays the identity half | R11. Constitution IV's end-to-end check is a different check from 011's `--check` |
| **D12** | Move-and-annotate `STARTUP_ANALYSIS.md`; delete the three; leave 001's reference | R9, brief §5.4 option 1 |

## Complexity Tracking

> No constitution violations. Nothing to justify.

Two judgement calls worth recording: **D8 mutates the listener's node dict** (its `mac`) before
seeding — accepted because that dict *is* the daemon's own record by the aliasing contract, the value
is the node's true identity, and the alternative (a second dict for the seed) would break the
by-reference rule `ensure` exists to honour. **D10 reads environment variables in a daemon that
otherwise has no configuration surface** — accepted because the alternative is a schema change in
another repository for two integers.

## Dependencies and sequencing

| Depends on | State | Effect if missing |
|---|---|---|
| `cuems-utils` `73daab6` (`NodeIndex.ensure`) | present on branch `011-etc-cuems-first-install`; installed in `.venv` | the prerequisite test fails; Story 3 cannot land; Stories 1, 2, 4, 5, 6 can |
| `cuems-common` templates with the sentinel (`1.3.0-23`, 011 handover §4) | **not yet in `cuems-common` `feat/xml-refactor` (`3af31cc`)** — the checkout's templates still carry the production uuid | on a node: the render refuses (zero sentinels) and the daemon exits; in the suite: fixtures carry the sentinel, so nothing blocks. The coordinated landing is what makes both sides true at once |
| Ledger §5 | written 2026-09-28 | — |
| Decision D (consumers) | taken 2026-09-28 | no consumer code changes |

Order of work for `/speckit-tasks`: Story 5 (documents) first, independent; then Stories 1, 2 and 3
on the daemon; then Story 6 (polish, droppable to a maintenance pass per FR-025); then docs,
changelog, ledger §6; the re-cut last and by the maintainer.
