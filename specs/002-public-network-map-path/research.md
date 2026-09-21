# Research — 002 public network-map path

**Phase 0, 2026-09-18 (updated 2026-09-21). Status: ✅ UNBLOCKED — R3 fixed upstream and verified here** — a defect that the merge candidate carries
regardless of this feature, and that makes option A's seed unloadable. Phase 1 has not
been started. Everything below was measured, not inferred. Measured against cuems-nodeconf
`d548e7c`/`3e526e1`, cuems-utils `9e5e79f`, and cuems-common `f2fc0f5`
(= `xml-refactor-merge-candidate`).

---

## R1 — 04a's design leaves 28 tests without a document

**Measured:** 04a's change applied as written (delete the import, refill a kept
`self._document`, keep it in `read_network_map`) → **28 failed, 67 passed**, every failure
`AttributeError: 'CuemsNodeConf' object has no attribute '_document'`.

**Why:** 28 tests build `CuemsNodeConf()`, assign `network_map` directly and call
`adopt_node`/`unadopt_node`/`refresh_network_map`/`_save_network_map` without start-up ever
running (7 files: adoption_flow 4, engine_callback 2, integration 6, missing_nodes 2,
network_map 6, node_adoption 4, phase1_changes 4). 04a's "verified end to end" covered the
library path, not this daemon's tests.

**Also measured:** give each instance an **empty** document and all **95 pass**. The fix is
setup-only (subject and assertion untouched, per SC-002): the tests supply a document through
the import §4 keeps. There is no alternative in the library's public `tools` surface —
`ConfigManager.load_network_map()` is its only producer of a document, and
`cuemsutils.config.__all__ == []`.

**Decision (proposed):** the daemon starts with no document (`None`), and says so clearly if a
save or refresh is attempted before one is loaded. The 28 tests get a one-line setup that hands
the instance an empty document through the kept import.

## R2 — the IPC listener is live before the map is read, and that is safe

`start()` calls `set_comms()` before `run()`, so adopt/unadopt RPCs can arrive before
`read_network_map`. Until then the index is `__init__`'s empty one, so those RPCs answer
"not found" and never reach a save — today's behaviour, unchanged. **Constraint:**
`read_network_map` must keep the document **before** it installs the populated index.
Otherwise an RPC in between could adopt a node and save through a missing document.

## R3 — ⛔ an empty `<node_list/>` cannot be loaded (blocks option A, and the merge candidate)

**Measured through nodeconf's real `read_network_map`**, with the fixture `settings.xml`:

| `/etc/cuems/network_map.xml` | result |
|---|---|
| cuems-common `e149089` (placeholder node) | OK, 1 node |
| cuems-common **`f2fc0f5`** — the merge-candidate tag (empty `<node_list/>`) | **`TypeError: 'NoneType' object is not iterable`** |

**Cause — in `cuems-utils`:** `src/cuemsutils/xml/settings.py:158-160`, `NetworkMap.get_node`:
`nodes_list = network_dict.get('node_list')` is `None` for an empty `<node_list/>`, then
`for node_item in nodes_list`. `ConfigManager.node_network_map`'s own docstring promises a
`ValueError` when no node carries this uuid. The empty map breaks that contract with a
`TypeError`, which nodeconf's catch (`except ValueError`, feature 001) does not handle.

**Consequence for the merge candidate, independent of 002:** on any host whose map is the
shipped one — every fresh install, and any upgrade where the operator takes the maintainer's
version at the conffile prompt — `run()` reads the map (the file exists), `read_network_map`
raises, and start-up fails. The unit has `Restart=on-failure` / `RestartSec=10`, so it retries
every 10 s and fails the same way, forever. Only nodeconf writes this node into the map, so
nothing breaks the loop. The engine's `load_config()` goes through the same `load_network_map()`
call, so it is exposed identically. (That call was measured; the engine process itself was not
run.)

**How it was missed — three suites, each for its own reason:** cuems-common's T040 validated the
empty map against the XSD only; no cuems-utils test loads an empty `node_list` through
`ConfigManager`; every nodeconf fixture map contains nodes.

**Consequence for 002:** option A's seed *is* this map, so as specified it cannot be loaded.

> **✅ RESOLVED, 2026-09-21 — verified against the fixed library, no monkeypatch.** `cuems-utils` `e363d03`
> makes `get_node` raise `ValueError` for all three empty shapes, message unchanged, inside `0.1.0rc16`
> (`ce5b5b0` adds the records; their T085-T090 are `[X]`). Verified here: their
> `tests/contract/test_empty_node_list.py` is 9/9 green and **5 failed against the pre-fix file**, so it is
> genuinely failing-first; the fresh-node sequence now completes with the real library — read the shipped
> empty map (0 nodes) → write this node → re-read (1 node); this repository's gate is 95 + 15 green. **No
> nodeconf code changed**: `except ValueError` was already right. Pins unmoved, candidate not re-cut. Their
> answer is vendored at `specs/planning/04b-cuems-nodeconf-empty-node-list.md`.
>
> Option 1 chosen. Report and checklist (T085-T090) filed at
> `../cuems-utils/specs/010-consumer-migration/empty-node-list-{report,tasks}.md`, pushed as `230df12`.
> **The fix ships inside `0.1.0rc16`** (rc16 was never released — tags stop at `v0.1.0rc14`), so **no pin
> moves here and the merge candidate is not re-cut**; this repository only rebuilds `cuemsutils` from the
> fixed commit. Verified from this side by monkeypatch: read empty shipped map (0 nodes) → write this node →
> re-read (1 node), with `read_network_map`'s `except ValueError` unchanged. 002 stays blocked until T086
> lands; the design does not change.

**Options — as assessed before the decision:**

| | Fix | Assessment |
|---|---|---|
| **1** | `cuems-utils`: `get_node` treats a missing/empty `node_list` as "not found" → `ValueError`, with a test loading an empty map through `ConfigManager` | **Recommended.** Restores the documented contract at its source (D22, "report, do not patch"). nodeconf's existing catch then covers both fresh-node cases, and option A works unchanged. **Chosen.** It lands inside `0.1.0rc16`, so no floor moves and no re-cut follows (see the note above) |
| 2 | nodeconf also catches `TypeError` | A consumer-side patch over a library defect, and a broad catch that would also swallow real bugs. Leaves the engine exposed |
| 3 | cuems-common ships a node again | Reintroduces the placeholder that f78c876 removed for good reason |

## R6 — two things their answer adds for Phase 1

**Their §3 — the gap on this side.** Every fixture map in `tests/fixtures/` contains nodes, so **nothing in
this suite exercises the boot path a fresh install takes**. That is why this repository missed the defect too.
Phase 1 should add an empty-map fixture, byte-identical to what `cuems-common` ships, and drive
`read_network_map` and the first write over it. It also gives option A's seed a direct test.

**Their §4 — an adjacent finding they left alone deliberately.** A document whose root is *entirely* empty
(`<CuemsNetworkMap/>`, no `node_list` element) decodes to `{}`, so `refresh`/`save` raise `AttributeError`.
`get_node` answers it correctly either way, so the boot path is unaffected, and **nothing ships that shape**.
It constrains option A rather than blocking it: the seed must write the shipped `<node_list/>` shape, never a
bare root. FR-004 already says "the same shape `cuems-common` ships"; R4's `chmod` and this are the two
things the seeding code must get right.

## R4 — the seeded file's mode needs an explicit `chmod`

Plain create: umask `0022` → `0644`, umask `0077` → **`0600`**. An explicit `chmod 0644` gives
`0644` either way. The unit sets no `UMask=`, so systemd's default (`0022`) would happen to
work, but FR-005 must not depend on that: write the seed, then `chmod 0644`, which is the
mode cuems-common installs.

## R5 — the existing missing-map tests

`test_error_handling.py::test_run_exits_on_no_ip` exits before the map is read.
`test_integration.py::test_first_run_becomes_controller_scenario` uses a missing map in `tmp_path`,
so option A's seeding path must write only inside `map_path`'s directory, never the real
`/etc/cuems`.
