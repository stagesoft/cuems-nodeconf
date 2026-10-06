<!-- SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- SPDX-FileContributor: Ion Reguera <ion@stagelab.coop> -->

# cuems-nodeconf

Part of the **CUEMS** ecosystem — see the [`cuems-RELATIONS`](https://github.com/stagesoft/cuems-RELATIONS) repo for the system index, architecture diagram, and protocol/port map.

## Role

Node-side discovery + adoption daemon. Uses avahi (`_cuems_nodeconf._tcp.local`) to publish each node's UUID/MAC/role/IP and maintain `/etc/cuems/network_map.xml` automatically. Python 3.11+. Service `cuems-nodeconf.service`, `PartOf=cuems-node.target`, runs as **root**. Prebuilt `.deb` cached at `rc1_packages/`.

When reactivated it also owns **node identity**: assigns `<role_id>` on adoption and applies the OS-side identity chain (hostnamectl + `/etc/hosts` + avahi-daemon.conf). The `cuems-nodeconf apply-identity[ --check]` CLI for planned role-flips is **planned, not yet implemented in source**. The full node-identity field contract lives in the cuems-common CLAUDE.md and `cuems-common/docs/node-identity-contract.md`. **nodeconf does NOT touch network plumbing** (`/etc/network/interfaces`, dhcpd/dhclient, hostapd) — avahi/zeroconf + network_map writes + (future) the identity chain only.

## Status (Phase-1 re-enable)

**Re-enabled + soak-passed on the formitgo controller (10.16.1.111) since 2026-06 (nodeconf 0.1.0-6, branch `feat/nodeconf-reenable` `e7f70fa`).** It is **still disabled elsewhere** in the fleet; cluster topology is otherwise hand-edited in `network_map.xml`. Multi-node validation is deferred (ClickUp `869dnux7j`). Five bugs were fixed during the re-enable and are load-bearing:

1. **Map duplicate-node** — merge by UUID, not the name-derived mac (the controller's avahi service is named `controller` → `get_mac` returns a garbage key → duplicate node + real node flipped offline).
2. **nng panic on shutdown** — AsyncCommsThread cancels the engine-listener + closes the loop in-thread.
3. **`formitgo.local` CollisionError** — AliasPublisher passes `AVAHI_PUBLISH_NO_REVERSE` (forward A only; was colliding with the host's native reverse PTR on bond0).
4. **IPC-perm crash-loop (the big one)** — nodeconf runs as root and created `/tmp/nodeconf.ipc` root-owned; the cuems-user engine then failed its Communicator R/W check and exited 1 in a restart loop whenever nodeconf won the boot race. Fix: nodeconf `chmod 0666` the socket after binding. Recovery if it recurs: `systemctl disable --now cuems-nodeconf; rm -f /tmp/nodeconf.ipc; systemctl restart cuems-controller-engine` (the engine tolerates an *absent* socket, only a root-owned one kills it).
5. **Packaging** — ship only `cuemsnodeconf*`; blanket-strip dh-virtualenv's staged deps (two `pwiz.py` conflicts with cuems-utils).

## `<online>` field ownership

`<online>` in `network_map.xml` is **nodeconf's** field and is **NOT a real-time liveness signal** — it's a discovery-pass snapshot.

- **Why it exists:** to remember adopted-but-currently-absent nodes without losing their identity records. Removing offline nodes would discard uuid/mac/role_id/adoption history; instead nodeconf keeps the row and marks `<online>False</online>` = "still known, currently absent". Re-discovery flips it back to `True` and the node resumes its role without re-adoption.
- **Cadence (corrected 2026-09-04):** nodeconf is **resident** since `3e100bb` — `_run_worker_loop` re-merges avahi discovery and rewrites the map on every (debounced) avahi event **or every 30 s**. So `<online>` is a **≤30 s-stale discovery proxy**, not the boot-only snapshot this section used to describe. It is still *not* runtime liveness: discovery answers "did avahi see this node in the last pass", the engine's ping/pong answers "is it alive right now", and only the second gates GO.
- **The engine does NOT write it.** `ControllerEngine._probe_cluster_liveness` produces a *different* signal (sub-second ping/pong at each project load, used to decide which nodes the GO gate waits for). It lives in memory only. Overwriting `<online>` with the engine's view corrupts nodeconf's snapshot semantics — we tried (commit `fd46651` on `feat/cuems-display-setup`) and reverted it (`e8df682`, 2026-05-18) because the two signals have different time scales and consumers.
- **Practical:** reading `<online>` (cuems-logs `--list-nodes`, UIs, audits) = "what nodeconf saw at boot/reconfig", not "alive now". For runtime liveness use the engine (`/engine/status/*` over WebSocket OSC, or scrape `journalctl -u cuems-controller-engine | grep "Cluster state resolved"`). Only nodeconf should write it (operators may hand-flip it during the transition — that just simulates the next discovery). New "is node X reachable?" code: boot-time intent → `<online>`; right-now liveness → the engine probe.

## Adoption from the UI (the full chain)

`{"action":"nodelist_modify","value":<uuid>,"modify_action":"ADD"|"REMOVE"}`
travels **browser → cuems-editor (WS `:9092`) → engine (`/tmp/editor.ipc`) →
nodeconf (`/tmp/nodeconf.ipc`)** and lands in `engine_callback` →
`adopt_node`/`unadopt_node`, which flip `<adopted>` and rewrite the map
atomically. Two traps worth knowing before debugging a "nothing happens":

- **The engine hop only exists since `feat/nodelist-modify-dispatch`.** It was
  written once and archived under `refs/tags/archive/feat-node_adoption`, an
  ancestor of no branch, so on any older engine the click dies at
  `Command nodelist_modify not recognized`.
- **nodeconf ships disabled everywhere except formitgo.** With no
  `/tmp/nodeconf.ipc`, the engine's `request_to_nodeconf` gets `None` (the
  Communicator swallows the exception) and answers *"the node configuration
  service is not responding"*. The editor now also publishes
  `nodeconf_available` in its mappings payload so the UI can grey the control.

Adoption is **refused while a project is running or merely loaded** — the GO
gate's `_required_nodes` set is computed once, at load, so accepting a REMOVE
mid-load would leave it waiting on a node that is gone. Unload first.

**Two threads write the map.** The resident loop (main thread) and
adopt/unadopt (comms thread) both render through the same
`map.tmp.<pid>` before `os.replace`, so both must hold `_map_lock` — without it
a concurrent pair can promote a truncated XML that nothing can load.

## Field notes / gotchas

- **Foreign controllers on a shared LAN are filtered (0.1.0-8).** Every
  controller advertises `node_type=master`, and the taller has three clusters
  on one LAN (test2, test, test3). Before 0.1.0-8 `merge_discovered_nodes`
  took every master it heard and `set_master_always_adopted` marked them
  **adopted** — test2's map gained test3 (2026-10-01) and the `test` box
  (2026-10-06) as adopted controllers. Now `_cluster_master_uuids()` decides
  who "our" master is (a controller: itself; a node: the master its map already
  records; an empty map: first come, as before) and `_is_foreign_master()`
  drops the rest at discovery and purges any already persisted (`Dropped
  foreign controller … belongs to another cluster` in the journal). The
  firstrun election (`set_node_type`) still looks at *all* masters on the LAN,
  so a brand-new node on a shared LAN will still elect itself a slave of
  whichever controller it hears first.

- **mDNS interface scoping** (shaped the alias design): `avahi-publish -a` cannot scope a static A record to one interface (it floods all, leaking 169.254 onto the UI net) — interface-scoped records need the avahi D-Bus API `EntryGroup.AddAddress(interface_index, ...)`. avahi-daemon's native hostname publication is already per-interface-correct, so do NOT statically publish `controller.local` when hostname == controller (redundant + the double-A-record Mac trap). `.local` is link-scoped — no resolution across routers; UI access from routed segments needs real DNS.
