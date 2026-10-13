<!-- VENDORED from cuems-utils@b7598d5 specs/planning/nodeconf-atomization.md
     Stale feature number 009 -> 010 corrected. Do not edit to diverge. -->

> **Status (2026-10-13): STILL THE BASIS, BUT OUT OF DATE — rows 5 and 10 are done and the class has grown responsibilities this table does not list. Read `13-atomization-remeasured.md` with it.** See `README.md` for the index.

# `cuems-nodeconf` atomization basis (T051)

Written as the target-design basis for a **future, dedicated `cuems-nodeconf` feature** — this
feature (008) does not execute the split. Only row 5 (network-map domain/config logic) moves,
into `cuems-utils` (`data-model.md` §5, `tests/contract/test_nodeindex_characterization.py`). Rows
1–4 and 6–10 stay exactly where they are, in `cuemsnodeconf/CuemsNodeConf.py`.

## The ten responsibilities

Reproduced from `specs/planning/xml-rebuild/xml-rebuild-08-extension-audit.md` §4 (E11), the
audit's own catalog of `CuemsNodeConf` (756 lines, one class, as of that audit) — carried forward
here as the record this feature's decision (row 5 only, D22/D16) was made against.

| # | Responsibility | Representative methods |
|---|---|---|
| 1 | Daemon lifecycle | `start`, `stop`, `run`, `_run_worker_loop`, `notify_systemd` |
| 2 | Network interface discovery | `get_ips` (hardcoded interface names `bridge0:avahi`, `ethernet1:avahi`, `bond0`) |
| 3 | Avahi/mDNS listener orchestration | `start_avahi_listener`, `on_node_event`, `callback`, `check_nodes`, `check_first_run`, `wait_for_local_service_registration`, `retreive_local_node` |
| 4 | Node role election | `set_node_role`, `_should_resume_master` |
| 5 | **Network-map domain/config logic** (moved, this feature) | `read_network_map`, `write_network_map`, `refresh_network_map`, `merge_discovered_nodes`, `set_master_always_adopted`, `check_missing_adopted_nodes`, `adopt_node`, `unadopt_node`, `_map_signature` |
| 6 | OS network reconfiguration | `change_network_to_master`, `change_network_settings_to_master` (dbus `StopUnit`/`StartUnit` on `networking.service`/`avahi-daemon.service`, copies `/etc/network/interfaces`) |
| 7 | Avahi service-template file management | `_install_master_service_template`, the inline slave-template copy in `set_node_role` |
| 8 | mDNS alias publishing | `publish_aliases_if_master`, `_ui_alias` |
| 9 | Master lock file | `update_master_lock_file`, part of `_should_resume_master` |
| 10 | Engine IPC dispatch | `set_comms`, `engine_callback` (routes `nodelist_modify` ADD/REMOVE to `adopt_node`/`unadopt_node`) |

## Which rows are single-class candidates, and why

A row is a **single-class candidate** if its methods share state that nothing outside the row
reads or writes, and it has no hidden dependency on another row's internals beyond a narrow,
nameable interface.

| Row | Candidate? | Why |
|---|---|---|
| 1 (lifecycle) | No, stays a coordinator | Owns the other nine rows' start/stop ordering by construction — collapsing it into another row would just relocate the coordination, not remove it. |
| 2 (interface discovery) | **Yes** | `get_ips` reads only `netifaces` and writes only `self.ip`/`self.controller_ip`/`self.cluster_iface`/`self.ui_iface`. A `NetworkInterfaces` value object (or a function returning one) has no other row's state in it. |
| 3 (Avahi orchestration) | **Yes**, mostly | `start_avahi_listener`/`on_node_event`/`check_nodes`/`check_first_run` operate on `self.listener.nodes` (already a `NodeIndex`) and the zeroconf/browser objects. `wait_for_local_service_registration`/`retreive_local_node` are pure over `self.listener.nodes` + `self.ip` — extractable functions once `self.ip` is passed in rather than read off `self`. |
| 4 (role election) | Partial | `set_node_role` reads row 3's discovered controllers (`self.listener.nodes.controllers`) *and* triggers row 6 (`change_network_to_master`) *and* row 7 (`_install_master_service_template`). A single class here would need those three as injected collaborators, not a free extraction. |
| 5 (network-map domain) | **Yes — done** | This feature's own evidence: it split cleanly into `NodeIndex`/`CuemsNetworkMapType` with discovery passed in as a plain argument (research R7), and the characterization tests pin the boundary. |
| 6 (OS network reconfig) | **Yes** | `change_network_to_master`/`change_network_settings_to_master` touch only dbus/systemd and `/etc/network/interfaces`; no other row's state. |
| 7 (service-template files) | **Yes** | Pure file-copy from `TEMPLATES_PATH` to `/etc/avahi/services/`, parameterized by role. |
| 8 (alias publishing) | **Yes** | `publish_aliases_if_master`/`_ui_alias` need `self.node`, `self.ip`/`self.controller_ip`/`self.cluster_iface`/`self.ui_iface` (row 2's outputs) as inputs, and own `self.alias_publisher`'s lifecycle. Clean once row 2's outputs are passed in rather than read off `self`. |
| 9 (master lock file) | **Yes** | One function of `node_role` and a path. Already nearly pure. |
| 10 (engine IPC dispatch) | No, stays thin | `engine_callback` should become a **thin translator**: parse the RPC, call row 5's `NodeIndex.adopt`/`unadopt`, translate the `bool` back into the day's `{'OK', 'error'?}` shape (see `migration-guide.md`'s T052 entry for exactly what that translation has to reconstruct). Not a class of its own so much as the seam between the IPC transport and row 5. |

## Accounting for the live UI at the end of row 5's dispatch chain (E14)

Row 10's `engine_callback` is not dead code with no caller: `nodelist_modify` originates in
`cuems-frontend/src/app/components/settings/settings.component.ts`'s `confirmAddNode`/
`confirmRemoveNode`, a real UI operators use today (E20). Whatever atomization row 5 or row 10
undergo, the chain `nodelist_modify` → `engine_callback` → adopt/unadopt must keep working end to
end — this is exactly why 008 characterized row 5's behaviour before moving it (E23) rather than
re-deriving it from the schema, and it is why a future split of row 10 cannot be scoped as "delete
and rewrite": the RPC response shape (`{'OK': bool, 'error'?: str}`) is a contract with a live
Angular component, not an implementation detail free to change silently.

## The `network_map`/`project_mappings` entanglement

Row 5's atomization must not assume it owns *all* per-node identity going forward.
`project_mappings.xsd` declares its own `NodeType` (`cuemsutils.config.mappings.NodeType`) —
node hardware mappings, keyed by the same `uuid`/`mac` pair `network_map.xsd`'s `NodeType`
(`cuemsutils.config.network_map.node`) uses for node *identity*. The two are deliberately **not**
shared as one Python class (`config/mappings.py`'s docstring: "sharing one would be the F15
failure in miniature") — but a `cuems-nodeconf` atomization that reaches into `project_mappings`
for anything (e.g. to validate that an adopted node also has hardware mappings) has to reach it as
its **own** domain object, through `ConfigManager`/`ConfigBase`, not by assuming `NodeIndex`'s
node carries mapping data too. No such reach exists in `CuemsNodeConf.py` today (checked: zero
`project_mappings`/`ProjectMappings` references in the whole `cuems-nodeconf` package) — this is a
constraint for the *next* feature to respect, not a defect this one found.

## What this document is not

Not a commit to when the remaining nine rows split, and not a redesign of rows 1–4/6–10's
internals — D16 does not require touching `cuems-nodeconf` in this feature, and **010's** job is
narrower still (row 5's consumption, not the rest of the atomization). *(Renumbered from 009 on
2026-08-25; corrected on vendoring.)* This is the basis a future
feature proposal cites, so that work does not start by re-deriving the inventory this audit already
did.
