# Verification record — what was verified, and what was not (T054)

**Feature 001, recorded 2026-09-17.** The constitution's testing gate says a change to
discovery, role election, the identity chain, OS network reconfiguration or boot ordering
"MUST additionally state how it was verified on real hardware, or state plainly that it was
not. Both are acceptable answers; silence is not." This is that statement. Quote it in the
PR description.

## Verified, by something that ran

| What | How | Result |
|---|---|---|
| The suite | `./run-tests.sh` (1/2) | **95 passed**, nothing skipped |
| The equivalence gate (SC-001) | `./run-tests.sh` (2/2), `specs/planning/yardstick/` unmodified | **15 passed** |
| Row 5 removed (SC-002) | grep for the nine method definitions | five gone; `refresh_network_map`, `adopt_node`, `unadopt_node`, `read_network_map` remain as thin adapters |
| Retired TXT key gone (SC-004) | grep over `*.py` and `cuems.service.*` | **zero** outside the enumerated exceptions |
| Public import paths (SC-008) | grep for `cuemsutils.xml` / `cuemsutils.timeoutloop`; deprecation warnings | zero imports, zero warnings |
| The package refusal (SC-007) | `tests/packaging/release-gate-demo.sh`, real packages in throwaway chroots | **nine of nine scenarios matched**; `evidence/out-of-order-refusal.txt` |
| Permissions surface (T052) | inspection plus a measured save | **finding — see below** |
| Scope boundaries (T053) | `git diff ccdcbd6..HEAD` | no module added, no node-model test added, 34 → 32 methods |

## NOT verified — no hardware was involved

Both of these need a deployed package, a live controller and the operator UI. Neither was
available to the session that implemented the feature, and **neither was performed**.

| | What remains | Why it cannot be skipped |
|---|---|---|
| **SC-003** (T050) | `quickstart.md` §3: drive all six rows of the adopt/unadopt outcome table from the frontend settings view on the controller, including the persistence check that the map on disk changes *immediately* | The RPC shape is a contract with a live Angular component. The suite mocks the dispatch; it cannot show the operator's button working. `NodeIndex.adopt` mutates without persisting, so a dropped save looks correct in the UI and loses state on restart |
| **SC-006** (T051) | `quickstart.md` §4: with both halves deployed, confirm a controller and a node discover each other; then, deliberately, confirm a half-renamed pair does **not** silently mis-role | Avahi behaviour here is characterized against mock `ServiceInfo` objects. Nothing in the suite exercises real mDNS, D-Bus or multi-node discovery |

The packaging half of §4 (SC-007) **was** performed — see the table above. It is the
relationship gate, not the discovery gate, and does not stand in for SC-006.

## Open finding — the map's mode, reported not patched

Measured: `/etc/cuems/network_map.xml` at `0644` comes back **`0600`** after a save.
The cause is upstream (`cuems-utils` `documents.py:189-195`: `mkstemp` is `0600` and
`os.replace` carries the temporary file's mode onto the target). The identical outcome from
the pre-feature call path shows this is **not** a regression introduced by feature 001.

It matters because `cuems-nodeconf` runs as **root** while both engines run as
**`User=cuems`**, and `cuems-common` ships the file `0644` so the engine can read it. Written
up with a suggested fix in `specs/001-network-map-object-adoption/upstream-report.md`,
finding 1. Not worked around in this repository: the guarantee belongs to the writer, and
every other consumer of `save_document` is exposed the same way.

## Also outstanding

- **T042**, the merge gate: cuems-common's counterpart is ready at `1a00159`, and its own
  gate T019 waits on this repository. What remains is the human agreement on a shared merge
  window. Neither half merges alone.
- ~~**T049**, the upstream report~~ — **done.** Filed, received in `b6b5eb5` and closed by `6fe2d3f`
  (the mode fix, with its own failing-first test) and `9e5e79f` (both docstrings). All three findings are
  fixed in the library; none was patched from this side.
