# Verification record — feature 002 (T017)

**Recorded 2026-09-21**, baseline `2fd1f9c` (95 + 15 green before any edit). The constitution
requires a change touching discovery, the identity chain, OS reconfiguration or boot ordering to
"state how it was verified on real hardware, or state plainly that it was not. Both are
acceptable answers; silence is not." This is that statement. Quote it in the PR description.

## Verified, by something that ran

| What | How | Result |
|---|---|---|
| The suite | `./run-tests.sh` (1/2) | **114 passed** (95 baseline + 19 added), nothing skipped |
| The equivalence gate (FR-008, SC-003) | `./run-tests.sh` (2/2) | **15 passed** |
| Yardstick untouched (FR-008, SC-003) | `diff` against `../cuems-utils/tests/contract/test_nodeindex_characterization.py` | **identical** — diffed, not assumed |
| No internal import in shipped code (FR-001, SC-001) | `tests/test_public_surface.py`, and `grep -rn "from cuemsutils.config" cuemsnodeconf/` | **zero**; was 1 |
| Library prerequisite (FR-011, SC-007) | `tests/test_library_prerequisite.py`; upstream discriminator `../cuems-utils/tests/contract/test_empty_node_list.py` | passes here; 9 passed there |
| Fresh-node boot (FR-004, FR-005, SC-005) | `tests/test_fresh_node_boot.py` | seeds the shipped bytes, mode **0644** under umask `0077`, reads 0 nodes, writes, re-reads 1 node |
| `run()`'s own seeding branch | same file, `TestRunSeedsExactlyOnce` | seeds when absent; **does not overwrite** an existing map |
| Adoption survives a refresh (FR-003, SC-004) | `tests/test_network_map.py::TestAnAdoptionIsNotLostToTheNextRefresh` | on disk after the next pass |
| Nothing pre-existing changed (SC-002) | `git diff -U0 2fd1f9c -- tests/` | **additions only, no removed line**; all **28** `patch.object(..., 'save')` sites present, same distribution |
| Library unpatched from this side (FR-009) | `git -C ../cuems-utils status` | clean; no `type(...)` route; `refresh` still delegated to the library |
| Both decisions recorded (FR-010, SC-006) | spec.md and contracts/ | option A and the kept test imports, each with its reason |

## NOT verified — no hardware was involved

**Deferred by decision**, not overlooked. Constitution IV wants the adopt/unadopt chain verified
against the real dispatch path; this feature changes the document those RPCs save through, and
that check needs a controller and the operator UI. A genuine fresh install was likewise not
attempted.

The authoritative list, with steps and what would prove each, is
**[checklists/hardware-verification.md](../checklists/hardware-verification.md)** (FR-012, SC-008),
which also carries feature 001's outstanding T050 and T051. All four entries are unchecked.

What *was* done instead, and its limit: the empty-map boot was exercised in a temporary
directory on a development checkout against `cuemsutils` `ce5b5b0`. That is evidence for the
code path, not for a node.

## Noted in passing, not acted on

The constitution's testing gate still reads "16 test files, currently 81 tests" against a suite
of 114. Pre-existing drift, deliberately not edited here: governance text changes by its own
explicit update, not as a side effect of a feature.
