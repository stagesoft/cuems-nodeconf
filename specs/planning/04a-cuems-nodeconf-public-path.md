<!-- VENDORED 2026-09-17 from cuems-utils@9e5e79f:
     specs/planning/xml-rebuild/010-consumer-prompts/04a-cuems-nodeconf-public-path.md
     Body kept VERBATIM so it stays byte-comparable with upstream's copy. Two notes:
       - the `Repository:` line below names the author's own checkout
         (/disk/Projects/StageLab/cuems-nodeconf), which does not exist on this machine.
         Left as provenance; this repository's own artefacts use relative paths only.
       - VALIDATED against this tree at b3f5bb0 on 2026-09-17, and it holds: every cited
         coordinate (:21, :260, :290-292, :455-462, :521-544, :179-185), the 28 patch.object
         sites across 6 files (9/6/5/5/2/1, all 'save'), config.__all__ == [], the live
         CuemsNetworkMapType from ConfigManager.network_map, and the empty <node_list/>
         conffile at debian/install:204. NOT IMPLEMENTED — read and validated only. -->

# Feature 010 — `cuems-nodeconf`: close the last internal import

**Status:** ready to run — **follow-up to [04-cuems-nodeconf](04-cuems-nodeconf.md)**, not a new flow
**Date:** 2026-09-17
**Repository:** `/disk/Projects/StageLab/cuems-nodeconf`
**Raised by:** `cuems-utils`' wave-1 gate (feature 010, T029/T030 — see
`cuems-utils/specs/010-consumer-migration/migration-guide.md` §4a)

---

## 0. What this is, in one paragraph

Feature 001's network-map swap landed cleanly: it removed the two
`cuemsutils.xml` internal imports the migration asked it to remove
(`mapper`'s `Mapper`/`read_config_document`, `settings`' `NetworkMap`). In doing
so it introduced **one new internal import** that nobody scheduled, because at
the time there appeared to be no public alternative:

```
cuemsnodeconf/CuemsNodeConf.py:21   from cuemsutils.config.network_map import CuemsNetworkMapType
```

`cuemsutils.config.__all__` is `[]`, and `cuemsutils/tools/NodeList.py`'s own
module docstring is explicit: *"a consumer imports `node` from here, never from
`cuemsutils.config.network_map`."* D34 says the config objects reach this
repository through **public** paths.

**There is a public path, and it already exists** — it was missed on both sides.
This prompt is that finding plus its verification, so the change can be made
without re-deriving it.

**This is not a request to change `cuems-utils`.** FR-025's instruction is *name
the existing equivalent rather than adding a synonym*, and the equivalent
exists. `cuems-utils` is adding **no** public alias for this class (its T084).

---

## 1. The finding, measured rather than argued

`ConfigManager.network_map` **already returns a live `CuemsNetworkMapType`**,
with `.save` and `.refresh` on it. Measured against `cuems-utils` @ `d0340fc`
(`0.1.0rc16`):

```
ConfigManager.network_map -> cuemsutils.config.network_map.CuemsNetworkMapType
  is CuemsNetworkMapType : True     has .save : True     has .refresh : True
```

**Why both sides missed it**: `ConfigManager.load_network_map` reads

```python
self.network_map = netmap.get_dict()
```

which looks like it yields a plain dict. It does not — `get_dict()` returns the
value under the document's `main_key`, and for `network_map` that value *is* the
bound object. `save_network_map` already depends on this (`self.network_map.save(...)`),
so the behaviour is load-bearing, not incidental. `cuems-utils` is correcting
that spelling and a contradictory type annotation on the setter (its T083); the
behaviour does not change.

---

## 2. The change

This daemon never needs to **name** the class. It needs to stop **constructing**
a document and start **refilling** the one it already holds. That preserves
feature 001's own design — *"the index in `self.network_map` stays the single
in-memory source of truth"* (`refresh_network_map`'s docstring) — exactly, since
`node_list` is overwritten wholesale either way.

```python
# before — cuemsnodeconf/CuemsNodeConf.py:290-292
def _network_map_document(self):
    """The persisted form of self.network_map, built fresh from the index."""
    return CuemsNetworkMapType(node_list=[{"node": n} for n in self.network_map.values()])

# after — no import; the document comes from the public façade and is refilled
def _network_map_document(self):
    self._document["node_list"] = [{"node": n} for n in self.network_map.values()]
    return self._document
```

`self._document` comes from `read_network_map`'s **existing**
`ConfigManager.load_network_map()` call (`:521-544`). That call is already made;
what changes is that its result stops being thrown away — today the method builds
the index from `manager.network_map` and then lets both the manager and the
document go out of scope.

**Verified end to end** against `0.1.0rc16`, importing only `cuemsutils.tools.*`:
load through `ConfigManager`, refill `node_list`, then `document.save(path)`,
`document.refresh(discovered, path)` and `ConfigManager.save_network_map(path)` —
all three succeed.

### Call sites

| Site | What it does today | After |
|---|---|---|
| `:21` | the import | **deleted** |
| `:290-292` `_network_map_document` | constructs a document per call | refills and returns the retained one |
| `:260` `refresh_network_map` | `document = self._network_map_document()` then `document.refresh(...)` | unchanged in shape |
| `:455-462` `_save_network_map` | `self._network_map_document().save(self.map_path)` | unchanged in shape |
| `:521-544` `read_network_map` | builds the index from `manager.network_map`, discards the document | **retain the document** as `self._document` |

---

## 3. The first-run branch — decide this deliberately

`run()` at `:179-185`:

```python
self.is_first_run = not os.path.isfile(self.map_path)
if not self.is_first_run:
    self.read_network_map()
else:
    self.network_map = NodeIndex()      # no document is ever loaded
```

On that branch there is no document to retain, and **nothing public constructs an
empty network-map document** — `ConfigManager.network_map` is the bare `{}` that
`__init__` sets, with no `.save`, and `cuems-utils`' descriptor hands back a plain
`dict` (deliberately), so it does not serve either.

**In deployment this branch is dead.** `cuems-common` ships
`/etc/cuems/network_map.xml` with an empty `<node_list/>` as a conffile
(`cuems-common/debian/install:204`), and this package `Depends: cuems-common (>= 1.0.0)`.
On any packaged host the file exists, so `is_first_run` is false. The branch is
reachable only on a dev checkout or a host where the file was deleted by hand.

Three honest options — **pick one and record why**, do not leave it implicit:

| | Approach | Cost |
|---|---|---|
| **A** | On the first-run branch, write a minimal empty map with stdlib `ElementTree` (four lines, the same shape `cuems-common` ships), then `load_network_map()` it | Fully closes the import. A little indirect: writing a file to be able to read it back |
| **B** | Keep the import, guarded, for this branch only | Honest and small, but leaves `__all__ == []` violated on a path that never runs in the field — which is the sort of exception that outlives its reason |
| **C** | Delete the first-run branch; require the conffile, and fail loudly if it is absent | Smallest code. Turns a silent degradation into a clear error, which suits a daemon whose output other services read — but it is a behaviour change and needs its own justification |

**Recommendation: A**, with C worth considering on its merits. If B is chosen,
say so in the code at the import, with the reason and the condition under which
it could be removed.

---

## 4. The tests are a separate decision — do not fold them in silently

**Six test files import the class, at 28 `patch.object(CuemsNetworkMapType, 'save')`
sites**, measured at `b3f5bb0`:

```
tests/test_integration.py     9      tests/test_node_adoption.py   6
tests/test_adoption_flow.py   5      tests/test_network_map.py     5
tests/test_missing_nodes.py   2      tests/test_engine_callback.py 1
```

These patch the class because that is how you stop a test writing to `/etc`. They
are **not shipped code**, and D34's constraint is about what the daemon reaches
for at runtime. Decide explicitly whether:

- the tests keep the import (defensible: a test patching a collaborator is not a
  consumer using an API), or
- they move to patching through the retained instance, or via a string target
  (`patch('cuemsutils.config.network_map.CuemsNetworkMapType.save')`), which
  removes the import but still names the internal path.

Whichever is chosen, **state it** — "the shipped import is closed; the test
imports are kept, because X" is a complete answer. Pretending 28 patch sites
disappear is not.

### ⚠️ The vendored yardstick MUST NOT be touched

`specs/planning/yardstick/test_nodeindex_characterization.py:23` reads

```python
from cuemsutils.config.network_map import node
```

That file is **byte-identical to `cuems-utils/tests/contract/test_nodeindex_characterization.py`
and must stay so** — it is the yardstick feature 001's equivalence claim rests on,
and its guarantee depends on not being edited from this side. It is **out of scope
here**, permanently. If the count of internal imports is reported anywhere, the
yardstick is an enumerated exemption with that reason, not a site to fix.

---

## 5. Acceptance

- [ ] `grep -rn "from cuemsutils.config" cuemsnodeconf/` returns **nothing**
- [ ] The full suite passes **unchanged in intent** — 110 at `b3f5bb0`
      (95 local + 15 yardstick). Tests may change *how* they patch; no test's
      subject or assertion changes to accommodate the new shape
- [ ] The vendored yardstick is still byte-identical to `cuems-utils`' copy —
      `diff` it, do not assume it
- [ ] `refresh_network_map`'s "index is the single source of truth" guarantee is
      still true: an operator adoption made between passes is not lost to a stale
      document. Add a test if one does not already cover it — the retained
      document is a new opportunity for exactly that staleness
- [ ] The first-run decision from §3 is recorded, with its reason
- [ ] The test decision from §4 is recorded, with its reason

## 6. What NOT to do

- **Do not** ask `cuems-utils` for a public alias. It has declined, by decision
  (its T084), on FR-025's "name the equivalent rather than add a synonym"
- **Do not** reach the class via `type(manager.network_map)`. It works and it
  reads as a mistake — the next person deletes it
- **Do not** reimplement `refresh`'s orchestration (merge → controller-always-adopted
  → write-if-changed) locally to avoid needing a document. That is precisely what
  D22 moved into the library, and feature 001 removed from here
- **Do not** edit the vendored yardstick (§4)
- **Do not** take this as licence to revisit row 5 or the other nine
  responsibilities — D23 still holds

---

## 7. Context to read first

| | |
|---|---|
| `cuems-utils/specs/010-consumer-migration/migration-guide.md` §4a | the finding, its measurement, and why the first framing of it was wrong |
| `cuems-utils/specs/010-consumer-migration/tasks.md` T083, T084 | what `cuems-utils` is doing about it, and what it is not |
| this repository's `specs/001-network-map-object-adoption/` | the feature this closes out |
| this repository's `specs/001-network-map-object-adoption/upstream-report.md` | the three findings sent the other way, for symmetry |
