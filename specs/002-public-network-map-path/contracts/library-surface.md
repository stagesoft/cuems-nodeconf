# Contract — what this daemon may import, and how it obtains a document

The interface this feature changes is the boundary between `cuems-nodeconf` and `cuemsutils`.
This is that contract, as it must read after the change.

## 1. Allowed imports in shipped code (`cuemsnodeconf/`)

| Import | Status |
|---|---|
| `cuemsutils.tools.NodeList` — `NodeIndex`, `NodeRole`, `node` | ✅ public |
| `cuemsutils.tools.ConfigManager` — `ConfigManager` | ✅ public |
| `cuemsutils.tools.TimeoutLoop`, `cuemsutils.tools.CommunicatorServices` | ✅ public |
| `cuemsutils.log`, `cuemsutils.errors` | ✅ public |
| **`cuemsutils.config.*`** | ❌ **forbidden** — `cuemsutils.config.__all__ == []`; this is the import the feature removes |
| `cuemsutils.xml.*` | ❌ forbidden — internal machinery (constitution, "public import paths only") |

**Verification**: `grep -rn "from cuemsutils.config" cuemsnodeconf/` returns nothing (SC-001).

### Two enumerated exemptions, neither in shipped code

1. **Tests** keep `from cuemsutils.config.network_map import CuemsNetworkMapType`, at all 28
   `patch.object(..., 'save')` sites plus the new setup lines (FR-007). A test patching a
   collaborator to keep saves off the real filesystem is not the daemon consuming an API;
   D34 governs what the daemon reaches for at runtime.
2. **The vendored yardstick** (`specs/planning/yardstick/`) imports the internal path and is
   **permanently out of scope** — it is `cuems-utils`' file, byte-identical to their copy, and
   editing it destroys the equivalence guarantee feature 001 rests on.

## 2. Obtaining a document — the only permitted route

```text
ConfigManager(config_dir=<dir of map_path>, load_all=False)
    .load_network_map()          # raises ValueError if the map does not list this node
    .network_map                 # -> a live CuemsNetworkMapType: .save and .refresh included
```

`load_network_map` assigns `netmap.get_dict()`, which **reads as a dict and is not one**: for
`network_map` it returns the bound document. `save_network_map` already depends on this, so the
behaviour is load-bearing rather than incidental (`cuems-utils` T083 documents it at the
assignment).

**Forbidden alternatives**, all rejected explicitly by 04a §6:

- asking `cuems-utils` for a public alias — declined by decision (their T084);
- `type(manager.network_map)` to reach the class — works, and reads as a mistake;
- reimplementing `refresh`'s orchestration locally — that is exactly what D22 moved out.

## 3. The exception contract this daemon depends on

`ConfigManager.load_network_map()` raises **`ValueError`** when the map does not list this
node — *including* when the map lists no nodes at all.

That second clause was **not** true until `cuems-utils` `e363d03`: an empty `node_list` raised
`TypeError` and crash-looped this daemon on every fresh install. Reported from this repository
and fixed upstream inside `0.1.0rc16`; pinned there by `tests/contract/test_empty_node_list.py`.

Consequences for this repository:

- `read_network_map` keeps catching **`ValueError` only** — deliberately narrow, so that
  `SchemaError` and `ValidationError` still fail loudly. It needs **no** change.
- The daemon requires a `cuemsutils` build at `e363d03` or later. **The version string cannot
  express this** (the fix shipped inside `rc16`, which was never released), so the discipline is
  operational: rebuild `cuemsutils` from the fixed checkout in every venv and packaging run.
  The discriminator is `cuems-utils`' own `tests/contract/test_empty_node_list.py`.
- Pins stay `>= 0.1.0rc16, << 0.1.1~` in both `debian/control` and `pyproject.toml`.

## 4. Unchanged by this feature

The RPC contract with the operator UI — `{'OK': bool, 'error'?: str}`, every well-formed
request answered — is untouched. Only the document that `adopt_node`/`unadopt_node` save
through changes, never the answer they give (constitution IV).
