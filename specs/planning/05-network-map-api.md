<!-- VENDORED from cuems-utils@b7598d5 specs/008-rebuild-extension/data-model.md §5 -->

> **Status (2026-10-13): SUPERSEDED — adopted in feature 001. `cuems-utils`' `NodeList.py` is the authority on this API now.** See `README.md` for the index.

## 5. The network-map object (ITEM C) — landed (T037–T052)

`NodeIndex` is already the MAC-keyed working set feature 007 created, which is the same shape
`CuemsNodeConf` maintains ad hoc — so no translation layer is needed (research R7).

```
NodeIndex  (existing: from_nodes, by_role, controllers)
    merge(discovered: Mapping) -> None            # match by uuid, the stable key
    adopt(node_uuid) -> bool
    unadopt(node_uuid) -> bool                    # refuses the controller
    set_controller_always_adopted() -> None
    missing_adopted(discovered: Mapping) -> tuple[...]
    signature() -> tuple[...]                     # stable over persisted fields

CuemsNetworkMapType  (existing: save)
    refresh(discovered: Mapping, path) -> bool    # merge + controller;
                                                   # writes only if signature changed
```

**`refresh` takes `path`**, unlike the shape sketched earlier in this section: it writes through
`save(path)`, and `save` has no default path (§2) — the parameter was implied by "writes" and is made
explicit here now that the method is landed.

**Discovery is passed in, never reached for.** Four of `CuemsNodeConf`'s methods read
`self.listener.nodes` directly; parameterising that is what makes them functions of their inputs and
therefore pinnable by E23's characterization tests. It is also what keeps discovery — a
`cuems-nodeconf` responsibility under D23 — out of this repository.

**`refresh` returns whether it wrote**, preserving today's write-only-if-changed behaviour, which is
what `signature()` exists for. It calls `merge` and `set_controller_always_adopted` only —
`missing_adopted` is reporting-only in the daemon too (never affects the map or the write decision), so
it is not part of the orchestration; a caller that wants the warning calls it separately on the same
`discovered` argument.

**Not ported**: `CuemsNodeConf.set_master_always_adopted`'s `self.is_first_run` branch, which clears
every non-controller node's `adopted` flag on a first run. `set_controller_always_adopted()`'s shape
above carries no such parameter. Left for 009 to reconcile when the daemon actually adopts this object
— recorded here rather than silently reproduced or silently dropped.

### The dispatch chain target (T042a)

The operator's adopt/unadopt chain, traced end to end: `cuems-frontend`'s `settings.component.ts`
(`confirmAddNode`/`confirmRemoveNode`) emits `nodelist_modify` with `modify_action` `'ADD'`/`'REMOVE'`
→ forwarded to `CuemsNodeConf.engine_callback` (`CuemsNodeConf.py:113-144`), which dispatches:

| `modify_action` | Daemon call today | `NodeIndex` equivalent |
|---|---|---|
| `'ADD'` | `self.adopt_node(node_uuid)` | `NodeIndex.adopt(node_uuid)` |
| `'REMOVE'` | `self.unadopt_node(node_uuid)` | `NodeIndex.unadopt(node_uuid)` |

No third `modify_action` is recognised — anything else is already an error response in
`engine_callback`. Asserted by `tests/contract/test_dispatch_chain_target.py`.

### T049 — `write_network_map`'s `required_fields` filter: an artifact, not preserved behaviour

`CuemsNodeConf.write_network_map` (`:413-438`) pre-checks `['uuid','mac','name','node_role','ip']`
for `None` and raises `ValueError` naming the mac and field, *before* building and saving. Every one of
those five is already `minOccurs="1"` in `network_map.xsd` — `CuemsNetworkMapType.save()` (landed,
feature 007) already rejects the same documents via T1 schema validation, raising `SchemaError`. The
daemon's check predates that save path (it existed when the daemon serialized by hand) and duplicates
what the schema now enforces on its own; its only remaining difference is a friendlier message
(naming the mac and field) under a different exception type (`ValueError`, not `SchemaError`) — not a
distinct behaviour, and not part of `save()`'s documented contract (§2). Classified as an **artifact**
and not ported: `NodeIndex`/`CuemsNetworkMapType` rely on `save()`'s existing T1 validation instead.

### T050 — the `cleanup()` defect: prescribed, not fixed here

`CuemsNodeConf.cleanup` (`:579-583`) reads `self.cm.show_lock_file`, but `self.cm` is never assigned
anywhere in the class — every call raises `AttributeError`. Out of scope to fix directly (D16: this
feature does not edit consumer repositories); recorded as a prescribed fix in `migration-guide.md` for
whoever next touches `cuems-nodeconf` — likely `self.cm = ConfigManager(...)` needs assigning in
`__init__`, matching the pattern every other consumer of `show_lock_file` uses.

---

