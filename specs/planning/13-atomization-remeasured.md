<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->
> **Updated 2026-10-14**: rows 3 and 10 changed (foreign-controller scoping `155fe6c`, `node_set` `3d3601d`); line numbers below are from 2026-10-13 and have moved.

<!-- REPO-ORIGINAL — not vendored. Written 2026-10-13 against feat/xml-refactor @ 80c1d5d
     (CuemsNodeConf.py = 1091 lines). Re-measure before relying on any coordinate here. -->

# The atomization basis, re-measured — and the obligations added since

`01-atomization-basis.md` is the vendored ten-row inventory from `cuems-utils` feature 008,
measured on a 756-line class. The class is now **1091 lines**. Features 001–003 implemented two rows
and added responsibilities the table does not have, and `cuems-utils` has since assigned this
repository work that no row holds. This file is the current basis. It does **not** edit `01`; the two
are read together, and `cuems-utils`' own copy (`specs/planning/nodeconf-atomization.md`) is out of
date in the same way.

**This repository now owns its atomization basis.** `cuems-utils`'
`hardware-outputs-capability-layer.md` §3 names `nodeconf-atomization.md` as *"the natural place to
state where a probe/transcribe responsibility sits among its ten"*, but the work is ours. Upstream's
copy should become a pointer here rather than a second copy that drifts.

## 1. The ten rows, re-measured

| # | Responsibility | Methods today | State |
|---|---|---|---|
| 1 | Daemon lifecycle | `start` :161, `stop` :133, `run` :433, `_run_worker_loop` :654, `notify_systemd` :687, `_configured_seconds`/`_iface_timeout`/`_controller_pause` :177–195 | Unchanged in role. Owns the start-up order (`contracts/startup-order.md`, feature 003) |
| 2 | Network interface discovery | `get_ips` :691 | **Interface names still hard-coded** (`bridge0:avahi`, `ethernet1:avahi`, `bond0`). `origin/rc_1`'s `141cf1f` (a static link-local cluster address) is being ported in step 0c |
| 3 | Avahi/mDNS listener orchestration | `start_avahi_listener` :727, `on_node_event` :681, `callback` :908, `check_nodes` :913, `wait_for_local_service_registration` :928, `retreive_local_node` :944 | `check_first_run` deleted (`80c1d5d`). **Gains `_cluster`** (`155fe6c`): computes this host's cluster controllers with the library and logs the foreign ones; the filtering and removal happen in `refresh(cluster=)` (D22) |
| 4 | Node role election | `set_node_role` :757, `_should_resume_master` :732, `_live_record_role` :263 | Still first-come, with no protocol. **Runtime issue 5** (`11-startup-analysis.md`) is open and is its own feature |
| 5 | Network-map domain/config logic | `refresh_network_map` :526, `_network_map_document` :566, `_index_from_document` :646, `_save_network_map` :782, `adopt_node` :804, `unadopt_node` :827, `_find_node` :801, `read_network_map` :849 | **Done** (D22). What is left here is thin orchestration over `NodeIndex`/`CuemsNetworkMapType` |
| 6 | OS network reconfiguration | `change_network_to_master` :1041, `change_network_settings_to_master` :1083 | Unchanged. Still the daemon's most destructive path (`CLAUDE.md`) |
| 7 | Avahi service record | `_render_service_record` :303, `_install_master_service_template` :753, `_reload_avahi` :286 | **Changed in kind.** Feature 003 replaced the file copy with a render from `settings.xml` (the identity), so it now depends on row 11 |
| 8 | mDNS alias publishing | `publish_aliases_if_master` :984, `_ui_alias` :975 | Unchanged |
| 9 | Master lock file | `update_master_lock_file` :1024 | Unchanged |
| 10 | Engine IPC dispatch | `set_comms` :363, `engine_callback` :368 | **Done as a thin translator** (001). Gained the readiness refusal (003). **Gained `node_set`** (`3d3601d`): `_node_set` validates, `alias_node` delegates to `NodeIndex.set_alias` |

## 2. Rows the inventory does not have

| # | Responsibility | Where | State |
|---|---|---|---|
| 11 | **Provisioning and start-up identity** | `_preflight` :199, `_load_identity` :235, `_refuse_unprovisioned` :224, `_seed_empty_map` :610, `_seed_own_row` :586, and the `_ready` flag | **Exists** (003). A single-class candidate: its inputs are `settings.xml` and the map path, and its outputs are `settings_uuid`/`settings_mac` plus a seeded row |
| 12 | **OS identity chain** | — | **Planned, not in source.** `role_id` assignment on adoption, hostnamectl, `/etc/hosts`, `avahi-daemon.conf`, and the `cuems-nodeconf apply-identity [--check]` CLI. The contract is `cuems-common/docs/node-identity-contract.md`. It is a **second OS-touching path** beside row 6, so `CLAUDE.md`'s "exactly one path" sentence changes when it lands |
| 13 | **Hardware probe → `hardware_outputs.xml`** | — | **Assigned to this repository 2026-10-12** (`cuems-utils` `hardware-outputs-capability-layer.md` §3). Discovery owns the probed port inventory. Prior art: `CuemsHwDiscovery.py` on `origin/main` (`c6ccc7b`, 2026-06-01, a 299-line prototype using jack and Xinerama). It imports the deleted `CuemsNode` and `XmlReaderWriter` and will not run on this branch, so it is input for the feature, not code to merge |
| 14 | **`display.conf` transcription** | — | **Assigned to this repository**, same source. It reads `/run/cuems/display.conf`, which `cuems-common`'s `cuems-generate-display-conf` writes when videocomposer starts, and records the geometry. Rows 13 and 14 never write the same element, so there is still only one writer per element (F1). Open: refresh on every start or only on change (upstream §7.4) |

**The obligation in rows 13–14 is recorded here as accepted.** That removes the gate upstream §5
names (*"`cuems-nodeconf` acquiring the obligation — hard, and it is the real gate"*). It does not
schedule the work: upstream also needs its structure pass and a public `ConfigManager` accessor,
and `cuems-common` must agree to a second reader of `display.conf`.

**Prerequisite that neither document states:** rows 13–14 are per-node, but this daemon is
enabled only on the formitgo controller. Enabling it on every node (ledger §5 in
`specs/002-public-network-map-path/checklists/hardware-verification.md`) comes first.

## 3. Candidates, revised

| Row | Candidate? | Change from `01` |
|---|---|---|
| 2 | **Yes** | Should take its interface names from configuration while it moves |
| 3 | **Yes** | Now includes the foreign-controller filter, which is a pure function of `discovered` and this cluster's controller uuids |
| 4 | Partial | Unchanged. The collaborators to pass in are rows 3, 6, 7 — and later, the election protocol |
| 7 | **Yes, behind row 11** | It needs the provisioned uuid passed in |
| 11 | **Yes** | New |
| 12–14 | Born as their own classes | New code should not be added to `CuemsNodeConf` first and extracted later |
| 1, 10 | No | Unchanged reasoning |

## 4. Constraints carried forward

- D22: map mutations happen in `cuems-utils`, never here. Row 3's filter only narrows what is
  *passed in*. Removing a node already saved in the map is a library call (see
  `specs/upstream-reports/foreign-controller-scoping.md`).
- `01`'s `project_mappings` constraint still holds and now applies to row 13: hardware data
  reaches this daemon as its own domain object through `ConfigManager`, never on `NodeIndex`'s node.
- **D23 bound feature 010 only.** A dedicated atomization feature needs the maintainer to lift it
  explicitly. Not done yet.
