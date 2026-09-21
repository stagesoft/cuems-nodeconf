# Data model — 002 public network-map path

No schema changes, no new persisted fields. What changes is **who owns the in-memory document
and for how long**. Three entities, and the rules between them.

## 1. Node index (`self.network_map`)

The MAC-keyed `NodeIndex` of known nodes — unchanged by this feature, and still the **single
in-memory source of truth** (feature 001's guarantee, restated in FR-003).

| | |
|---|---|
| Type | `cuemsutils.tools.NodeList.NodeIndex` (a `dict` subclass) |
| Key | the node's MAC |
| Written by | `read_network_map` (from a document), discovery refresh, `adopt_node`/`unadopt_node` |
| Invariant | an adoption recorded here is never overwritten by a stale document; every save refills the document **from** the index, never the reverse |

## 2. Kept document (`self._document`) — **new lifetime, not a new thing**

The live `CuemsNetworkMapType` that `ConfigManager.load_network_map()` already returns. Today
it is discarded at the end of `read_network_map`; this feature keeps it.

| | |
|---|---|
| Obtained from | `ConfigManager.network_map`, after `load_network_map()` — the only public producer |
| Named by | nothing in shipped code. The daemon never imports or spells the class (FR-001) |
| Lifetime | from the first successful `read_network_map()` to process exit |
| `node_list` | overwritten **in full** from the index before every save and every refresh |

### States

```text
      __init__                 read_network_map() succeeds
  ┌──────────────┐   seed?   ┌──────────────────────────────┐
  │ _document =  │──────────▶│ _document = the loaded one   │──┐
  │    None      │           │ (kept for the process life)  │  │ refill from index
  └──────────────┘           └──────────────────────────────┘◀─┘ before save/refresh
         │
         │ save or refresh attempted in this state
         ▼
   RuntimeError, named clearly — never AttributeError (D1)
```

**Why the `None` state is reachable at all**: `set_comms()` starts the IPC listener *before*
`run()` reads the map (R2). In that window the index is empty, so adopt/unadopt answer "not
found" and never reach a save. The error exists for the case that ordering ever changes.

**Ordering rule (constitution VI)**: `read_network_map` assigns `_document` **before**
`network_map`. Installing a populated index while `_document` is still `None` would let an RPC
arriving in between adopt a node and then fail to save it.

## 3. Empty map seed — a file, not an object

Written only when `map_path` does not exist, so that a document can be loaded by the same path
used for an existing map (option A, FR-004).

| | |
|---|---|
| Content | byte-identical to what `cuems-common` ships (200 bytes) — see [contracts/empty-map-seed.md](contracts/empty-map-seed.md) |
| Nodes | **none.** `<node_list/>` is empty, so the seed introduces no identity (constitution III is not engaged) |
| Mode | `0644`, set explicitly — a plain create is `0600` under umask `0077` (R4) |
| Written | atomically: temp file in the same directory, then `os.replace` (constitution II) |
| On failure | log and exit, as the other start-up failures do. Running on with a map that can never be saved is the worse answer |
| Reachable when | a development checkout, or a host where the file was deleted by hand. On a packaged host `cuems-common` ships it as a conffile |

### What the seed is *not* allowed to be

A bare `<CuemsNetworkMap/>` root, with no `node_list` element at all. That shape decodes to
`{}` and makes `refresh`/`save` raise `AttributeError` upstream — reported by `cuems-utils`
(their §4, an adjacent finding they deliberately left unfixed, because nothing ships that
shape). The seed carries `<node_list/>`, which works fully.

## Relationships

```text
  disk                        memory
  ────                        ──────
  network_map.xml  ──load──▶  kept document  ──build──▶  node index
       ▲                           ▲                         │
       └────── save ───────────────┴──── refill node_list ────┘
                                          (index wins, always)
```

The cycle is deliberately one-directional on refill: the document is a serialisation buffer,
the index is the truth. `refresh` is the one operation that writes *into* the document (merge,
controller-always-adopted, write-if-changed — all library logic, D22), after which the index is
rebuilt from it, exactly as feature 001 left it.
