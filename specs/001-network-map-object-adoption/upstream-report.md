# To report upstream in `cuems-utils` — three findings, none of them patched here

> ## ✅ All three closed upstream, 2026-09-17 — none patched from this side
>
> | Finding | Resolution |
> |---|---|
> | 1. `save_document` leaves the target `0600` | **Fixed** in `6fe2d3f`, at the choke point `write_tree`, so it covers every `save_document` consumer. `tests/contract/test_save_permissions.py` (their T081) written failing-first: 6 of 10 assertions failed pre-fix, 10/10 pass now. Re-measured here against `9e5e79f`: `0644` in, `0644` out |
> | 2. `set_controller_always_adopted`'s docstring | **Rewritten** in `9e5e79f` (their T082a) — now states there is deliberately no first-run behaviour, and why the deleted branch was harmful |
> | 3. `refresh`'s "open item" paragraph | **Rewritten** in `9e5e79f` (their T082b) — now says the item is closed, and closed in the library's favour |
>
> Received in `b6b5eb5` ("receive nodeconf's upstream report"); their T080-T084 are all `[X]`. The
> discipline held in both directions: every fix landed in the library, and the vendored yardstick is
> still byte-identical (`sha256 6212292683…`, untouched by the pull).

**Raised 2026-09-17 from `cuems-nodeconf`'s feature 001** (T049 and T052). Measured against
`cuems-utils` @ `d0340fc` (`0.1.0rc16`). Nothing in this document has been fixed from this
side, deliberately: the yardstick's guarantee depends on
`tests/contract/test_nodeindex_characterization.py` not being edited by its consumer, and
the same discipline applies to the library it characterizes. Re-measure before acting.

---

## 1. `save_document` leaves the target `0600` — a permissions defect, not cosmetics

**Where**: `src/cuemsutils/xml/documents.py:189-195`.

```python
handle, temporary = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
os.close(handle)
tree.write(temporary, encoding="utf-8", xml_declaration=True)
os.replace(temporary, target)
```

`tempfile.mkstemp` creates its file `0600` by construction, and `os.replace` carries the
**temporary file's** mode onto the target. Every save therefore resets the document's
permissions, silently, however the file was installed.

**Measured** in `cuems-nodeconf`, twice:

| | |
|---|---|
| `/etc/cuems/network_map.xml` before a save | `0644` (the mode `cuems-common` ships) |
| after `CuemsNetworkMapType.save(...)` | **`0600`** |

The second measurement used the pre-feature call path verbatim, so this is **not** a
regression introduced by feature 001 — it is long-standing library behaviour that feature
001 merely inherited and noticed.

**Why it is not cosmetic.** `network_map.xml` is the cluster's topology and is read by
processes that are not the one that wrote it:

- `cuems-nodeconf` runs as **root** (`cuems-nodeconf.service` declares no `User=`).
- `cuems-controller-engine` and `cuems-node-engine` run as **`User=cuems`**
  (`cuems-common/etc/systemd/system/cuems-*-engine.service:20-25`).

So the first map write on any node makes the topology root-only, and the non-root engine
loses the file it reads. That is the same failure shape as the `/tmp/nodeconf.ipc`
crash-loop recorded in `cuems-nodeconf`'s CLAUDE.md: a root process creating something a
non-root service must read. `cuems-common` ships the file `0644` (`debian/install:204`)
precisely so the engine can read it.

**Suggested fix, upstream**: preserve the target's existing mode across the replace — stat
the target before writing and `os.chmod` the temporary to match, falling back to
`0644 & ~umask` when the target does not yet exist. Both callers that matter
(`save_network_map` and every other `save_document` consumer) get it for free.

**Not worked around here.** `cuems-nodeconf` could `chmod` after every save, but that would
put a permissions rule in the consumer for a guarantee the writer owes, and every other
consumer of `save_document` would still be exposed.

---

## 2. `NodeIndex.set_controller_always_adopted`'s docstring describes behaviour it does not have

**Where**: `src/cuemsutils/tools/NodeList.py:177`.

```python
def set_controller_always_adopted(self) -> None:
    """The controller is always adopted; on a first run, nothing else is."""
```

The method has no first-run behaviour and no parameter that could carry one — it sets
`adopted = True` on controllers and touches nothing else. The clause "on a first run,
nothing else is" describes the daemon branch that was deliberately **not** ported.

A reader of this docstring would reasonably conclude the library still clears
non-controller adoption on a first run. It does not, and `cuems-nodeconf` deleted the
branch that did, having measured it to have no reachable correct effect
(`specs/planning/08-firstrun-signals.md`).

---

## 3. `CuemsNetworkMapType.refresh`'s docstring still calls a closed item open

**Where**: `src/cuemsutils/config/network_map.py:156-162`.

> **Not ported**: the daemon additionally clears every non-controller node's `adopted` flag
> on a first run … recorded as an open item in `migration-guide.md` rather than added
> silently.

That item is **closed**, and closed in the library's favour: the consumer removed the branch
rather than asking for the parameter. `set_controller_always_adopted()` having no first-run
parameter was correct, not an omission awaiting reconciliation. The paragraph should say so,
or go.

---

## Why these are reported rather than fixed

`cuems-nodeconf` is a consumer of this library. Editing the library from a consumer's branch
would put the fix somewhere the library's own tests do not gate it, and — for the docstrings
— would touch the file whose stability the characterization yardstick depends on. Finding 1
in particular deserves a test in `cuems-utils`' own suite: a document saved over an existing
`0644` file comes back `0644`.
