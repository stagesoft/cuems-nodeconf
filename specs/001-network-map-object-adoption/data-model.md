# Phase 1 — Data model

Entities as this feature leaves them. Nothing here is new: the shapes already exist in
`cuemsutils`, and the value of writing them down is that **where each piece of state lives
changes**, even though none of the shapes do.

---

## Where state lives, before and after

| | Today | After |
|---|---|---|
| Working set | `self.network_map` is a **`NodeIndex`**, built by hand in `read_network_map` | `self.network_map` is a **`CuemsNetworkMapType`** — the document |
| Index | the working set itself | derived per operation from `node_list`, discarded after |
| Merge / controller-adopted / write decision | nine daemon methods | `CuemsNetworkMapType.refresh(discovered, path)` |
| Adopt / unadopt | daemon methods returning dicts | `NodeIndex.adopt`/`.unadopt` returning bools, on a derived index, written back and saved |
| Reporting | `check_missing_adopted_nodes` | `NodeIndex.missing_adopted(discovered)`, called by the daemon |

The direction of the arrow matters: **the document owns `node_list`; the index is a view**.
Getting this backwards loses operator adoptions (research D-A).

---

## Network map (document)

`cuemsutils.config.network_map.CuemsNetworkMapType` — a declared-field config object,
validated against `network_map.xsd` on save.

- **`node_list`** — a list of `{"node": <node>}` wrappers. The wrapper is kept, because
  `cuems-engine` iterates that shape.
- **`refresh(discovered, path) -> bool`** — merges, applies controller-always-adopted,
  compares signature, writes only on change, returns whether it wrote.
- **`save(path) -> None`** — validates then writes. Raises `SchemaError` on a document that
  does not match the schema; `OSError` propagates unwrapped. No default path.

**Obtained by**: `ConfigManager.load_network_map()` then `.network_map`. Measured equal in
result to the internal reader it replaces.

**Validation**: the schema requires `uuid`, `mac`, `name`, `node_role`, `ip` and `online`.
The daemon's own pre-save check on those fields is **not** carried over — the schema
enforces the same thing on the same write, and the local check predates that path.

---

## Node index (view)

`cuemsutils.tools.NodeList.NodeIndex` — a MAC-keyed mapping of node records, derived from
`node_list` by `{item["node"]["mac"]: item["node"]}`.

| Method | Contract |
|---|---|
| `merge(discovered)` | matches by **`uuid`**, never by the discovered key. Preserves `adopted` on matched nodes, sets `adopted=False` on genuinely new ones, sets `online` per pass |
| `adopt(uuid) -> bool` | `True` on success **and** when already adopted; `False` when absent **or** offline |
| `unadopt(uuid) -> bool` | `True` on success **and** when already unadopted; `False` when absent **or** the controller |
| `set_controller_always_adopted()` | every controller becomes adopted. No first-run behaviour |
| `missing_adopted(discovered) -> tuple` | adopted nodes not among `discovered`. Reporting only |
| `signature() -> tuple` | key-sorted, order-independent, over the persisted fields |

`adopt` and `unadopt` **mutate only — they do not persist**. Both `False` returns are
two-way ambiguous, which is why the daemon re-runs the discriminating lookup.

---

## Node record

`cuemsutils.config.network_map.node` (public path `cuemsutils.tools.NodeList.node`).
Measured field set from a loaded document: `uuid`, `mac`, `name`, `node_role`, `ip`,
`adopted`, `online` — plus the operator fields `role_id`, `alias`, `hostname` where present
(`signature()` covers all ten).

- **`uuid`** — the only stable identity key. Never derive identity from `name`: the
  controller advertises its service as `controller`, so a name-parsed MAC is garbage.
- **`node_role`** — a `NodeRole` after loading, not a string: `controller`, `node`,
  `firstrun`.
- **`adopted`** — operator state. Set only by adopt/unadopt and by
  `set_controller_always_adopted`; preserved across merges.
- **`online`** — a **discovery-pass snapshot**, not liveness. Written only by this daemon.
- **`role_id` / `alias` / `hostname`** — operator fields the merge must never clobber.

## State transitions — `adopted`

```
                 adopt(uuid), node online
  not adopted ─────────────────────────────▶ adopted
       ▲                                        │
       │            unadopt(uuid),              │
       └──────── node is not the controller ◀───┘

  adopt(uuid) on an offline node      -> refused, state unchanged
  unadopt(uuid) on the controller     -> refused, state unchanged
  set_controller_always_adopted()     -> controller forced to adopted
  merge(discovered)                   -> preserved on known nodes; False on new ones
```

Both refusals return the same `False` as "uuid not found", which is the whole reason the
daemon re-discriminates.

---

## Discovery record

What the Avahi listener produces per peer: `uuid`, `node_role`, `ip`, `mac`, `name`.
Constructed with `adopted=False` and `online=True` **always** — adoption is map state and
never travels on the wire.

**Passed into** `refresh` and `missing_adopted` as an argument. The library never reaches
for it; discovery stays this daemon's responsibility.

**Changing in this feature**: the TXT key carrying the role becomes `node_role`, its values
become `controller`/`node`/`firstrun`, and the translation table from the retired
vocabulary is removed rather than extended. See `contracts/avahi-txt.md`.

---

## Modify request and response

The operator's instruction, over the engine socket. Unchanged in shape by this feature —
see `contracts/engine-rpc.md`, which is the authoritative statement.
