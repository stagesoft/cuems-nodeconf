# Phase 0 — Research

Nine decisions — eight from plan time, measured against `cuems-utils@d0340fc` (`0.1.0rc16`),
and D-I added during implementation. Where a planning document asserted something, it was
re-checked rather than transcribed; two assertions did not survive planning, and two of this
file's own (D-A, D-G) did not survive implementation — both revised in place, originals kept.

---

## D-A — Who owns the map state: one source of truth that refresh always sees

> **Revised during implementation (2026-09-15).** The decision originally recorded here
> was "hold the **document** as the source of truth and derive an index per mutation".
> Implementing it literally breaks row 4, so it was reversed in direction while keeping
> its constraint. The original text is kept below the revision for the record.

**Decision, as implemented**: `self.network_map` **stays a `NodeIndex`** and is the single
in-memory source of truth. Each refresh builds a `CuemsNetworkMapType` from it, calls
`refresh`, and reads the merged `node_list` back into the index. Every save builds a
document from the index the same way.

**Why the original decision was reversed**: `_should_resume_master` (row 4) reads the map
as an index — `self.network_map.get(self.node['mac'])`. On a `CuemsNetworkMapType` that
silently returns `None`, disabling resume-master detection and sending a firstrun
controller down `set_node_role` → `change_network_to_master`: the networking restart that
method's own comment says must not happen on a resume. A caller that keeps resolving but
becomes wrong (FR-030a-ii), in a row FR-024 says not to touch.

**Why the reversal is still correct**: the constraint that drove the original decision —
`refresh` must always see operator adoptions made between passes — is met, because the
document is rebuilt from the index on every pass rather than held alongside it. Measured:
the index, the document's `node_list` and `refresh`'s internal index all hold the *same*
node objects, so nothing is copied and in-place merge updates reach the index.

**Original decision (superseded)**: `CuemsNodeConf` holds a **`CuemsNetworkMapType`** as
its single source of truth. Every mutation derives a `NodeIndex` from `node_list`, mutates
it, writes `node_list` back, and saves.

**Rationale**: measured in the library source —

```python
# CuemsNetworkMapType.refresh(discovered, path)
current = NodeIndex({item["node"]["mac"]: item["node"]
                     for item in (self.get("node_list") or [])})
before = current.signature()
current.merge(discovered); current.set_controller_always_adopted()
if current.signature() == before: return False
self["node_list"] = [{"node": n} for n in current.values()]
self.save(path); return True
```

`refresh` **rebuilds its index from `node_list` on every call** and writes the result
back. `adopt`/`unadopt`/`missing_adopted`/`signature` live on `NodeIndex`; `refresh`/`save`
live on `CuemsNetworkMapType`; and **there is no public `NodeIndex` accessor on either
class** (checked: `NodeIndex` appears in `network_map.py` only inside `refresh`'s body and
its docstring, and not at all in `ConfigManager`).

**Alternatives considered**:

- *Keep `self.network_map` as a `NodeIndex`, as today.* Originally rejected as losing data
  — but that holds only if a document is *also* kept long-lived beside it. Building the
  document from the index on every pass removes the divergence, and this is what was
  implemented (see the revision above).
- *Hold both and keep them synchronised.* Rejected: two sources of truth for the cluster's
  topology, in a daemon whose constitution names exactly that as a correctness concern.
- *Ask upstream for a `NodeIndex` accessor.* Reasonable, and worth raising — but it edits
  the library mid-feature for ergonomics, and the seam is four lines. Recorded as a
  follow-up, not done here.

**Consequence**: the derive/write-back pair is a small daemon-side adapter. It holds no
state and disappears if the library later exposes an accessor. It is row 5 shrinking to a
seam, not an eleventh responsibility (constitution V).

---

## D-B — The bool is two-way ambiguous; the daemon re-runs the check

**Decision**: after a `False` return, the daemon looks the uuid up itself to decide which
error string to send.

**Rationale**: measured —

| Call | Returns `False` when |
|---|---|
| `NodeIndex.adopt(uuid)` | the uuid is **not present** *or* the node is **offline** |
| `NodeIndex.unadopt(uuid)` | the uuid is **not present** *or* the node is **the controller** |

The migration guide says to reconstruct the message "from the `False` return and which
check failed" — but the return does not say which check failed. So the discrimination is:

```
adopt   -> False: uuid absent            => "Node {uuid} not found"
                  uuid present, offline  => "Cannot adopt node {uuid}: node is offline"
unadopt -> False: uuid absent            => "Node {uuid} not found"
                  uuid present, controller => "Cannot unadopt master node"
```

A uuid lookup against the map is a read, not domain logic — it does not reintroduce what
D22 moved out.

**Alternatives considered**: change the library to return a reason enum. Rejected for this
feature — it is an API change to a class that just landed, and the yardstick pins the bool.
Worth proposing separately.

**Note**: the daemon's current success path returns `{'OK': True, 'message': 'Node already
adopted'}`. `engine_callback` forwards only `OK` and `error`, so `message` never reaches
the UI today. Dropping it is not a contract change.

---

## D-C — `cleanup()` is deleted, not repaired

**Decision**: delete the method.

**Rationale**: two measurements, either of which would be sufficient.

1. **It has no callers.** `grep` for `cleanup` across the package returns only its own
   definition. It is dead code that would raise `AttributeError` if anything called it.
2. **Repairing it would make `settings.xml` a construction-time requirement of the
   daemon.** `show_lock_file` is `ConfigBase.settings['show_lock_file']`, and
   `ConfigManager.__init__` calls `ConfigBase.__init__`, which calls
   `load_base_settings()` **unconditionally — `load_all=False` does not skip it**.
   Verified by running it against a directory holding only `network_map.xml`:
   `FileNotFoundError: Configuration file .../settings.xml not found`.

So "assign a `ConfigManager` in `__init__`", as the migration guide prescribes, would add
a hard boot-time dependency to a daemon under a 60 s systemd start budget, and would break
every existing test that constructs `CuemsNodeConf()` — for a method nothing calls.

**Alternatives considered**:

- *Assign lazily via a property.* Works, but keeps a dead method alive and still drags a
  `ConfigManager` in the first time anything touches it.
- *Assign in `__init__` inside a `try`.* Trades a crash for a silently absent attribute —
  the same defect in a quieter form.
- *Read `show_lock_file` some other way.* Solving a problem no caller has.

The spec permits "fixed or deleted" (FR-012); the evidence points one way.

---

## D-D — Adopt and unadopt must still persist

**Decision**: after a successful `adopt`/`unadopt`, the daemon writes `node_list` back and
calls `save(path)`.

**Rationale**: `NodeIndex.adopt` and `.unadopt` **mutate only**. The daemon's current
`adopt_node`/`unadopt_node` each call `write_network_map` on success, so the operator's
change is on disk before the response is sent. Nothing in `refresh` covers this — a change
left in memory would survive only until the process restarted, and would look like it had
worked. Constitution II.

**Alternatives considered**: let the next `refresh` persist it. Rejected: `refresh` writes
only when the signature changed, which it would have — but the window between the UI's
`{'OK': True}` and the next tick is up to 30 s of unpersisted state, across which a
restart loses the adoption silently.

---

## D-E — `missing_adopted` is called by the daemon, on the same argument

**Decision**: keep the warning. Call `missing_adopted(discovered)` explicitly, with the
same mapping passed to `refresh`.

**Rationale**: the library's own docstring states that `missing_adopted` is reporting-only
and deliberately excluded from `refresh`'s orchestration, because it never affects the map
or the write decision. Reproducing today's log therefore requires an explicit call. The
spec's FR-007 makes keeping it a requirement rather than a choice; the alternative
(dropping it) would silently remove an operator-facing signal about absent nodes.

---

## D-F — The first-run branch: nothing to reconcile

**Decision**: closed before this plan. No first-run parameter is needed on
`set_controller_always_adopted`, and none is requested.

**Rationale**: the branch was deleted in its own commit after being shown to have no
reachable correct effect. `specs/planning/08-firstrun-signals.md` carries the proof and the
options for any future first-boot requirement.

**Upstream note, not this feature's to fix**: `NodeIndex.set_controller_always_adopted`'s
docstring still reads *"The controller is always adopted; on a first run, nothing else
is."* The method has no first-run behaviour. `CuemsNetworkMapType.refresh`'s docstring
likewise still describes the un-ported branch as an open item. Both should be corrected in
`cuems-utils`; report rather than patch, since the yardstick's guarantee depends on that
file not being edited from this side.

> **✅ Closed 2026-09-17** — reported (T049) and both docstrings rewritten upstream in `cuems-utils`
> `9e5e79f` (their T082). See `upstream-report.md`.

---

## D-G — The public load path is equal in result, verified not assumed

**Decision**: replace `cuemsutils.xml.settings.NetworkMap` with
`ConfigManager.load_network_map()` + `.network_map`. Delete `Mapper` and
`read_config_document` outright.

**Rationale**: run against the library's own fixture —

```
PUBLIC   type: CuemsNetworkMapType   refresh: True  save: True
INTERNAL type: CuemsNetworkMapType
EQUAL IN RESULT: True
```

The public accessor returns the same object type with the same content, and it carries
`refresh`/`save` — so it is both the replacement for the internal reader *and* the source
of the document object D-A requires. The other two names were measured to have no call
site beyond the import line, so no public equivalent is needed for them.

**Caveat inherited from D-C**: `ConfigManager` construction requires `settings.xml`. The
daemon reads its map at `:176-181`, on a node where `cuems-common` has installed that file,
so this is satisfied in production — but it is a new failure mode at boot if the config
package is absent or broken. The load already sits inside `run()`'s `sys.exit(-1)` region,
so the failure is loud rather than silent, which is the right shape. Called out for the
implementer.

> **Revised during implementation (2026-09-15).** The move was briefly held. A file search
> of the sibling checkouts found no package that ships `/etc/cuems/settings.xml`
> (`cuems-config-node` only edits an existing one), and `ConfigBase` schema-validates the
> file at construction — so the concern was that topology discovery would become coupled
> to an unrelated configuration file.
>
> **Resolved the same day, by the maintainer:** `cuems-nodeconf` is never a standalone
> service. Its `cuems-utils` and `cuems-common` dependencies provision
> `/etc/cuems/settings.xml` on every node, so nodeconf always finds both `settings.xml` and
> `network_map.xml`. The premise rests on that statement; the file search did not locate
> the provisioning step. **The decision above stands and is implemented** (T004/T009),
> reading from the map's own directory so the read and write paths are the same file.
>
> Consequence, accepted: a `settings.xml` that fails validation now stops nodeconf's boot
> read as well as the engine — loudly, never by falling back to an empty map. Tests and
> standalone development provision both files through the `cuems_conf_dir` fixture
> (`tests/fixtures/etc_cuems/`), never the real `/etc/cuems`.
>
> **Found while implementing it — a contract the internal reader did not have.**
> `ConfigManager.load_network_map()` ends by resolving *this node's own entry* by the
> `settings.xml` uuid, and raises `ValueError` when the map does not list it. That is
> every freshly provisioned node: `cuems-config-node write` gives `settings.xml` a new
> uuid and leaves `network_map.xml` alone, and `cuems-common` ships a map listing one
> controller. Measured on exactly that node: the public path raised, the internal reader
> loaded, and the engine's own `load_all=True` path raised too. nodeconf is the service
> that writes a new node into the map, so it must be able to read such a map. The earlier
> "equal in result" measurement missed this only because its fixture happened to contain
> the settings uuid.
>
> **Decision (maintainer, 2026-09-15):** `read_network_map` catches **only** that
> lookup's `ValueError`. By then the map is loaded and validated; broken documents raise
> `SchemaError`/`ValidationError`, which are not `ValueError`s; and if the map was not
> populated the exception propagates. Pinned by `test_reads_a_map_that_does_not_list_this_node_yet`
> and `test_a_map_that_fails_validation_still_fails_loudly`. **Upstream, to report:** the
> eager lookup makes the accessor unusable as-is by the map's own writer.

---

## D-H — How this repository's CI reaches the yardstick

**Decision**: run it as a separate, explicit invocation —
`pytest specs/planning/yardstick/` — alongside `pytest tests/`, and require both green.

**Rationale**: the constitution's testing gate asks this repository to say how it reaches
the equivalence gate or record the manual procedure honestly. The yardstick is vendored
here and imports only `cuemsutils` (no daemon modules, no `dbus`/`zeroconf` stubs), so it
runs unmodified in this repository's environment — measured: 15 passed. Keeping it a
separate invocation rather than folding it under `tests/` preserves the README's read-only
rule and keeps its provenance visible: it is `cuems-utils`' file, run here, not this
repository's test.

**Alternatives considered**:

- *Add `specs/planning/yardstick` to `testpaths`.* Would make it look like a local test and
  invite editing — the precise failure the vendoring note warns about.
- *Reach into the sibling checkout.* Rejected: the whole point of the vendoring was to make
  this repository self-contained.

---

## D-I — Two write behaviours the library call alone would lose

*Added during implementation (2026-09-15).*

**Decision**: the daemon keeps a `_map_write_pending` flag that owes the next refresh a
write, independent of whether discovery changed anything. It starts `True` and is set
again whenever a save fails.

**Rationale**: measured against `CuemsNetworkMapType.refresh` —

- **Retry after a failed write.** When `save` raises, `refresh` has *already* reassigned
  `node_list`. On the next pass it therefore sees no change and never retries, leaving the
  map on disk stale until an unrelated node event. The pre-migration daemon retried every
  pass, because its signature cache advanced only on a successful write.
- **The start-up write.** The pre-migration cache began empty, so the first discovery pass
  always wrote the map. Without the flag, a loaded map identical to discovery is never
  rewritten at boot.

Both behaviours were pinned by tests committed and proven green against the pre-migration
code *before* the swap (`test_network_map.py`).

**Alternatives considered**: let `refresh` alone decide. Rejected — the write-if-changed
rule answers "did discovery change the map?", not "is the disk behind memory?", and the
daemon is the only party that knows a write failed.
