<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# cuems-nodeconf's gate report for cuems-utils feature 014

**For**: `cuems-utils` specs/014-xs-boolean-and-media-elements/, task T033 (record every sibling
arm, including any left red and why) and T030 (this repository's own gate).
**From**: `cuems-nodeconf`, branch `feat/xml-refactor`, commits `4d7c91d` and `61c5705`.
**Library measured against**: `../cuems-utils` @ `014-xs-boolean-and-media-elements` `b8b44e7`.
**Date**: 2026-10-05.

This file is written to be copied or linked into `cuems-utils`' own record (T033); nothing in
`../cuems-utils` was edited to produce it, per that feature's guardrail.

---

## 1. Summary

Feature 014 retypes `cms:BoolType` to `xs:boolean` (XML text `true`/`false`, JSON wire real
booleans) across five elements in `script.xsd` and `network_map.xsd`. `cuems-nodeconf` holds
objects — never the lexical string — so **no source change was needed**. The gate's scope was one
fixture, one disk-bytes test assertion, and two docs. All closed; see §2.

While closing that gate, running this repository's full suite surfaced 32 failures with a
*different*, pre-existing cause — feature 013's device-class reshape was never applied to this
repository's `settings.xml` fixtures. That is **not** a 014 defect; arm A (library at the 014
branch point) and arm C (library on 014, fixtures converted) show the identical 32-failure set, so
014 neither caused nor fixed it. It is reported here anyway (§3) because closing it surfaced a
second thing that *is* upstream's to know about: `cuems-reshape-devices` cannot carry a settings
document across both the 013 reshape and the later F3 retirement of `audio_cards`/`universes` in
one pass. No tool failed in a way that produced a wrong answer — it correctly refused and named
the reason — but the two migrations were evidently never exercised together before.

## 2. Feature 014's own gate (T030)

| Arm | Result |
|---|---|
| A — branch point (`cuems-utils@84705b9`) | 32 failed / 142 passed |
| B — library moved, fixtures untouched | 33 failed / 141 passed |
| C — library moved, fixture converted | 32 failed / 142 passed (failing-test set identical to arm A) |
| Yardstick (`specs/planning/yardstick/`) | 15 passed, unaffected, all arms |

**Documents converted**: `tests/fixtures/etc_cuems/network_map.xml`, via `cuems-convert-documents`
(now `doc_version="2"`; `.bak` deleted after). `tests/fixtures/etc_cuems/settings.xml` and
`settings_sentinel.xml` needed nothing *for this feature* — `settings.xsd` declares no boolean
element, verified by inspection (no `True`/`False` text in either file).

**Source changed**: none.

**Write-path check**: confirmed on bytes, not the object, per the gate's own instruction (nodeconf
is the one sibling that writes `network_map.xml` continuously). Extended
`tests/test_network_map.py::TestAnAdoptionIsNotLostToTheNextRefresh::test_an_adoption_between_passes_is_on_disk_after_the_next_pass`
reads the file nodeconf just wrote and regex-matches the element text directly.

**Test whose premise was retired**: that same test's regex was pinned to the old spelling
(`<adopted>\s*True\s*</adopted>`); narrowed to `<adopted>\s*true\s*</adopted>` — same guarantee
(the adoption reaches disk), new wire form.

**Docs corrected** (named by the migration guide as teaching the retired spelling):
`CLAUDE.md:25` and `specs/001-network-map-object-adoption/quickstart.md:76,80` — both showed
`<adopted>True</adopted>`/`<online>False</online>`-style examples, now lowercase.

**The one-way door** (migration guide §4.3, `DocumentTooNewError` after `save()` bumps
`doc_version`): checked this repository's own docs for an upgrade/rollback procedure that would
need correcting for the "upgrade the package before nodeconf restarts, no rollback after" rule.
None exists here (checked `README.md`, `CLAUDE.md`, `debian/changelog`, `specs/002-*/research.md`,
`specs/planning/10-readiness-window.md`) — nothing to correct.

**Commits**: `4d7c91d` — the gate itself (fixture conversion, test narrowing, doc corrections).

## 3. Independent finding: feature 013's device reshape, never applied here, and a tooling gap it exposed

### 3.1 What was wrong

`tests/fixtures/etc_cuems/settings.xml` and `settings_sentinel.xml` were still in the **pre-013**
device shape (`<videoplayer>`/`<audioplayer>`/`<dmxplayer>` as flat children of `<node>`, instead
of wrapped in `<players><player class="...">`). `cuems-utils`' own
`sibling-repository-updates.md` for feature 013 already named this precisely: *"`cuems-power-bridge`
and `cuems-nodeconf` were **not** run here — their suites are outside this task's scope... this
table is a prediction for them."* The prediction was correct and nobody closed it afterwards. Every
one of the 32 failures in §2's arms A/B/C traced to the same root cause: `ConfigManager` loads
`settings.xml` before anything else, and `raise_if_old_device_shape` refuses it outright before any
schema decode, so the failure surfaces at a dozen different call sites (`read_network_map`,
`_load_identity`, `_refuse_unprovisioned`, …) but is one defect.

### 3.2 The tooling gap this uncovered

Running `cuems-reshape-devices` directly on the two fixtures does **not** fix them:

```
settings.xml: skipped (would not validate: ... Unexpected child with tag 'audio_cards' at
position 3 ... Schema component: AudioPlayerType ...)
```

The chain, as read from `src/cuemsutils/xml/versioning.py` and `mapper.py`:

1. A later change (F3) retired `audio_cards` (from `AudioPlayerType`) and `universes` (from
   `DmxPlayerType`) entirely from `settings.xsd`, with a registered `settings` 1→2 converter
   (`_settings_1_to_2`) that drops them on read — but it looks for them at
   `Settings/node/audioplayer/audio_cards` and `Settings/node/dmxplayer/universes`: the **old**,
   flat device-shape path.
2. `raise_if_old_device_shape` runs *before* any version-based conversion and refuses a flat-shape
   document unconditionally, directing the user to `cuems-reshape-devices` first.
3. `cuems-reshape-devices` reshapes the structure (wraps players, adds `class`) but does not know
   about `audio_cards`/`universes` — that is a different feature's concern — and then validates its
   own output against the **current** schema, where neither field is legal on any player type. It
   refuses, correctly, but with no path forward.
4. Even if a document reached `_settings_1_to_2` after reshaping, the converter's old
   `node/audioplayer/audio_cards` lookup no longer matches `node/players/player[@class='audio']`,
   so it would not fire there either.

**Net effect**: no combination of the shipped tools carries a document that is simultaneously
pre-013-shaped *and* still carrying the two retired derived counts to a validating result. This is
likely rare in the field (013's own measurement found it only in test fixtures across siblings,
not in any live document), but it is a real gap between two migrations that were each tested in
isolation and never exercised together. Whether it is worth a combined conversion path, or just a
note in the 013/F3 migration guides warning that `cuems-reshape-devices` assumes the retired-field
drop already happened, is a call for that repository, not this one.

### 3.3 Remediation applied here

Hand-rewrote both fixtures: players wrapped in `<players><player class="video"|"audio"|"dmx">`,
`audio_cards`/`universes` dropped, `doc_version="2"` set, the dmx latency comment carried into its
`<player>` block unchanged. Validated directly against the live `settings.xsd` via
`XMLSchema11.validate` and against the full suite: all 32 previously-red tests now pass, **174/174
total**, yardstick **15/15**.

**Commit**: `61c5705`.

This closes the fixture debt but does not touch the tooling gap in §3.2 — that is `cuems-utils`'
decision to make, hence this report.

## 4. Operational note: concurrent sibling sessions sharing one `../cuems-utils` checkout

During this gate, `../cuems-utils` was briefly found in a detached `HEAD` at a much older commit
(`07a7f9f`, predating `0.1.0rc14`) rather than on `014-xs-boolean-and-media-elements` where this
session had left it. Traced to another sibling repository's session running its own gate against
the same shared working tree concurrently — not a defect in this repository's process or in
`cuems-utils`. It was caught before any result was trusted (re-verified library resolution, schema
validity and the full suite against the restored branch before committing), and `../cuems-utils`
was returned to `014-xs-boolean-and-media-elements`, clean, with its own history untouched.

Worth naming as a process note rather than a finding: running multiple sibling gates concurrently
against one shared `../cuems-utils` checkout lets one session's branch switch invalidate another's
in-flight measurement. A separate worktree or clone per concurrent gate session would remove the
race; a single shared checkout works fine for sequential gates, which is how this feature's gates
were apparently intended to run.

## 5. What `cuems-utils`' T033 can record verbatim

```
REPOSITORY: cuems-nodeconf      GATE: T030        HEAD: 61c5705
LIBRARY:    ../cuems-utils @ 014-xs-boolean-and-media-elements b8b44e7

ARM A (branch point, cuems-utils@84705b9):   32 failed / 142 passed
ARM B (library moved, fixtures untouched):   33 failed / 141 passed
ARM C (library moved, fixture converted):    32 failed / 142 passed (identical failing-test set to arm A)
YARDSTICK:                                   15 passed, all arms

DOCUMENTS CONVERTED:   tests/fixtures/etc_cuems/network_map.xml (cuems-convert-documents, doc_version="2")
DOCUMENTS NEEDING NOTHING (014): settings.xml, settings_sentinel.xml — schema declares no boolean
SOURCE CHANGED:        none
TESTS WHOSE PREMISE WAS RETIRED: test_network_map.py::...::test_an_adoption_between_passes_is_on_disk_after_the_next_pass
                                  — regex narrowed from True to true, same guarantee
DOCS CORRECTED: CLAUDE.md:25; specs/001-network-map-object-adoption/quickstart.md:76,80

STILL RED AT 014's GATE: none, after closing the independent 013 fixture debt below.
FINDINGS FOR cuems-utils:
  1. (013/F3 interaction) cuems-reshape-devices cannot migrate a settings document that is both
     pre-013-shaped and still carrying audio_cards/universes; see report §3.2. Resolved locally by
     hand-rewrite (61c5705), not upstream.
  2. (process note) concurrent sibling-gate sessions sharing one ../cuems-utils checkout can race
     on branch state; see report §4. No action taken against cuems-utils itself.

COMMITS:  4d7c91d — docs/test(014): adopt the xs:boolean wire form from cuems-utils feature 014
          61c5705 — test(fixtures): reshape settings.xml to the current device/player schema
```
