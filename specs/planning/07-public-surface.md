<!-- EXTRACTED from cuems-utils@b7598d5
     specs/010-consumer-migration/contracts/descriptor-access.md and
     specs/010-consumer-migration/migration-guide.md §§1-2. Wave 0 LANDED 2026-09-07. -->

> **Status (2026-10-13): SUPERSEDED — the pins and the public imports landed (features 001/002).** See `README.md` for the index.

# The public surface this repository migrates onto

Feature 010's **wave 0 has landed** in `cuems-utils`. What this repository imports internally today
has a public replacement now, so the migration is a move onto something that exists — not a
dependency on planned work.

## Requires `cuemsutils >= 0.1.0rc16`

The public surface below was added **after** `0.1.0rc15`, which is what this repository currently
pins. A floor of `rc15` cannot express "I need the descriptor", so the pin must move to
**`0.1.0rc16`** in `pyproject.toml` **and** `debian/control`, which currently disagree with each
other (`>=0.1.0rc15` against `>= 0.1.0rc5`).

Per feature 010's FR-091 the gate also wants an **upper bound or a `Breaks:`**, not only a floor:
a floor cannot express "must refuse a library that has moved past me", which is what the release
gate actually says.

## The three imports to replace

| Internal import (today) | Replacement |
|---|---|
| `cuemsutils.xml.settings.NetworkMap` — `CuemsNodeConf.py:23`, used at `:567` | `ConfigManager.load_network_map()` then `.network_map`. Asserted **equal in result** to the internal reader, not merely working |
| `cuemsutils.xml.mapper.Mapper` — `CuemsNodeConf.py:22` | **Nothing. Delete the import.** Measured across the whole checkout: the import line is its only occurrence |
| `cuemsutils.xml.mapper.read_config_document` — `CuemsNodeConf.py:22` | **Nothing. Delete the import.** Same measurement |

So of the three names in those two lines, **only one has a call site**. Two need no public
equivalent at all, and inventing synonyms for them would have built public surface for nobody.

## The descriptor, if this repository ever needs it

```python
from cuemsutils.tools.ConfigManager import ConfigManager, SchemaName

ConfigManager(load_all=False).get_schema_descriptor(SchemaName.NETWORK_MAP)
```

Takes the **enum**, never a bare string — a string raises `TypeError`. `SchemaName` has six members
whose values are the registry's own strings, so `SchemaName(name)` and `member.value` cross between
the two forms.

`cuemsutils.xml.__all__` remains `[]`. This accessor is the front door; there is no back one.

## `Timeoutloop` moved too (C10)

`CuemsNodeConf.py:26` imports `from cuemsutils.timeoutloop import Timeoutloop`, used at `:309`,
`:617` and `:629`. That path is now a **deprecation shim** that warns on use. The class lives at
`cuemsutils.tools.TimeoutLoop.TimeoutLoop`.

This matters beyond tidiness: feature 010's wave 5 **deletes** the shim, and the deletion is gated
on a measured count of live imports across all six consumer repositories reaching zero. This
import is one of the nine currently counted.
