<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# `node_set` — the operator's node alias, written by the map's only writer

**Repo-original, not vendored.** A ready-to-implement brief, written 2026-10-08. It covers one new
IPC action and one handler method, together with their tests and verification. It is not run
through the full spec-kit flow:
- the contract is fixed by three repositories that already agree on it (§3);
- every decision is settled (§2);
- the change touches two responsibilities this class already has (constitution V), and adds none.

If implementation turns up a question this document does not answer, that is the signal to stop and
run `/speckit.specify` after all.

**Measured against** this repository's `feat/xml-refactor` @ `2045897`, `cuems-utils` @ `67c89bd`,
`cuems-engine` `origin/feat/xml-refactor` @ `fc0cad3`, and `cuems-editor` feature
`002-config-round-trip` (local, `b10fff1`). Re-measure line numbers before relying on them
(constitution, *Measure, do not transcribe*).

## 1. The requirement

An operator gives a node a human label (`<alias>`) in the UI. The label must **persist**, and the
only process that can persist it is this daemon.

**Why the editor can't write the file itself:**
- `read_network_map()` (`CuemsNodeConf.py:849`) runs only at start-up.
- Every later write (`refresh_network_map` `:526`, `_save_network_map` `:782`) serialises the
  daemon's **in-memory** index.
- `CuemsNetworkMapType.refresh` decides whether to write by comparing `NodeIndex.signature()` before
  and after the merge (`cuems-utils` `config/network_map.py:141`), never against the file.

So a `network_map.xml` written by anyone else is **silently reverted** at the daemon's next write:
a discovery change, an IP change, any adopt or un-adopt. That is constitution II ("never racing
another writer") seen from outside.

`cuems-editor` 002 therefore stops writing `network_map` through its `config_save` (its FR-019) and
sends alias edits here as **`node_set`** (its FR-024 to FR-027).

## 2. Re-evaluation — does the requirement hold here?

Checked against this repository's constitution, specs and planning on `feat/xml-refactor`.
**Verdict: it holds, with three corrections to what the consumers first wrote.**

| # | Claim | Result | Evidence |
|---|---|---|---|
| R1 | The daemon is the map's only runtime writer and reverts outside writes | **Holds** | §1, and constitution II |
| R2 | `alias` is the operator's; `role_id` and `hostname` are the daemon's | **Holds** | `cuems-common` `docs/node-identity-contract.md:35-37`. Constitution, Operating Constraints: this daemon assigns `<role_id>` and applies the OS-side identity chain |
| R3 | ~~The daemon publishes the operator `alias` over mDNS, so a change must be republished~~ | **Wrong — corrected** | `_ui_alias` (`:982`) publishes the deployment constant `CONTROLLER_ALIAS = 'formitgo.local'` (`:62`). Its docstring: *"distinct from the free-form operator `<alias>` map field"*. Nothing publishes the operator alias. `node_set` has **no** mDNS step |
| R4 | Discovery would overwrite an alias set between passes | **Does not happen** (measured) | `NodeIndex.merge` copies the discovered node's keys onto the stored one. A discovered node carries only `uuid, mac, name, node_role, ip, adopted, online`, so `alias` and `role_id` survive a merge, and the stored object stays the same object |
| R5 | The engine must relay `node_set` as it relays `nodelist_modify` | **No — the editor talks to the daemon directly** | The engine never reads `alias` (no read found in `cuems-engine` `src/` at `fc0cad3`). Its relay exists for `nodelist_modify`'s preconditions (refusing while a project is loaded or running, then reloading its own topology, `ControllerEngine.py:805-880`); neither applies to a label. `cuems-editor` 002 decided this as its Q2. Only `cuems-frontend` reads `alias`, to label nodes |
| R6 | A second requester can reach the socket | **Holds** | `communicate.py` binds `/tmp/nodeconf.ipc` as an NNG `Rep0`, sets mode `0666` for any local CUEMS process (`:87-99`), and serves one request at a time on a fresh context (`cuems-utils` `CommunicatorServices.responder_get_request`). Two requesters queue; neither starves the other beyond one handler's run time |
| R7 | Constitution IV holds for the new action | **Holds, as written** | IV: *"Every well-formed request over `/tmp/nodeconf.ipc` MUST be answered"*. That covers any requester. The response shape `{'OK': bool, 'error'?: str}` is reused unchanged |
| R8 | Constitution V allows it | **Holds** | Dispatch is responsibility 10 (engine IPC dispatch: a thin translator, `01-atomization-basis.md`); the mutation is responsibility 5, delegated to `NodeIndex`. No eleventh responsibility |
| R9 | An invalid alias is harmless | **No — it would poison the index (measured)** | `<alias>` is `cms:NonEmptyString`. An in-place `""` makes `save` raise `SchemaError` *after* the index changed. `_save_network_map` then sets `_map_write_pending`, and every later write fails on the same row until restart. **The alias must be validated before anything changes** (§4) |
| R10 | The readiness window applies | **Yes, and it must be gated** | Before `_ready` (`:906`) the index is empty, so a `node_set` would answer a false *"not found"*: the same defect feature 003 fixed for `nodelist_modify` |

Stale coordinates noticed in passing, not acted on: the constitution's "774 lines" and "81 tests"
are now **1098** lines (`CuemsNodeConf.py`) and **152** test functions.

## 3. The contract

**Parties.** `cuems-editor` (requester, direct) and `cuems-nodeconf` (responder). `cuems-engine` is
**not** a party.

**Request** — a dict on `/tmp/nodeconf.ipc`:

```json
{"action": "node_set", "node_uuid": "<uuid4 string>", "alias": "<non-empty string>" | null}
```

- `alias: null` **clears** the label (the element is optional; measured: setting the key to `None`
  or removing it both save without `<alias>`).
- `alias` must be **present**. A request without the key is refused, because "unset" and "leave
  alone" can't be told apart.
- **No other key is accepted.** A request carrying any other field (`role_id`, `hostname`, `name`,
  `ip`, `online`, `adopted`, `node_role`, `mac`, `uuid`) is refused and the refusal names it. The
  editor refuses the same first (its FR-024); this is defence in depth, not the primary check.

**Responses**, in order of checks. All have the shape `{'OK': bool, 'error'?: str}`:

| Case | Response | Write? |
|---|---|---|
| not ready (map not loaded) | `{'OK': False, 'error': 'nodeconf is still starting up'}`, the exact feature 003 string | no |
| a key other than `action`/`node_uuid`/`alias` | `{'OK': False, 'error': 'node_set accepts only alias; refused: <sorted keys>'}` | no |
| `alias` key missing | `{'OK': False, 'error': 'node_set needs an alias (null clears it)'}` | no |
| `node_uuid` missing or not a string | `{'OK': False, 'error': "node_set needs a node uuid, got <repr>"}` | no |
| `alias` neither `null` nor a non-blank string | `{'OK': False, 'error': 'alias must be a non-empty string or null'}` | no |
| uuid not in the map | `{'OK': False, 'error': 'Node <uuid> not found'}`, the string adopt already uses | no |
| alias already that value | `{'OK': True}` | **no** (constitution II: the signature did not move) |
| set or cleared | `{'OK': True}`, after the write | yes |
| the write fails | `{'OK': False, 'error': '<exception text>'}`, through `engine_callback`'s existing exception path | no. The change stays in memory and is owed to the next refresh (`_map_write_pending`), exactly as for adopt |

An **offline** node may be labelled; unlike adopt, a label has no liveness precondition. The
controller may be labelled.

Consumers relay the error string verbatim with no retry (decision D of
`specs/003-startup-readiness/contracts/readiness-response.md`, which binds the editor here too).

## 4. Library dependency — `cuems-utils` §0a G4

The daemon delegates every map mutation to `NodeIndex` (`adopt`, `unadopt`, `merge`, `ensure`).
Decision **D22** puts network-map logic in `cuems-utils`, and D2 rejected even a daemon-side insert
for that reason (`specs/003-startup-readiness/research.md:217-218`). The setter therefore lands in the library first. It is
recorded as gate **G4** in `../cuems-utils/specs/planning/upcoming-feature-requirements-2026-10-02.md`
§0a, with these semantics, which this document and that one now state identically:

`NodeIndex.set_alias(node_uuid, alias) -> bool`
- **Validates first**: `alias` must be `None` or a string matching `NonEmptyString`, else
  `ValueError`, raised **before** any node is touched (R9).
- **Mutates in place**, on the node object the document holds (the T091/T092 aliasing contract
  that `adopt` documents). `None` removes the key.
- Returns `False` for an unknown uuid and `True` otherwise, whether or not the value changed. The
  caller tells "unchanged" apart by `signature()`, as `adopt_node` does.
- `signature()` already includes `alias`, so the write-if-changed path needs no change.

**Order: the library first, then this repository.** Until `set_alias` is in the `cuemsutils` this
repository installs, the handler can't be written without breaking D22. Do not stand in for it with
a direct `node['alias'] = …`.

## 5. Implementation

Two code sites, both in `cuemsnodeconf/CuemsNodeConf.py`.

**5a. `engine_callback` (`:368`)** — a second branch beside `nodelist_modify`, before the
unknown-action `else`:
- the `_ready` gate, answering the feature 003 string (R10);
- then the key, `node_uuid` and `alias` checks of §3, in that order;
- then `result = self.alias_node(node_uuid, alias)`, and the response built exactly as the
  `nodelist_modify` branch builds it (`OK`, plus `error` if present);
- every path answers through `respond_to_engine` (constitution IV);
- the docstring's "a request from the engine" becomes "a request from the engine or the editor".

**5b. `alias_node(node_uuid, alias)`** — beside `adopt_node` (`:804`) and modelled on it:

```python
before = self.network_map.signature()
try:
    found = self.network_map.set_alias(node_uuid, alias)
except ValueError as e:
    return {'OK': False, 'error': str(e)}          # nothing changed (R9)
if not found:
    return {'OK': False, 'error': f'Node {node_uuid} not found'}
if self.network_map.signature() == before:
    return {'OK': True}                            # no write (constitution II)
self._save_network_map()
Logger.info(f'Node {node_uuid} alias set')
return {'OK': True}
```

Nothing else changes: no mDNS step (R3), no write-path change, and `refresh_network_map` stays as it
is (R4).

**5c. Documentation in the same change:**
- add a dated amendment to `specs/003-startup-readiness/contracts/readiness-response.md`. Its
  *"What is not gated"* section and *"Only this branch is gated"* comment now also cover `node_set`,
  and its *Parties* line gains `cuems-editor` as a direct requester for `node_set`;
- update the comment in `engine_callback` that says "Only this branch is gated".

A constitution amendment is **not** required: IV's rule is already about every request on the
socket. Mentioning the second requester in IV's prose is an optional PATCH amendment, and it is the
maintainer's call.

## 6. Tests

All in `tests/`, with the existing stubs (`conftest.py`) and the fixtures under
`tests/fixtures/etc_cuems/`. Write each before the code it guards.

| Test | Asserts |
|---|---|
| `test_engine_callback.py`: `node_set` before ready | the feature 003 string, no write |
| `test_engine_callback.py`: every refusal row of §3 | exact error text; the map file's bytes unchanged |
| `test_engine_callback.py`: set, clear (`null`), unchanged | `OK` true; the file has / lacks `<alias>`; **no write** on unchanged (mtime and bytes) |
| `test_engine_callback.py`: an empty or blank alias | refused **and** the index unchanged: a following `adopt` still saves (the R9 poisoning regression) |
| `test_engine_callback.py`: an unknown action | still `unknown action: …` (the existing behaviour, re-asserted) |
| `test_node_aliasing.py` | the alias set through the handler is visible in the document `_network_map_document()` serialises: the same object, not a copy |
| `test_network_map.py` (or a new `test_node_set.py`) | set an alias, run `refresh_network_map` with a discovery that changes the node's `ip`, and the alias is still on disk (R4, the reason the requirement exists) |
| offline node, controller node | both can be labelled |

The suite must stay fully green, and coverage of the adopt/unadopt chain must not drop (Testing
Gate).

## 7. Verification

- **On a development checkout**, run a dispatch-path check, as constitution IV asks: a `Req0` client
  sends `node_set` over a real IPC socket to an `engine_callback` served by `AsyncCommsThread`
  (`communicate.py:26`) against a fixture map, and the reply and the file are asserted. No existing
  test opens a real socket (`tests/test_communicate.py` covers thread state only), so this check is
  new; a temporary socket path keeps it off `/tmp/nodeconf.ipc`.
- **On hardware** (the formitgo controller, where the daemon is enabled), from the editor UI:
  1. label a node;
  2. confirm `<alias>` is in `/etc/cuems/network_map.xml`;
  3. un-adopt and re-adopt another node, and confirm the label survived that write;
  4. confirm the label shows in every open UI.

  Record the result, or state plainly that it was not performed (Testing Gate: *silence is not an
  answer*), in a new row of the verification record this change creates beside this document, or
  in the commit message.

## 8. Out of scope

- Editing `role_id` or `hostname` through any action. They are this daemon's (R2).
- Publishing the operator alias over mDNS (R3). If ever wanted, it is a new responsibility-8
  decision, not part of this command.
- Routing `node_set` through the engine (R5).
- Bulk or multi-node edits. One node per request.
- The atomization of `CuemsNodeConf` (constitution V: the basis stays valid; this change only adds
  to rows 5 and 10).

## 9. Counterparts

| Repository | What it does | Where |
|---|---|---|
| `cuems-utils` | `NodeIndex.set_alias` (§4), first | requirements doc §0a G4 |
| `cuems-editor` | `node_set` action: refuses non-operator fields, answers `unavailable` when the socket is absent (no IPC attempt), connects directly, treats a `None` reply from `Communicator.send_request` as a failure (it swallows exceptions; `cuems-engine` learned this, `ControllerEngine.py`), applies its own timeout, refreshes all sessions | feature 002, FR-024 to FR-027. Its upstream report (cuems-editor UR-8) is answered by this document |
| `cuems-frontend` | the alias field in Settings; "unavailable" when nodeconf is not running | not yet assigned |

## 10. Done when

- [ ] `cuemsutils` with `NodeIndex.set_alias` is installed here, with its commit recorded.
- [ ] §5a and §5b landed; §5c amendments written.
- [ ] Every §6 test written first, seen failing, then green; the full suite green.
- [ ] §7's dispatch-path check run; the hardware check run, or recorded as not run.
- [ ] `cuems-editor` told the contract is live (the response to its UR-8).
