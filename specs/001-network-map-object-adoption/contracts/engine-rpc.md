# Contract — the engine RPC (`/tmp/nodeconf.ipc`)

**Status**: existing contract, preserved verbatim by this feature. Nothing here is new;
it is written down because the implementation underneath it is being replaced.

**Transport**: NNG Req/Rep over `/tmp/nodeconf.ipc`. The daemon runs as root and the
engine does not, so the socket is `chmod 0666` after binding — unchanged by this feature,
and load-bearing (a root-owned socket crash-loops the engine).

**Far end**: `cuems-frontend`'s `settings.component.ts` (`confirmAddNode` /
`confirmRemoveNode`), via the engine. A UI operators use today.

---

## Universal rule

**Every well-formed request receives exactly one response.** Returning without responding
leaves the engine blocked until its own 15 s timeout, which reaches the operator as an
unexplained stall rather than an error. This applies to the unknown-action branch and to
the exception handler, not only to the happy path.

The migration MUST NOT narrow this back to a single answering path.

## Request

```json
{ "action": "nodelist_modify", "value": "<node uuid>", "modify_action": "ADD" | "REMOVE" }
```

No third `modify_action` is recognised.

## Response

```json
{ "OK": true }
{ "OK": false, "error": "<message>" }
```

`OK` is always present. `error` is present exactly when `OK` is false. Any other key the
handler produces internally is dropped at the boundary and never reaches the UI.

## The five outcomes of `nodelist_modify`

| `modify_action` | Condition | Response |
|---|---|---|
| `ADD` | node present, online, not adopted | `{'OK': True}` |
| `ADD` | node present, already adopted | `{'OK': True}` |
| `ADD` | node present, offline | `{'OK': False, 'error': 'Cannot adopt node {uuid}: node is offline'}` |
| `ADD` / `REMOVE` | uuid not in the map | `{'OK': False, 'error': 'Node {uuid} not found'}` |
| `REMOVE` | node present, not the controller | `{'OK': True}` |
| `REMOVE` | node present, already unadopted | `{'OK': True}` |
| `REMOVE` | node is the controller | `{'OK': False, 'error': 'Cannot unadopt master node'}` |
| any other value | — | `{'OK': False, 'error': 'Invalid modify_action: {value}'}` |

**The three error strings are byte-for-byte fixed.** They are what the Angular component
displays.

## Other actions

| Case | Response |
|---|---|
| a well-formed message with any other `action` | `{'OK': False, 'error': 'unknown action: {action}'}` |
| an exception anywhere in the handler | `{'OK': False, 'error': '<str(exception)>'}` |

## What the migration must do to keep this true

The ported `NodeIndex.adopt` / `.unadopt` return a **bare bool**, and each `False` is
**two-way ambiguous**:

- `adopt` returns `False` for *absent* **and** for *offline*
- `unadopt` returns `False` for *absent* **and** for *is the controller*

So the daemon cannot map the bool to a string directly. On `False` it MUST look the uuid
up in the map and choose:

```
adopt   False -> absent?              "Node {uuid} not found"
                 present & offline?   "Cannot adopt node {uuid}: node is offline"
unadopt False -> absent?              "Node {uuid} not found"
                 present & controller? "Cannot unadopt master node"
```

A successful `adopt`/`unadopt` MUST also **persist** before responding — the ported methods
mutate only, while the methods they replace wrote to disk on success. Answering `{'OK':
True}` for a change that is not on disk is a lie the operator cannot see.

## Verification

Not satisfiable by unit tests alone. See `quickstart.md` §3 for the end-to-end procedure
against the real dispatch path — spec SC-003.
