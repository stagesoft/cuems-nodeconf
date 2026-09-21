# `cuems-nodeconf` — planning bundle for the network-map object adoption

**Assembled** 2026-09-07 from `cuems-utils@b7598d5` (branch `010-consumer-migration`).
**Purpose**: make this repository's spec-driven work **self-contained**. Everything the flow needs
is here; the sibling `cuems-utils` checkout is no longer required reading.

## Start here

Read **`00-runnable-flow.md`** and run it. It is a complete spec-kit flow — branch and bootstrap,
a constitution step (this repository has none), the `/speckit.specify` → `implement` chain, and
exit criteria. It names the feature **`001-network-map-object-adoption`**.

The other files are what its CONTEXT block asks for, brought in-repo.

| File | What it is | Why you need it |
|---|---|---|
| `00-runnable-flow.md` | The flow itself | The SDD |
| `01-atomization-basis.md` | `CuemsNodeConf`'s **ten responsibilities**, which are single-class candidates, and why | D23 says leave this basis intact. It exists so you do not re-derive the inventory |
| `02-settled-decisions.md` | The 7 decisions that bind this repo, plus FR-030a-i/ii | Do not reopen these |
| `03-consumer-audit-findings.md` | C4, C6, C9, C10 — measured 2026-09-03 | The four findings that are this repository's |
| `04-item-c-inventory.md` | Feature 008's ITEM C: **T050** and **T052**'s call-site table | Your row-5 inventory and the RPC-shape contract |
| `05-network-map-api.md` | The shape of `NodeIndex`/`CuemsNetworkMapType` | What you are migrating **onto** |
| `06-node-model-handover.md` | Feature 007's moved-symbol table and public import path | Confirm 007 landed here; do **not** redo it |
| `07-public-surface.md` | The public replacements, the version floor, `Timeoutloop` | Wave 0 landed — these exist now |
| `08-firstrun-signals.md` | **Repo-original, not vendored.** The three signals this repository calls "first run", what feature 001 deleted and why, and the options if genuine first-boot behaviour is ever needed | Written 2026-09-07 during 001's preparation. The deleted branch also closes 008's "left for 009 to reconcile" note in file 05 |
| `09-self-node-seeding.md` | **Repo-original, not vendored.** Whether nodeconf should write its own entry at start-up: the two eager `get_node` lookups, what a seed needs, its preconditions, and the provisioning requirements | Research only, 2026-09-17. Read it before answering "why not just create the node?" — and before touching the shipped placeholder controller |
| `04b-cuems-nodeconf-empty-node-list.md` | **Vendored 2026-09-21** from `cuems-utils@ce5b5b0`. Their answer to this repository's second upstream report: `get_node` now raises `ValueError` on an empty map, inside `0.1.0rc16` | Read with `specs/002-public-network-map-path/research.md` R3. **Verified here against the fixed library**; the only action on this side is rebuilding `cuemsutils`, plus their §3 — add an empty-map fixture, since nothing here exercises the boot path a fresh install takes |
| `yardstick/test_nodeindex_characterization.py` | **The yardstick** | D22: the swap is done when these pass, not when the code looks equivalent |

## The one thing to understand before starting

**D22 makes this a measured migration, not a rewrite.** Feature 008 characterized row 5's behaviour
*before* moving it, precisely so equivalence could be demonstrated rather than argued. The
vendored test file is that characterization. Run it against the new API; if it passes unchanged,
the swap is correct. If you find yourself editing it to accommodate the new API, stop — that is
the moment the guarantee is lost.

**And row 5's dispatch chain ends at a live UI.** `nodelist_modify` originates in
`cuems-frontend`'s `settings.component.ts` (`confirmAddNode`/`confirmRemoveNode`), which
operators use today on the controller where this daemon runs. The RPC response shape
`{'OK': bool, 'error'?: str}` is a contract with an Angular component, not an implementation
detail. This cannot be scoped as "delete and rewrite".

## Corrections applied on vendoring

Three, all recorded rather than silently fixed:

1. **Stale feature number.** `01-atomization-basis.md` said "009's job"; the 2026-08-25
   renumbering makes that **010**.
2. **The `cuemsutils` floor was wrong.** `00-runnable-flow.md` records
   `pyproject.toml >=0.1.0rc15` and `debian/control >= 0.1.0rc5`. Feature 010's wave 0 has since
   added `SchemaName` and `get_schema_descriptor`, and `cuems-utils` is now **`0.1.0rc16`**.
   The pin must move to `>=0.1.0rc16` in **both** files — and per FR-091 the gate wants an upper
   bound or a `Breaks:` too, since a floor cannot express "must refuse a library that has moved
   past me". See `07-public-surface.md`.
3. **Stale source comments are a task, not a nuisance.** `AvahiTool.py:12` and
   `CuemsAvahiListener.py:19-24` defer the TXT-record change "to feature 008" — a closed,
   `cuems-utils`-only feature. Correcting them is part of the work (C9).

4. **A machine-specific path, left deliberately.** `04a-cuems-nodeconf-public-path.md`'s `Repository:`
   header names the author's own checkout by absolute path, which does not exist here. Kept
   verbatim so the vendored body stays byte-comparable with upstream; this repository's own artefacts
   (`tests/packaging/release-gate-demo.sh`, the evidence files) use relative paths only, because evidence
   has to reproduce on any development machine.
5. **File 09's §6 went stale in ten days** — it described a placeholder controller `cuems-common` has
   since deleted (`f78c876`). Corrected in-file with a dated note rather than rewritten, since §8's
   recommendation was reached with the placeholder in view.

## Freshness — the coordinates were already stale on arrival

The audit that produced this bundle measured `CuemsNodeConf.py` on **2026-09-03** at `7abc01f`.
By the time it was vendored (2026-09-07) two commits had landed and **every row-5 line number had
moved +18**; the file grew 756 → 774 lines. `00-runnable-flow.md` now carries the re-measured
numbers with the originals in brackets, so the shift is visible rather than silent.

One of those two commits matters beyond line numbers. **`21c2875` "fix(ipc): answer every engine
request, not just nodelist_modify"** changed `engine_callback` — the row-10 dispatch that row 5's
adopt/unadopt chain runs through. It used to reply only for `nodelist_modify`, leaving the engine
**blocked** on any other well-formed message.

Verified on vendoring: the RPC response shape this feature treats as a contract —
`{'OK': bool, 'error'?: str}` — is **unchanged** by that fix. But the dispatch is now broader, so
the row-5 swap must not regress the other branches while migrating this one.

**The lesson generalises**: re-measure before relying on any coordinate here. This project has now
found stale line numbers three times — `TOTAL_COMPLEX_TYPES` said 56 against a true 58, feature
010's exempt-set numbers had all moved, and these.

## Provenance, and the one file that can drift

Every file carries a `VENDORED`/`EXTRACTED` header naming its source and commit. The documents
are snapshots of settled decisions and will not move.

**`yardstick/test_nodeindex_characterization.py` is different** — it is live code, and the
original still runs in `cuems-utils`' suite. A fix applied to one copy does **not** reach the
other, which is the duplication (F15) this whole rebuild exists to end. Two consequences:

- treat the vendored copy as **read-only**: run it, do not edit it;
- if it needs to change, change it in `cuems-utils` and re-vendor from there.

## What was deliberately left behind

`xml-rebuild-01/03/04/05/06` (XML-engine internals), `xsd-type-resolution.md` (withdrawn library
machinery) and `envelope-feature.md` (a future `script.xsd` feature) have no bearing on this work.
`xml-rebuild-07` (1 733 lines) and `xml-rebuild-09` (497) were **extracted from** rather than
copied: only the parts that bind this repository are reproduced, in files 02 and 03.
