# `cuems-nodeconf` — planning folder

**Re-indexed 2026-10-13.** This folder was assembled on 2026-09-07 as the self-contained bundle for
feature `001-network-map-object-adoption`, from `cuems-utils@b7598d5` (branch
`010-consumer-migration`), and grew briefs for features 002 and 003. All three features have
landed, so most of it is now record, not instruction. Every file carries a dated status banner
under its header. **Files are kept in place, not moved to an archive**, because sibling repositories
link to some of them by path (`09`, `10`), and in-repo specs link to most of the rest.

## What is live

| File | Status | Read it when |
|---|---|---|
| `13-atomization-remeasured.md` | **Current basis** | Planning any structural change to `CuemsNodeConf`, the identity chain, the hardware probe/transcription, or the election protocol. It also records this repository's acceptance of the hardware obligation |
| `01-atomization-basis.md` | Still the basis, out of date | With `13`. It is the vendored ten-row inventory `13` re-measures |
| `02-settled-decisions.md` | Partly in force | Before proposing anything that touches the map, the node model or the public imports. D23 needs the maintainer to lift it before an atomization feature |
| `08-firstrun-signals.md` | Reference | Before adding any first-boot behaviour |
| `11-startup-analysis.md` | Historical, one item open | The only written boot-order narrative. Runtime issue 5 (election) is open |
| `yardstick/test_nodeindex_characterization.py` | **Live gate** | Always: `./run-tests.sh` runs it. Read-only; change it in `cuems-utils` and re-vendor |

## Waiting

| Slot | For | Blocked on |
|---|---|---|
| `12-node-set-alias.md` | The `node_set` IPC brief (operator alias edits), cited by `cuems-utils` as if it already existed | `cuems-utils` feature 015's `NodeIndex.set_alias` (its gate G4). Not written until that lands. See `../upstream-reports/coordinated-release-bump-corrections.md` §5 |

## Superseded — kept as record

| File | Implemented by |
|---|---|
| `00-runnable-flow.md` | feature 001 |
| `03-consumer-audit-findings.md` | features 001/002 (C4, C6, C9, C10) |
| `04-item-c-inventory.md` | feature 001 (T052); T050's `cleanup()` no longer exists |
| `04a-cuems-nodeconf-public-path.md` | feature 002 |
| `04b-cuems-nodeconf-empty-node-list.md` | upstream fix + this repository's empty-map fixture |
| `05-network-map-api.md` | feature 001. `cuems-utils`' `NodeList.py` is the authority |
| `06-node-model-handover.md` | confirmed in feature 001 |
| `07-public-surface.md` | features 001/002 |
| `09-self-node-seeding.md` | feature 003 |
| `10-readiness-window.md` | feature 003 |

## Related, outside this folder

- `../upstream-reports/` — requests and corrections this repository sends to `cuems-utils`:
  `foreign-controller-scoping.md` (the library half of `rc_1`'s `80ccc83`) and
  `coordinated-release-bump-corrections.md`.
- `../sibling-gates/` — gate reports for `cuems-utils` features. `014` is closed.
- `../002-public-network-map-path/checklists/hardware-verification.md` — the ledger of every
  verification owed on hardware, for features 001–003.

## Standing lessons

- **Re-measure before relying on any coordinate.** Line numbers in this folder have gone out of date
  four times so far.
- **Measure against the branch that is releasing**, not the default branch or the one named in a
  document. In October 2026 that was `origin/rc_1` for this repository, not `debian/bookworm`.
- **Name a document or a behaviour in comments, never a feature number.** Numbers get reassigned.
