<!-- VENDORED from cuems-utils@b7598d5 specs/007-node-model-migration/migration-guide.md §§4, 4a -->

> **Status (2026-10-13): SUPERSEDED — confirmed in feature 001.** See `README.md` for the index.

# Feature 007's handover — CONFIRM, do not redo (FR-030a-i)

## 4. The moved-symbol table (T084)

**Scope note, updated**: `cuems-utils` (Phases 1–4, 6, 8) landed in an earlier pass. Phase 5 (US3,
`cuems-common`) and Phase 7 (US5, `cuems-nodeconf`), descoped from that earlier pass, have now
landed too — each on its own `007-node-model-migration` branch, in its own repository, as **local
commits only**. Nothing in either sibling repository has been pushed or merged; §7 (the release
gate) states what that does and does not authorise. The table below now reflects the actual state
of every symbol T006a's inventory named, not an intended one.

| Source | New home | Status | Authorising requirement |
|---|---|---|---|
| `cuemsnodeconf.CuemsNode.node` | `cuemsutils.config.network_map.node` (internal) / `cuemsutils.tools.NodeList.node` (public re-export) | **landed** — typed, tested (C1–C11), constructible directly (FR-004) | FR-002, FR-002b, data-model §3.2 |
| `cuemsnodeconf.CuemsNode.node_list` | `cuemsutils.config.network_map.node_list` | **landed** — unchanged from feature 006, registry-bound | FR-002, data-model §3.3 |
| `cuemsnodeconf.CuemsNode.CuemsNodeDict`, `CuemsNode` (aliases) | *(deleted, not recreated)* | **landed** by policy — FR-002a is explicit that no shim is created | FR-002a |
| `cuemsnodeconf.AvahiTool.NodeType` (enum) | `cuemsutils.tools.NodeList.NodeRole` | **landed** — values verified against the loaded schema (C1) | FR-001, research R3 |
| `cuemsnodeconf.NodeXmlBuilders.{node,node_list}XmlBuilder` | `cuemsutils.xml.documents.build_tree` (registry-driven, via `CuemsNetworkMapType.save`) | **landed** — the write path exists and is tested (C4, C5) | FR-009, research R6 |
| `cuemsnodeconf.NodeXmlBuilders.{node,node_list}Parser` | `cuemsutils.xml.mapper.Mapper.decode_config` (registry-driven) | **landed** — was already true from feature 006's bindings | FR-011a, research R1 |
| `cuemsnodeconf.NodeXmlBuilders.STRING_TYPED_NODE_FIELDS` | *(deleted, not recreated — structural guarantee instead)* | **landed** — `tests/contract/test_node_field_coercion.py` asserts its absence (T064) and the structural replacement (T065) | FR-012, research R4 |
| `cuemsnodeconf.CuemsNodeConf`'s MAC-keyed working set | `cuemsutils.tools.NodeList.NodeIndex` | **landed** — `CuemsNodeConf.__init__`, `read_network_map`, `write_network_map` and every call site now build/consume a `NodeIndex` (T074) | research R5 |
| `cuemsnodeconf.CuemsNode.py`, `NodeXmlBuilders.py` (the files) | *(deletion target)* | **landed** — both files deleted (T071, T072), local branch | FR-018 |
| `cuemsnodeconf.CuemsNodeConf.py`'s `node_type` normalisation, hand-rolled atomic write, `XmlReader`/`XmlWriter` use | *(removal target — the upstream model and `save()` make each unnecessary)* | **landed** — `read_network_map` has no normalisation left (T075), `write_network_map` calls `CuemsNetworkMapType.save()` (T076), no `XmlReader`/`XmlWriter` import remains in `CuemsNodeConf.py` (T077; `CuemsHwDiscovery.py` named in the task does not exist in this repository — confirmed by directory listing, so there was nothing to retire there) | FR-015, FR-031, research R6 |
| discovery/adoption/orchestration symbols (`CuemsAvahiListener`, `CuemsConfServer`, `AliasPublisher`, `AvahiTool` minus its enum) | *(stay in `cuems-nodeconf`)* | **not applicable** — FR-032 says these do not move | FR-032 |

## 4a. The consumer's public import path (T084a)

```python
from cuemsutils.tools.NodeList import NodeRole, NodeIndex, node
```

**`cuemsutils.config` is internal.** `cuemsutils.config.__all__ == []` (contract C10) — a consumer
importing `cuemsutils.config.network_map.node` directly is importing an implementation detail that
happens to work today, the same status every name reachable through the emptied `cuemsutils.xml`
has carried since feature 006. `cuemsutils.tools.NodeList` is the one path this feature commits to.

---

## 5. What `cuems-engine` must change in feature 009 (T085)

Verified against the live call sites in `cuems-engine/src/cuemsengine/core/BaseEngine.py` at this
commit (`afff04a`), not transcribed from the spec:

| Site | Today | Must become |
|---|---|---|
| `BaseEngine.py:33` — `CONTROLLER_NETWORK_FLAG = "NodeType.master"` | a module-level string constant | `from cuemsutils.tools.NodeList import NodeRole`; compare against `NodeRole.controller` |
| `BaseEngine.py:410` — `node.get("node_type") == CONTROLLER_NETWORK_FLAG` (`_controller_ip_from_map`) | reads a key the converted document no longer has | `node.get("node_role") is NodeRole.controller` — and `node` is a typed object once `self.cm.network_map` is read through the migrated `ConfigManager`, so `.get` still works (it's dict-shaped) but the *value* comparison must change too |
| `BaseEngine.py:440` — same comparison, in the adopted-nodes host list | same | same fix |
| `BaseEngine.py:443` — `node.get("online") == "True"` | string comparison | `node.get("online") is True` — **found during this task's verification**, not in the original T006f inventory; independent of the `node_type` rename (§3's table, added row) |
| `BaseEngine.py:433` — `self.cm.network_map.get_nodes_by_adoption(network_dict)` | calls the now-deprecated, mutating method | migrate to `NetworkMap.partition_by_adoption(self.cm.network_map)` (US6, T082) — returns bare node objects, not `{"node": ...}` wrappers, so the unpacking at the call site changes shape too |

