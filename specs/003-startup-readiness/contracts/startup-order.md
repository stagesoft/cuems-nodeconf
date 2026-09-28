<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contract — the start-up order (constitution VI)

The order `cuems-nodeconf` performs its start-up in after this feature, and the answer an adopt
request receives at each point. Any later change to lifecycle, threading or IPC re-states this table.

| # | Step | Socket | Map | An adopt arriving now gets |
|---|---|---|---|---|
| 1 | pre-flight: system bus, avahi (logged, not fatal) | — | — | engine's own "not running" refusal (`cf5c4ad`) |
| 2 | read `settings.xml`; **refuse** if unprovisioned | — | — | same |
| 3 | render the mDNS service record; reload avahi if it changed | — | — | same |
| 4 | bind `/tmp/nodeconf.ipc`, `chmod 0666` | **yes** | — | **`nodeconf is still starting up`** |
| 5 | wait for an interface (`CUEMS_NODECONF_IFACE_TIMEOUT`, default 10 s); exit on timeout | yes | — | same |
| 6 | seed the empty map if the file is absent | yes | — | same |
| 7 | load the map: document, then index, then **ready** | yes | half → **yes** | same until ready; then the pre-feature answers |
| 8 | zeroconf, listener, wait for own registration | yes | yes | pre-feature |
| 9 | find self by IP **and** provisioned uuid; refuse on timeout | yes | yes | pre-feature |
| 10 | set own `mac` from `settings.xml`; `ensure` the own row | yes | yes | pre-feature (the row now exists) |
| 11 | role decision; render at the role site; aliases; controller pause (`CUEMS_NODECONF_CONTROLLER_PAUSE`, default 5 s) | yes | yes | pre-feature |
| 12 | first discovery pass; `READY=1`; resident loop | yes | yes | pre-feature |

## Invariants

- No point in the table answers "Node … not found" for a node that is present.
- Readiness is asserted only when both halves of the map are installed; it never reverts.
- An unprovisioned node never reaches step 4: no socket, no record, no announcement.
- The daemon is correct whether it wins or loses the race against the engine: before step 4 the
  engine refuses on its own signal; from step 4 the daemon answers for itself.
- Exiting during steps 5–9 leaves the socket file behind (pre-existing; engine-side limitation).

## Verification

- Steps 4–7 and the guard in 9: tests that exercise the window (research R8).
- Steps 1–3 against real avahi, 8–12 against a real network, and the whole chain from the operator's
  button: hardware ledger §5 (identity) and §6 (readiness on the real dispatch path).
