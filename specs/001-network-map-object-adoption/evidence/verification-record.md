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
| Permissions surface (T052) | inspection plus a measured save | **finding — fixed upstream, see below** |
| Scope boundaries (T053) | `git diff ccdcbd6..HEAD` | no module added, no node-model test added, 34 → 32 methods |

## NOT verified — no hardware was involved

Both of these need a deployed package, a live controller and the operator UI. Neither was
available to the session that implemented the feature, and **neither was performed**.

| | What remains | Why it cannot be skipped |
|---|---|---|
| **SC-003** (T050) | `quickstart.md` §3: drive all six rows of the adopt/unadopt outcome table from the frontend settings view on the controller, including the persistence check that the map on disk changes *immediately* | The RPC shape is a contract with a live Angular component. The suite mocks the dispatch; it cannot show the operator's button working. `NodeIndex.adopt` mutates without persisting, so a dropped save looks correct in the UI and loses state on restart |
| **SC-006** (T051) | `quickstart.md` §4: with both halves deployed, confirm a controller and a node discover each other; then, deliberately, confirm a half-renamed pair does **not** silently mis-role | Avahi behaviour here is characterized against mock `ServiceInfo` objects. Nothing in the suite exercises real mDNS, D-Bus or multi-node discovery |

> **Both of these now live on one ledger**, together with feature 002's two outstanding checks:
> `specs/002-public-network-map-path/checklists/hardware-verification.md` (entries 1 and 2 are T050 and
> T051). Tick them there and here, or in neither place.

The packaging half of §4 (SC-007) **was** performed — see the table above. It is the
relationship gate, not the discovery gate, and does not stand in for SC-006.

## ✅ CLOSED finding — the map's mode, fixed upstream 2026-09-17

> **Solved — do not treat as open.** Reported (T049), received and **fixed in `cuems-utils` `6fe2d3f`** at the
> single choke point `write_tree`, so it covers every `save_document` consumer. Its test
> (`tests/contract/test_save_permissions.py`) was written failing-first and parametrises the existing mode over
> `0644/0664/0600/0640`. **Re-measured here against `9e5e79f`: `0644` in, `0644` out**, and the suite stays green.
> What follows is the original finding, kept as the record of what was measured.

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

- **T042**, the merge gate — **still due**. Settled: cuems-common's candidate is the pushed tag
  `xml-refactor-merge-candidate` → `f2fc0f5` (same packaging as `1a00159`, which T047 built), the same tag
  name marks every repository's candidate, and the target is `rc_1` (here `74dca72`, a fast-forward).
  **This side is now cut**: feature 002 merged into `feat/xml-refactor` (fast-forward, 2026-09-21) and the
  signed tag `xml-refactor-merge-candidate` → `6c0cca7` marks it. Due: the human agreement on the merge
  window, and pushing — branch and tag are local only.
- ~~**T049**, the upstream report~~ — **done.** Filed, received in `b6b5eb5` and closed by `6fe2d3f`
  (the mode fix, with its own failing-first test) and `9e5e79f` (both docstrings). All three findings are
  fixed in the library; none was patched from this side.
