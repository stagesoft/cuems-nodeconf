<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Request to `cuems-utils` — keep another cluster's controller out of a network map

**From**: `cuems-nodeconf`, branch `feat/xml-refactor`.
**For**: `cuems-utils`, to land **after feature 015's work is done** and **inside `0.1.1`**, the
coordinated release (`specs/planning/coordinated-release-version-bump.md`). Both conditions are
explained in §6.
**Written**: 2026-10-13, against `cuems-utils` `feat/xml-refactor` @ `75a958e`. Every coordinate
below was measured there. Re-measure before editing.
**Self-contained**: this document is everything the implementer needs. Nothing in
`../cuems-nodeconf` has to be read to do the work.

---

## 1. The defect, in one paragraph

Several CUEMS clusters share one LAN (the workshop has `test2`, `test` and `test3` side by side),
and every controller announces itself over mDNS. `NodeIndex.merge` adds **every** discovered node
whose uuid it has not seen, and `NodeIndex.set_controller_always_adopted` marks **every** controller
adopted. So a controller's `network_map.xml` gains the other clusters' controllers **as adopted
nodes**, and `cuems-engine` then counts them as members of its own cluster. This happened in the
field: `test2` adopted `test3` on 2026-10-01, and the `test` box on 2026-10-06.

It was fixed on the parallel release line (`cuems-nodeconf` `origin/rc_1`, commit `80ccc83`,
released as `0.1.0-8`) **inside the daemon**, because on that line the daemon still owned the merge.
On the refactor line the merge is this library's (decision D22: map mutations live on
`NodeIndex`/`CuemsNetworkMapType`, never in the daemon), so the fix has to land here. The coordinated
release's rule 4 (*merge before bump: nothing already shipped is lost*) makes that a requirement of
the release, not an enhancement.

## 2. The rule — taken from the shipped fix, unchanged

A node's **cluster controllers** are a set of uuids:

1. **On a controller**: exactly its own uuid.
2. **On any other node**: the uuids of every `controller`-role node its map already records (set
   when it joined).
3. **When that set is empty** (a fresh node, or a legacy map with no controller): no scoping at all.
   Every discovered controller is accepted, which is the first-come behaviour of today.

A node is a **foreign controller** when its `node_role` is `NodeRole.controller`, the cluster set
is **non-empty**, and its `uuid` is **not** in the set.

Foreign controllers are **ignored** when discovered, and **removed** from the map if an earlier,
unscoped pass already saved them. Removed, not marked offline: an offline row means "ours, currently
absent" (`cuems-nodeconf` `CLAUDE.md`, `<online>` ownership), which is exactly what a foreign
controller is not.

The cluster set is computed from the map **before** this pass's merge. Computing it after would let
the merge's own additions define the cluster.

## 3. Existing behaviour that must not change

- `CuemsNetworkMapType.refresh(discovered, path)` called **without** the new argument behaves
  byte-for-byte as today. `tests/contract/test_nodeindex_characterization.py` is the yardstick a
  sibling vendors, and it pins `test_set_controller_always_adopted_adopts_every_controller`. It must
  pass **unedited**.
- **Aliasing (T091/T092)**: nothing new may copy a node. Removal deletes a key from the index. Every
  node that stays is the same object it was (`tests/contract/test_node_aliasing.py`).
- **Write-if-changed**: removing a node changes `signature()`, so the existing comparison already
  writes. A second identical pass writes nothing.
- No new public module. Everything goes on `cuemsutils.tools.NodeList.NodeIndex` and
  `CuemsNetworkMapType`, both already public.

## 4. Tasks

Coordinates are at `75a958e`: `src/cuemsutils/tools/NodeList.py` (`class NodeIndex(dict)` :55,
`merge` :136, `set_controller_always_adopted` :243, `signature` :272) and
`src/cuemsutils/config/network_map.py` (`refresh` :141, body from :192). Write each test first and
watch it fail before the code that makes it pass.

### T1 — `NodeIndex.cluster_controllers`

```python
def cluster_controllers(self, own_uuid=None, own_role=None) -> frozenset:
    """The uuids of the controller(s) this node belongs to (rule §2).

    own_role is NodeRole.controller and own_uuid is truthy -> frozenset({own_uuid}).
    Otherwise -> the uuids of every node in self whose node_role is
    NodeRole.controller and whose uuid is truthy. May be empty, meaning "no scoping".
    Read-only.
    """
```

Tests (`tests/contract/test_foreign_controllers.py`, new):
- a controller with `own_uuid="u-master"` → `{"u-master"}`, even when the map holds other
  controllers;
- a non-controller whose map holds one controller `u-master` → `{"u-master"}`;
- a non-controller with an empty map → `frozenset()`;
- a controller row with no uuid is skipped.

### T2 — `NodeIndex.foreign_controllers` (read-only) and `is_foreign_controller`

```python
@staticmethod
def is_foreign_controller(n, cluster) -> bool:
    return (n.get("node_role") is NodeRole.controller
            and bool(cluster) and n.get("uuid") not in cluster)

def foreign_controllers(self, cluster) -> tuple:
    """The foreign controllers in self, as the node objects themselves. Read-only."""
```

`foreign_controllers` exists so that a caller can **log** what a pass is about to remove before it
calls `refresh`. `refresh` returns `bool` and must keep doing so.

Tests: an empty cluster gives `()` whatever the map holds; a `node`-role row is never foreign; the
returned objects are the index's own objects (`is`, not `==`).

### T3 — `NodeIndex.drop_foreign_controllers`

```python
def drop_foreign_controllers(self, cluster) -> tuple:
    """Delete every foreign controller's key from self; return the removed nodes."""
```

Tests: a saved foreign controller with `adopted=True, online=False` is removed (the key is gone,
not flipped); our own controller and every `node`-role row keep their identity (`is`); an empty
cluster removes nothing.

### T4 — `CuemsNetworkMapType.refresh(..., *, cluster=None)`

Add one keyword-only parameter. The body becomes:

```python
current = NodeIndex({...})              # unchanged
before = current.signature()            # unchanged
if cluster:
    discovered = {k: n for k, n in discovered.items()
                  if not NodeIndex.is_foreign_controller(n, cluster)}
current.merge(discovered)               # unchanged
if cluster:
    current.drop_foreign_controllers(cluster)
current.set_controller_always_adopted() # unchanged — only ours remain to adopt
# ...the rest unchanged
```

`cluster=None` and `cluster=frozenset()` both mean "unscoped", which is today's behaviour.
Document the parameter in the docstring with §2's rule, and say that the **caller** computes it
with `cluster_controllers` **before** calling `refresh`.

Tests (`tests/integration/test_network_map_refresh.py`, extended). These are the four regression
tests of the shipped fix, translated to this API:

1. **The controller ignores foreign controllers.** Own controller `u-master`; discovered: own
   controller, one new node, two foreign controllers. With `cluster={"u-master"}`: the map holds
   exactly `{u-master, u-slave}`, `u-master` is adopted, and `u-slave` is not (it waits for the
   operator).
2. **The controller removes a foreign controller saved earlier.** The map holds `u-master` plus a
   foreign controller saved with `adopted=True`. With `cluster={"u-master"}`: `refresh` returns
   `True`, and **the bytes written to `path`** no longer contain the foreign uuid. Check the file, not
   the object.
3. **A node keeps its recorded controller.** The map holds controller `u-master` and this node.
   Discovered: `u-master`, this node, and a foreign controller. With
   `cluster = index.cluster_controllers(own_uuid="u-slave", own_role=NodeRole.node)`: the map is
   `{u-master, u-slave}` and `u-master` is online.
4. **A fresh node accepts the first controller.** Empty map. `cluster_controllers(...)` is empty.
   Discovered controller `u-master` is added and adopted, exactly as without the argument.

Plus:
- **Unchanged without the argument**: two controllers discovered and no `cluster` → both added and
  both adopted (today's behaviour, now stated by a test).
- **Idempotent**: a second `refresh` with the same inputs returns `False`.
- **Aliasing**: extend `tests/contract/test_node_aliasing.py` with one case, where a node object
  held by the caller before a scoped `refresh` is still the object in `node_list` afterwards.

### T5 — Documentation

- `NodeIndex`'s and `refresh`'s docstrings carry §2's rule and §5's limitation.
- The migration guide of whichever feature lands this gets one entry: the new keyword, the three
  new methods, and *"`cuems-nodeconf` passes `cluster`; no other consumer needs to"*.
- Name **this document** in comments, not a feature number. Numbers get reassigned
  (`hardware-outputs-capability-layer.md` §6).

## 5. Known limitation — stated, not fixed

A **fresh** node on a shared LAN, whose first pass hears two clusters' controllers, accepts both,
because its cluster set is empty (rule §2.3), and from then on both are "its" controllers. The
shipped fix has the same limitation. Fixing it needs a join protocol (which controller a node
belongs to), and that is part of `cuems-nodeconf`'s planned controller-election feature, not this
request. Do not try to solve it here.

## 6. Ordering and release

- **After 015.** 015 is in progress, and this request touches `NodeList.py`, the same file as its
  gate G4 (`NodeIndex.set_alias`). Landing it after avoids conflicts. It needs nothing from 015.
- **Inside `0.1.1`.** The coordinated release bounds consumers at `>= 0.1.1, << 0.1.2~`, so
  `cuems-nodeconf` can rely on the keyword with no feature detection. If it misses `0.1.1`, say so
  in the release notes: the consumer then publishes without the fix, and rule 4 of the bump
  document is broken for this item.
- **On the consumer side** (for information only, not a task here): `cuems-nodeconf` ships an
  interim filter on discovery in its own code, which keeps **new** foreign controllers out but
  cannot remove saved ones (D22). Its regression test for removal is a strict `xfail` naming this
  document. When this lands, the daemon deletes its interim filter, computes `cluster` with
  `cluster_controllers(settings_uuid, own_role)`, logs `foreign_controllers(cluster)`, passes
  `cluster=` to `refresh`, and the `xfail` turns `XPASS`.
