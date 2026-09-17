# cuems-nodeconf

Part of the **CUEMS** ecosystem — see the [`cuems-RELATIONS`](https://github.com/stagesoft/cuems-RELATIONS) repo for the system index, architecture diagram, and protocol/port map.

## Role

Node-side discovery + adoption daemon. Uses avahi (`_cuems_nodeconf._tcp.local`) to publish each node's UUID/MAC/role/IP and maintain `/etc/cuems/network_map.xml` automatically. Python 3.11+. Service `cuems-nodeconf.service`, `PartOf=cuems-node.target`, runs as **root**. Prebuilt `.deb` cached at `rc1_packages/`.

When reactivated it also owns **node identity**: assigns `<role_id>` on adoption and applies the OS-side identity chain (hostnamectl + `/etc/hosts` + avahi-daemon.conf). The `cuems-nodeconf apply-identity[ --check]` CLI for planned role-flips is **planned, not yet implemented in source**. The full node-identity field contract lives in the cuems-common CLAUDE.md and `cuems-common/docs/node-identity-contract.md`. **nodeconf touches network plumbing on exactly one path**: `set_node_role` → `change_network_to_master` → `change_network_settings_to_master` stops `networking.service` over D-Bus, copies `/usr/share/cuems/interfaces.master` over `/etc/network/interfaces`, restarts the unit and sleeps 10 s either side — the daemon's most destructive operation, on controller promotion. `dhcpd`/`dhclient` and `hostapd` are out of remit. An earlier note here claimed no plumbing at all; that was wrong, and cuems-common's CLAUDE.md plus the atomization basis' row 6 both already recorded the correction.

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
- **Cadence:** nodeconf runs at boot and on explicit reconfigure — not continuously. So `<online>` is stale between those moments *by design*.
- **The engine does NOT write it.** `ControllerEngine._probe_cluster_liveness` produces a *different* signal (sub-second ping/pong at each project load, used to decide which nodes the GO gate waits for). It lives in memory only. Overwriting `<online>` with the engine's view corrupts nodeconf's snapshot semantics — we tried (commit `fd46651` on `feat/cuems-display-setup`) and reverted it (`e8df682`, 2026-05-18) because the two signals have different time scales and consumers.
- **Practical:** reading `<online>` (cuems-logs `--list-nodes`, UIs, audits) = "what nodeconf saw at boot/reconfig", not "alive now". For runtime liveness use the engine (`/engine/status/*` over WebSocket OSC, or scrape `journalctl -u cuems-controller-engine | grep "Cluster state resolved"`). Only nodeconf should write it (operators may hand-flip it during the transition — that just simulates the next discovery). New "is node X reachable?" code: boot-time intent → `<online>`; right-now liveness → the engine probe.

## Field notes / gotchas

- **mDNS interface scoping** (shaped the alias design): `avahi-publish -a` cannot scope a static A record to one interface (it floods all, leaking 169.254 onto the UI net) — interface-scoped records need the avahi D-Bus API `EntryGroup.AddAddress(interface_index, ...)`. avahi-daemon's native hostname publication is already per-interface-correct, so do NOT statically publish `controller.local` when hostname == controller (redundant + the double-A-record Mac trap). `.local` is link-scoped — no resolution across routers; UI access from routed segments needs real DNS.
