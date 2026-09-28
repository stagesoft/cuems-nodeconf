<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contract — `/etc/avahi/services/cuems.service` is rendered from `settings.xml`

Counterpart of `cuems-utils` `specs/011-etc-cuems-first-install/contracts/cuems-common-handover.md`
§4a. `cuems-nodeconf` is the record's **sole writer**.

## Inputs

| Input | Owner | Shape |
|---|---|---|
| `/etc/cuems/settings.xml` → `<node><uuid>`, `<node><mac>` | `cuems-init-node` (`cuems-utils`) | schema-required strings |
| `/usr/share/cuems/cuems.service.{controller,node,firstrun}` | `cuems-common ≥ 1.3.0-23` | XML text carrying `uuid=00000000-0000-0000-0000-000000000000` in every `<txt-record>` that names a uuid |

## Sentinels (shared constants, pinned on both sides)

```
SENTINEL_UUID = "00000000-0000-0000-0000-000000000000"   # 36 characters
SENTINEL_MAC  = "000000000000"
```

## Rules

1. **Before the socket.** The first render happens before `/tmp/nodeconf.ipc` is bound. A daemon that
   refuses here creates no socket and announces nothing.
2. **Unprovisioned → refuse.** `settings.xml` absent, unreadable, invalid, or carrying either sentinel:
   log a line beginning `NOT PROVISIONED`, exit non-zero.
3. **Literal substitution.** rendered = template bytes with every `SENTINEL_UUID` replaced by the
   provisioned uuid. No parsing. A template with **zero** occurrences is refused (it carries a real
   identity and predates `cuems-common 1.3.0-23`).
4. **Write only on change.** If the live file's bytes equal the rendered bytes: no write, no reload.
5. **Atomic, readable.** Temp file in `/etc/avahi/services/`, mode `0644`, `os.replace`.
6. **Reload only on change.** `avahi-daemon.service` reloaded through the systemd D-Bus manager after a
   write; a reload failure is logged and does not stop the daemon.
7. **Role preserved at start.** The start-up render uses the role the live file already declares
   (`node_role=`), `firstrun` if there is no live file. Role changes render through the same helper:
   controller on election and on resume, node when a controller exists.
8. **Guard after discovery.** The entry discovered at this node's IP must carry the provisioned uuid;
   a different uuid is waited out (a stale record mid-reload) and, on timeout, refused with both values
   and the remedy.

## Operator consequences (documented in this repository)

- After `cuems-init-node --force-new-identity` (or feature 012's re-mint): **restart
  `cuems-nodeconf`**. Until then `cuems-init-node --check` exits **1** (live record disagrees).
- `cuems-init-node --check` exits **3** while the source carries the sentinel; the daemon refuses to
  start in that state with the same words.
- The record is unmaintained on a node where the daemon is masked or disabled; unmasking it
  fleet-wide is part of the coordinated landing (ledger §5).
