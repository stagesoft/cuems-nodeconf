# Contract — the empty map seed (option A)

What the daemon writes when `/etc/cuems/network_map.xml` is absent at start-up, so that a
document can be loaded by the same path used for an existing map.

## The bytes

Byte-identical to what `cuems-common` ships (`etc/cuems/network_map.xml` at `f2fc0f5`,
**200 bytes**, trailing newline included):

```xml
<?xml version='1.0' encoding='utf-8'?>
<cms:CuemsNetworkMap xmlns:cms="https://stagelab.coop/cuems/"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <node_list/>
</cms:CuemsNetworkMap>
```

**`<node_list/>` is required, not incidental.** A bare `<CuemsNetworkMap/>` root decodes to
`{}` upstream and makes `refresh`/`save` raise `AttributeError` — an adjacent finding
`cuems-utils` reported back and deliberately left unfixed, because nothing ships that shape.

The same bytes are the new test fixture `tests/fixtures/etc_cuems/network_map_empty.xml`, so the
fixture and the seed cannot drift apart.

## The rules

| | Rule | Why |
|---|---|---|
| **When** | only when `map_path` does not exist | On a packaged host `cuems-common` ships it as a conffile; this branch is a dev checkout or a hand-deleted file |
| **Where** | inside `map_path`'s directory, never a hard-coded `/etc/cuems` | Tests point `map_path` at a temp directory, and must never touch the real one |
| **Atomicity** | temp file in the **same** directory, then `os.replace` | Constitution II: complete or absent. A partial map would be loaded on the next boot and fail validation |
| **Mode** | `chmod 0644` explicitly, after writing | Constitution I. A plain create is `0600` under umask `0077` (measured). The engines read this file as `User=cuems`; the unit sets no `UMask=`, and the seed must not depend on systemd's default |
| **On failure** | log the path and exit non-zero, as other start-up failures do | Continuing with a map that can never be saved hides the fault until the operator's first adoption disappears |
| **After writing** | load it through the ordinary `read_network_map()` path | One load path for both cases. The seed lists no node, so the load raises `ValueError`, which feature 001's catch already handles |

## What loading a seeded map does

Measured end to end against the fixed library, with no daemon code change:

| Step | Result |
|---|---|
| `read_network_map()` on the seed | OK — index of **0 nodes** (the `ValueError` is caught and logged) |
| first write (`_save_network_map`) with one discovered node | OK — 513 bytes on disk |
| `read_network_map()` again | OK — index of **1 node** |

## What the seed must never become

- **Not** a self-seeding entry. Writing *this node* into the map is a separate, researched
  feature (`specs/planning/09-self-node-seeding.md`), deliberately not in scope here.
- **Not** a placeholder controller. `cuems-common` removed theirs in `f78c876`; it misrouted
  chrony and the log collector for every node that resolved the first controller in the file.
- **Not** written when the map already exists — that would discard the cluster's topology.
