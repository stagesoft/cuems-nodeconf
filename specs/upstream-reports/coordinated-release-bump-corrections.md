<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Corrections to `coordinated-release-version-bump.md` — the `cuems-nodeconf` rows

**For**: `cuems-utils` `specs/planning/coordinated-release-version-bump.md` (decided 2026-10-12,
measured the same day). Also one finding for `hardware-outputs-capability-layer.md`.
**From**: `cuems-nodeconf`, `feat/xml-refactor`, measured 2026-10-13 after `git fetch origin`.
Nothing in `../cuems-utils` was edited to produce this.

## 1. The release line is `rc_1`, not `debian/bookworm`

| Bump-document section | Says | Measured |
|---|---|---|
| §9 | packaging release line `origin/debian/bookworm` → `0.1.0-1` only; 9 behind | `debian/bookworm` stopped on 2025-12-30. **`origin/rc_1` is releasing**: `0.1.0-7` (2026-07-29), **`0.1.0-8`** (2026-10-06), **`0.1.0-9`** (2026-10-07), all `unstable`, by Ion Reguera. The refactor branch is 6 behind `rc_1` and 9 behind `debian/bookworm` (the two sets are disjoint) |
| §1 | `0.1.0-8` (UNRELEASED), nothing tagged, **no collision** | **Collision.** The refactor branch's `0.1.0-8 UNRELEASED` (the TXT-record rename) and the shipped `0.1.0-8` (foreign-controller filtering) share a number and nothing else. Neither is an ancestor of the other |
| §10.2 | `cuems-nodeconf`: **none** to absorb | **`0.1.0-8` and `0.1.0-9`**. `0.1.0-7` is identical on both lines (checked by diff) |

This is the mistake §9 already warns about for `cuems-common`, made here in the other direction:
the line that was measured is the one that stopped, not the one that is releasing.

## 2. A second `Breaks:` that a reused version has defeated

§1.1 records one: `cuems-utils`' `Breaks: cuems-common (<< 1.3.0-23~)`. There are two more, both on
the TXT-record rename (D33):

| Relation | Lets through, though it should refuse | Fixed by |
|---|---|---|
| `cuems-common` `Breaks: cuems-nodeconf (<< 0.1.0-8)` | released `cuems-nodeconf` **0.1.0-8, -9** (still `node_type`) | §4.3 → `<< 0.1.1~` |
| `cuems-nodeconf` `Breaks: cuems-common (<< 1.3.0-23~)` | released `cuems-common` **1.3.0-23, -24, -25** (still `node_type`; checked on `origin/rc_1`, which still ships `cuems.service.{firstrun,master,slave}`) | §4.2 → `<< 1.3.1~` |

Each one, if let through, gives a half-renamed pair: the listener reads `node_role`, the publisher
writes `node_type`, and the cluster discovers nothing, with no install error. The plan's §4 matrix
already fixes both. Only the measurement was missing.

## 3. What `cuems-nodeconf` did about it (step 4 of §11) — done 2026-10-13

- **Merged `origin/rc_1` (`78e7290`) and `origin/debian/bookworm` (`952b9dd`)** into
  `feat/xml-refactor`, which is now 0 behind both. The `rc_1` changelog entries `0.1.0-8`/`-9` are
  kept word for word (§10.1 rule 1). Each merge commit message records what happened to every
  absorbed commit.
- **`debian/bookworm`'s maintainer scripts were not absorbed.** Its `postinst` enables **and
  starts** `cuems-nodeconf` and copies `network_map.xsd` into `/etc/cuems`. The rc_1 packages
  `0.1.0-2`…`-9` never shipped maintainer scripts, so nothing in the field is lost.
- **A second, older collision**: `debian/bookworm` released a `0.1.0-1` (entry dated 19 Dec 2024,
  committed 2025-12-19; it is the `.deb` cached in `rc1_packages/`). The `0.1.0-1 UNRELEASED` entry
  that rc_1's `-2`…`-9` history starts from is a different build. The changelog keeps rc_1's history,
  because it is exactly what the shipped `-2`…`-9` packages carry. Both `-1` builds sort below
  `0.1.1-1`, so neither affects the bump.
- **Headed the branch's own entry `0.1.1-1 UNRELEASED` during the merge**, folding in the old
  `0.1.0-8 UNRELEASED` body (§10.1 rule 2). This is a maintainer decision (2026-10-13), taken so the
  changelog never runs backwards between the merge and the coordinated step 6.
  `debian/control`, `pyproject.toml` and every relation stay untouched until step 6.
- **Two fixes from `rc_1` needed a different home on this line.** `141cf1f` (static link-local
  cluster address) is ported as `16b207d`. `80ccc83` (foreign controllers) needs this library's merge:
  `../cuems-nodeconf/specs/upstream-reports/foreign-controller-scoping.md` is the request. Until it
  lands, the daemon ships an interim filter (`6afb5eb`), and the release is not complete for this item
  (rule 4).

## 4. For `hardware-outputs-capability-layer.md` §1, finding 2

*"`cuems-hardware-discovery` … has no checkout."* Its code does exist: `cuems-nodeconf`
`origin/main` `c6ccc7b` (2026-06-01, "Incorporation of development version of CuemsHwDiscovery
class from independent repository") added a 299-line `CuemsHwDiscovery.py` at the repository root.
It is a jack/Xinerama prober that writes an outputs XML. It imports the deleted
`.CuemsNode`/`cuemsutils.xml.XmlReaderWriter`, so it does not run on the refactor line, and it is
**not** merged there. It is input for the probe feature (`cuems-nodeconf`
`specs/planning/13-atomization-remeasured.md`, row 13), where this repository records the obligation
as accepted.

## 5. One stale citation that points here

`upcoming-feature-requirements-2026-10-02.md` (the G4 section) and
`etc-cuems-first-install-execution.md` (step 7) cite
`../cuems-nodeconf/specs/planning/12-node-set-alias.md` as existing and as *"stating these semantics
identically"*. **It does not exist** in this repository, its history, or any branch. It will be
written when 015's `NodeIndex.set_alias` lands. Until then, G4's text in this library is the only
statement of those semantics. The number `12` is reserved for it here.
