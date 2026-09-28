<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contract — the readiness refusal over `/tmp/nodeconf.ipc`

**Parties.** `cuems-nodeconf` (responder) and `cuems-engine` (requester), which relays to
`cuems-editor` and on to `cuems-frontend`'s settings page.

## Shape — unchanged

Every well-formed request is answered with `{'OK': bool, 'error'?: str}`. No new key. No silent
return. No raised exception reaches the socket (constitution IV).

## The new error value

| Condition | Response |
|---|---|
| `action == 'nodelist_modify'` and the daemon has not finished loading its map | `{'OK': False, 'error': 'nodeconf is still starting up'}` |

The string is exact and stable. It never contains `not found` and never contains a uuid. It is the
**only** response an adopt or unadopt can receive between the socket's creation and the map's load.

## What is not gated

Unknown actions, missing actions and non-dict bodies are answered as before, at any time:
`{'OK': False, 'error': 'unknown action: …'}` and the existing exception path.

## After readiness

Exactly the pre-feature responses, in the pre-feature order of checks:

| Case | Response |
|---|---|
| adopted | `{'OK': True}` |
| already adopted / already unadopted | `{'OK': True}` (no write) |
| offline node on adopt | `{'OK': False, 'error': …offline…}` |
| the controller on unadopt | `{'OK': False, 'error': …}` |
| uuid not in the map | `{'OK': False, 'error': 'Node <uuid> not found'}` |
| bad `modify_action` | `{'OK': False, 'error': 'Invalid modify_action: …'}` |

## Consumer behaviour — decision D (2026-09-28)

`cuems-engine` and `cuems-editor` **relay the error string verbatim**. No retry, no interpretation,
no new UI affordance. The operator reads *nodeconf is still starting up* and tries again.

Two prohibitions already recorded in the consumer repositories stand:

- `cuems-engine` must not deepen its reliance on the existence of `/tmp/nodeconf.ipc` as a readiness
  signal (its `specs/planning/xml-refactor/04-findings-new-to-this-pass.md`, F2a). Its instant
  refusal when the socket is absent (`cf5c4ad`) is **correct and stays**.
- `cuems-editor` must not add client-side retry or interpretation of the string
  (its `specs/planning/xml-refactor/00-runnable-flow.md`, §0a).

## Known limitation, out of scope

A `/tmp/nodeconf.ipc` file left behind by a daemon that exited during start-up satisfies the engine's
existence probe with nobody listening; the engine's own 5 s IPC timeout then applies. Pre-existing;
recorded for the engine flow, not changed here.
