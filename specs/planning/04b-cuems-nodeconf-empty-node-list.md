<!-- VENDORED 2026-09-21 from cuems-utils@ce5b5b0:
     specs/planning/xml-rebuild/010-consumer-prompts/04b-cuems-nodeconf-empty-node-list.md
     Body kept VERBATIM. Their answer to this repository's second upstream report.
     VERIFIED HERE on 2026-09-21 against the fixed library, with no monkeypatch:
       - their tests/contract/test_empty_node_list.py: 9 passed; 5 failed against the
         pre-fix settings.py, so it is genuinely failing-first;
       - fresh-node boot: read the shipped empty map (0 nodes) -> write this node ->
         re-read (1 node), with read_network_map's `except ValueError` unchanged;
       - this repository's gate: 95 + 15 green; __version__ still 0.1.0rc16.
     Outstanding for this repository: their section 3 (add an empty-map fixture). -->

# Feature 010 — `cuems-nodeconf`: your empty-`node_list` report is fixed upstream

**Status:** answer to an upstream report — **no work required in this repository beyond a rebuild**
**Date:** 2026-09-21
**Repository:** `../cuems-nodeconf`
**Raised by:** `cuems-nodeconf` feature `002-public-network-map-path` (report received here as
`cuems-utils/specs/010-consumer-migration/empty-node-list-report.md`)
**Closed by:** `cuems-utils` T085–T090 — see
`cuems-utils/specs/010-consumer-migration/migration-guide.md` §4a-ii and `baseline.md`

---

## 0. The answer, in one paragraph

You were right on every point, including the one that is easy to get wrong. `NetworkMap.get_node`
now raises **`ValueError`**, not `TypeError`, when the map lists no nodes — for all three shapes
(an empty `<node_list/>`, no `node_list` element at all, and a `None` value) — and the message is
unchanged, so your `test_reads_a_map_that_does_not_list_this_node_yet` keeps passing as written.
**Your `except ValueError` needs no change. Your pins do not move. Your merge candidate is not
re-cut.** The only thing this repository has to do is rebuild `cuemsutils` from the fixed commit.

---

## 1. What changed upstream

One line in `src/cuemsutils/xml/settings.py`, plus the comment explaining why it is that line:

```python
nodes_list = network_dict.get('node_list') or []
```

**Your warning about the trap was correct and was followed.** `.get('node_list', [])` does not fix
this: `node_list` is `minOccurs="0"`, and an empty `<node_list/>` decodes to a key that is *present
with value `None`*, so the default never fires. That is why the neighbouring guards at `:187` and
`:236` are safe by their `if not node_list:` check rather than by their defaults.

Pinned by `tests/contract/test_empty_node_list.py` — nine tests, written failing-first as you asked
(5 failed before the fix, 9/9 pass after), on inline XML constants so no sibling checkout is needed.
The full library suite is green at 2660 passed / 100 skipped / 2 xfailed.

Everything in your §7 "What NOT to do" was honoured: no consumer catches `TypeError`, no
placeholder node returns, `network_map.xsd` is untouched, `get_node` still raises rather than
returning `None`, and `tests/contract/test_nodeindex_characterization.py` — the vendored yardstick —
was not edited.

---

## 2. What this repository does about it

### 2.1 Rebuild `cuemsutils`. That is the whole change.

**The one caveat, and it is operational rather than expressible in packaging**: the fix ships
*inside* `0.1.0rc16` with no version bump, because rc16 has never been released (`cuems-utils`'
tags stop at `v0.1.0rc14`, it carries no `debian/` directory, and you build the wheel from a
checkout with `UTILS=<path>`). So `>= 0.1.0rc16` is satisfied by a build made *before* this fix and
by one made *after*, and nothing in the version string can tell them apart.

Therefore: **rebuild or reinstall `cuemsutils` from the fixed commit in every development venv and
in every packaging run.** The discriminator is `cuems-utils`' own
`tests/contract/test_empty_node_list.py` — if it fails, the installed build predates the fix.

This is the same shape as last time: your first report's `save_document` permissions fix landed
inside rc16 too (`6fe2d3f`), without a bump.

### 2.2 What explicitly does **not** change

| | |
|---|---|
| `debian/control` | `cuems-utils (>= 0.1.0rc16), (<< 0.1.1~)` — **unchanged**; FR-091's "both files agree" still holds |
| `pyproject.toml` | the matching floor — **unchanged** |
| `xml-refactor-merge-candidate` | **not re-cut** — the tag moves only when packaged content changes, and none did |
| `read_network_map`'s `except ValueError` | **unchanged** — deliberately narrow, and now correct for this case too |
| Your test fixtures | unchanged; see §3 for the one you may now want to *add* |

### 2.3 Your research.md R3 is unblocked

Option A — seed a fresh node with the same empty map `cuems-common` ships and load it back — is
implementable as of this fix. It was not before: the load raised `TypeError` before any of it could
be exercised.

---

## 3. The gap worth closing on your side too

Three suites missed this, each internally consistent and collectively blind:

| Repository | Why it did not catch it |
|---|---|
| `cuems-common` | T040 validated the empty map against the **XSD** only; it never loaded it through `ConfigManager` |
| `cuems-utils` | no test loaded an empty `node_list` through `ConfigManager` or `get_node` |
| `cuems-nodeconf` | **every fixture map in `tests/fixtures/` contains nodes** |

Schema-validity was checked where the document was authored, and loading was checked only against
documents that happened to be populated — so the one document every node actually installs was the
one nothing loaded. `cuems-utils` has closed its row. **Consider adding an empty-map fixture to
`tests/fixtures/`** — byte-identical to what `cuems-common` ships — and driving `read_network_map`
and the first-write path over it. That is your boot path on every fresh install; right now nothing
in your suite exercises it.

---

## 4. One adjacent finding, reported and deliberately not fixed

Re-measuring every `node_list` consumer after the fix (upstream T087) confirmed all four paths your
report names are safe. It also turned up a fifth thing your report did not cover, recorded rather
than fixed:

A document whose root is **entirely** empty — `<CuemsNetworkMap/>`, with no `node_list` element at
all — decodes to `None`, so `get_dict()` returns a plain `{}` and `refresh`/`save` raise
`AttributeError` on it. `get_node` answers it correctly either way (`ValueError`), so your boot path
is unaffected.

It was left alone on three grounds: it predates this fix, it is a decode-layer behaviour affecting
the whole document rather than anything about `node_list`, and **nothing ships that shape** —
`cuems-common` ships `<node_list/>`, which works fully. Widening the fix would touch the decode path
for all six schemas, which the report does not license. Flagged here so that if you ever *write* a
bare root, you know it round-trips differently.
