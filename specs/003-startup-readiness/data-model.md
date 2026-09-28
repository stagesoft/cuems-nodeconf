<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Data model — feature 003, start-up readiness

The entities the spec names, with their fields, rules and transitions. Research references are to
[research.md](research.md).

## 1. Readiness state

| Field | Type | Value |
|---|---|---|
| `_ready` | bool on the daemon instance | `False` from construction; `True` after the map is loaded |

**Transition.** Exactly one: `False → True`, as the last statement of `read_network_map()`, after
**both** `_document` and `network_map` are assigned (R1). Never reset. A load that raises leaves it
`False`.

**Consumers.** The `nodelist_modify` branch of `engine_callback` only. Written by the main thread,
read by the comms thread; a stale read yields the conservative answer.

## 2. Engine request and response (unchanged shape)

| Direction | Shape |
|---|---|
| request | `{'action': str, 'value'?: str, 'modify_action'?: 'ADD' \| 'REMOVE'}` |
| response | `{'OK': bool, 'error'?: str}` |

**New error value, while `_ready` is `False` and `action == 'nodelist_modify'`:**
`'nodeconf is still starting up'`. Every other request keeps today's answer. See
[contracts/readiness-response.md](contracts/readiness-response.md).

## 3. Provisioned identity

| Field | Source | Rule |
|---|---|---|
| `uuid` | `settings.xml` → `ConfigManager(...).node_conf['uuid']` | schema-required; must not equal the sentinel uuid |
| `mac` | `settings.xml` → `node_conf['mac']` | schema-required; must not equal the sentinel MAC |

**Sentinels** (module constants in the daemon, pinned by test to the 011 contract; R3):
`SENTINEL_UUID = '00000000-0000-0000-0000-000000000000'`, `SENTINEL_MAC = '000000000000'`.

**States.** *Provisioned* (both present, neither sentinel) → the daemon proceeds. *Unprovisioned*
(file absent, unreadable, invalid, or either field sentinel) → `NOT PROVISIONED …`, exit non-zero
before any socket or record. Read once at start; the identity does not change during a run — an
operator who re-mints restarts the daemon (spec FR-014).

## 4. mDNS service record

| Field | Value |
|---|---|
| template | `/usr/share/cuems/cuems.service.<role>` for `role ∈ {controller, node, firstrun}` — `cuems-common` package content, never written |
| rendered bytes | template bytes with every occurrence of `SENTINEL_UUID` replaced by the provisioned uuid (≥ 1 occurrence required, else refuse) |
| live file | `/etc/avahi/services/cuems.service`, mode `0644`, owner root, written atomically |
| changed | `rendered != current live bytes` — the only condition under which the file is written and avahi reloaded |

**Role at start-up.** Parsed from the live file's `node_role=` TXT record; `firstrun` when the file is
absent or unparseable. The start-up render never changes the role, only the uuid (R4).

**Transitions.** Rendered at start (before the socket), and at each role decision: controller
(election or resume) and node. See [contracts/service-record-render.md](contracts/service-record-render.md).

## 5. Own node record

The listener's `node` dict for the entry discovered at this daemon's IP (`retreive_local_node`).

| Field | After this feature |
|---|---|
| `uuid` | must equal the provisioned uuid, or the daemon refuses (R5) |
| `mac` | **replaced** with the provisioned MAC before seeding; the listener's value is a name-derived label, not identity (R6) |
| `node_role`, `ip`, `name`, `adopted`, `online` | as discovered |

**Seeding.** `network_map.ensure(self.node)`: inserts this very dict by reference when no row carries
its uuid; no-op otherwise. Later `merge` passes refresh it in place and never clobber `mac`.

## 6. Start-up configuration

| Variable | Type | Default | Governs |
|---|---|---|---|
| `CUEMS_NODECONF_IFACE_TIMEOUT` | seconds, int ≥ 0 | 10 | the interface wait, which bounds the readiness window |
| `CUEMS_NODECONF_CONTROLLER_PAUSE` | seconds, int ≥ 0 | 5 | the controller's pause before its first discovery pass |

Invalid values fall back to the default with a log line. Read once at start; logged (R7).

## 7. Pre-flight report

One log line per dependency checked before the socket exists: system bus reachable? avahi server
answering? Failure is named, not fatal; avahi gets one start attempt through the existing recovery
path (R7).

## 8. Start-up analysis document

`specs/planning/11-startup-analysis.md` (moved from the root): the original text, headed by a
measurement date and a status table — one row per finding (12) and per runtime issue (5) — matching
the brief's §5.2 and this feature's dispositions (spec Story 5). The three sibling documents are
deleted (R9).
