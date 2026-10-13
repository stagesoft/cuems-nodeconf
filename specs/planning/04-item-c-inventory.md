<!-- VENDORED from cuems-utils@b7598d5 specs/008-rebuild-extension/migration-guide.md, ITEM C -->

> **Status (2026-10-13): SUPERSEDED — T052 implemented in feature 001; T050's `cleanup()` no longer exists.** See `README.md` for the index.

# ITEM C — this repository's inventory, from feature 008's migration guide

## ITEM C — the network-map object moves in from `cuems-nodeconf`

**This ships with no first-party caller.** `NodeIndex.merge`/`adopt`/`unadopt`/
`set_controller_always_adopted`/`missing_adopted`/`signature` and
`CuemsNetworkMapType.refresh` (`data-model.md` §5) exist in this repository now,
characterized against `CuemsNodeConf`'s current behaviour, but nothing calls
them yet. 009 is where `cuems-nodeconf` actually adopts this object and
deletes its own copies.

### T050 — prescribed fix, `cuems-nodeconf/cuemsnodeconf/CuemsNodeConf.py:579-583`

```python
def cleanup(self):
    try:
        os.remove(os.path.join(CUEMS_CONF_PATH, self.cm.show_lock_file))
    except FileNotFoundError:
        pass
```

`self.cm` is never assigned anywhere in the class — every call to `cleanup()` raises
`AttributeError` before the `try` block's own exception handling ever gets a chance
(the `except FileNotFoundError` does not catch `AttributeError`). Not fixed here (D16:
this feature does not edit consumer repositories). **Prescribed fix**: assign
`self.cm = ConfigManager(...)` in `__init__` (matching how every other daemon reads
`show_lock_file`) — or, more directly, since `CuemsNodeConf` already carries
`self.map_path` = `os.path.join(CUEMS_CONF_PATH, MAP_FILE)`, read
`show_lock_file` off a `ConfigManager` instance constructed the same way. 009 should
land this alongside the `NodeIndex` adoption, since both touch `CuemsNodeConf.__init__`.

### T052 — call-site entries for the adopt/unadopt dispatch chain

Per `data-model.md` §5's table:

- `cuemsnodeconf/CuemsNodeConf.py:113-144` (`engine_callback`) — `self.adopt_node(node_uuid)`
  and `self.unadopt_node(node_uuid)` (each returning a `{'OK': ..., 'error'?: ...}` dict) are
  replaced by `self.network_map.adopt(node_uuid)` / `.unadopt(node_uuid)` (each returning
  `bool`). The RPC response shape (`{'OK': bool, 'error'?: str}`) is `engine_callback`'s own
  concern, not `NodeIndex`'s — 009's port needs to reconstruct the error message
  (`"Node {uuid} not found"` / `"node is offline"` / `"Cannot unadopt master node"`) from the
  `False` return and which check failed, since the ported methods no longer carry that string.
- `cuemsnodeconf/CuemsNodeConf.py:440` (`merge_discovered_nodes`), `:490`
  (`set_master_always_adopted`), `:501` (`check_missing_adopted_nodes`) — replaced by
  `CuemsNetworkMapType.refresh(discovered, path)`, called from `refresh_network_map`
  (`:229-246`) in place of its current four-step body. `check_missing_adopted_nodes`'s
  logging call is not part of `refresh`'s orchestration (§5) — 009 must call
  `self.network_map.missing_adopted(discovered)` itself if the warning log is to survive
  the port.
- `cuems-frontend/src/app/components/settings/settings.component.ts:119-139`
  (`confirmRemoveNode`/`confirmAddNode`) — unaffected. The chain's *shape*
  (`nodelist_modify` → `{OK: bool}` response) does not change; only what runs on the
  daemon side of it does.

---

