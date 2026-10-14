# `cuems-nodeconf` — planning folder

**Re-indexed 2026-10-13, feature table added 2026-10-14.** This folder was assembled on 2026-09-07 as the self-contained bundle for
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

## Feature split — status (2026-10-14)

The table to start SDD work from. Spec-kit's next number is **004**: `node_set` went in from its
brief, not through spec-kit, so it took no number. Numbers below are **proposed**; a feature gets
its number when `/speckit.specify` creates its folder, and if the order changes, the numbers follow
the order, not this table.

### Done

| Work | Where |
|---|---|
| 001 network-map object adoption · 002 public network-map path · 003 start-up readiness | `specs/001-*` … `specs/003-*` |
| `node_set` (operator alias over IPC) | `12-node-set-alias.md`, `3d3601d`; consumer side closed by `cuems-editor` `2c100a4` (UR-8, gate G4) |
| Foreign controllers on a shared LAN (`rc_1` `80ccc83`) | `../upstream-reports/foreign-controller-scoping.md`, landed in `cuems-utils` `38d2ede`; wired here `155fe6c` |
| Static link-local cluster address (`rc_1` `141cf1f`) | `16b207d` |
| Release lines absorbed (`rc_1`, `debian/bookworm`), changelog headed `0.1.1-1 UNRELEASED` | `78e7290`, `952b9dd` |

### Not SDD, but owed

| Work | Status | Gate |
|---|---|---|
| **Coordinated version bump** (`cuems-utils` `coordinated-release-version-bump.md` §11 step 6): `0.1.1-1` `unstable`; `cuemsutils >=0.1.1,<0.1.2`; `cuems-common` `Depends: >= 1.3.1~`, `Breaks: << 1.3.1~`; the version references in `tests/packaging/release-gate-demo.sh`, the 001/003 specs and the ledger | **Waiting** | Lands as one set with every sibling; `cuems-utils` `0.1.1` on PyPI first; tag re-cut is the maintainer's |
| **Hardware ledger** (`../002-public-network-map-path/checklists/hardware-verification.md` §1–§7) and **enabling the daemon on every node** (§5) | **Not performed** | Hardware access. §5 gates features 007/008 below |

### SDD features, proposed order

| # | Feature | Status | Hard dependencies | Start from |
|---|---|---|---|---|
| **004** | **`nodeconf-atomization`** — extract rows 2, 3, 7, 8, 9 and 11 into their own classes; row 4 gets its collaborators passed in; interface names become configuration. **No behaviour change**: the suite and the yardstick pass unedited | **Ready** once **D23 is lifted** (maintainer, in `02-settled-decisions.md`) | none else | `13-atomization-remeasured.md` §1–§4, `01`, `11` (boot order) |
| **005** | **`node-identity-apply`** — `<role_id>` on adoption; the OS identity chain (hostnamectl, `/etc/hosts`, `avahi-daemon.conf`); `cuems-nodeconf apply-identity [--check]` | **Ready** (soft: after 004, so it is born as its own class) | `cuems-common` `docs/node-identity-contract.md` stays the contract; a second OS-touching path, so `CLAUDE.md`'s "exactly one path" changes | `13` row 12; the contract's `apply-identity` section |
| **006** | **`controller-election`** — a real election and join protocol (runtime issue 5). Also fixes the stated limitation that a fresh node accepts every controller of its first pass | **Needs design** (`/speckit.specify` + clarify) | 004 (row 4's collaborators); ideally 005 (`role_id`) | `11` runtime issue 5, `08`, `../upstream-reports/foreign-controller-scoping.md` §5 |
| **007** | **`hardware-probe`** — the per-node port inventory into `hardware_outputs.xml` | **Blocked upstream** | `cuems-utils` capability layer (structure pass + public `ConfigManager` accessor; unnumbered there); daemon enabled on every node | `cuems-utils` `hardware-outputs-capability-layer.md`; `13` row 13; prior art `CuemsHwDiscovery.py` on `origin/main` (`c6ccc7b`) |
| **008** | **`display-conf-transcription`** — record `/run/cuems/display.conf`'s geometry | **Blocked** | 007; `cuems-common` agreeing to a second reader of `display.conf` | `13` row 14; capability layer §7.4 (on start vs on change) |

**Which can start today**: 004 as soon as D23 is lifted, and 005 in parallel if you accept it
landing before the split. 006 can start its spec and clarify phases now; its plan should wait for 004.

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
| `12-node-set-alias.md` | implemented directly from the brief, `3d3601d` (2026-10-14); `cuems-editor` closed UR-8 in `2c100a4`. Owed: hardware check (ledger §7a) |

## Related, outside this folder

- `../upstream-reports/` — requests and corrections this repository sent to `cuems-utils`. Both are
  **closed**: `foreign-controller-scoping.md` landed as `cuems-utils` `38d2ede`, and
  `coordinated-release-bump-corrections.md` is folded into the bump document (§1, §1.1, §9, §10.2)
  and the capability-layer document (§1 finding 2).
- `../sibling-gates/` — gate reports for `cuems-utils` features. `014` is closed.
- `../002-public-network-map-path/checklists/hardware-verification.md` — the ledger of every
  verification owed on hardware, for features 001–003.

## Standing lessons

- **Re-measure before relying on any coordinate.** Line numbers in this folder have gone out of date
  four times so far.
- **Measure against the branch that is releasing**, not the default branch or the one named in a
  document. In October 2026 that was `origin/rc_1` for this repository, not `debian/bookworm`.
- **Name a document or a behaviour in comments, never a feature number.** Numbers get reassigned.
