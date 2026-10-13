<!-- VENDORED from cuems-utils@b7598d5
     specs/planning/xml-rebuild/010-consumer-prompts/04-cuems-nodeconf.md
     Three corrections applied on vendoring — see ../README.md "Corrections applied".
     Do not edit to diverge: fix the original and re-vendor. -->

> **Status (2026-10-13): SUPERSEDED — executed as feature `001-network-map-object-adoption`.** See `README.md` for the index.

# Feature 010 — `cuems-nodeconf`: adopt the network-map object, rename the discovery wire

**Status:** ready to run — **pairs with [03-cuems-common](03-cuems-common.md)**
**Date:** 2026-09-03
**Repository:** `/disk/Projects/StageLab/cuems-nodeconf`
**Run order:** 04 of 06. See the [index](README.md).

---

## 0. State of this repository, measured 2026-09-03

| | |
|---|---|
| Current branch | **`feat/xml-refactor`** @ `e1f027b`, clean — the target branch already exists. *(Was `7abc01f` when audited 2026-09-03; two commits have landed since — see the re-measurement note below.)* |
| Base | itself; feature 007's node-model phase is already landed here |
| Spec-kit | **absent** — added on first run (§1) |
| Constitution | **absent** — written on first run (§2) |
| Existing features | none → this becomes **`001-network-map-object-adoption`** |
| Tests | `poetry run pytest` — 16 test files under `tests/` |
| `cuemsutils` pin | `pyproject.toml` `>=0.1.0rc15`; `debian/control` `>= 0.1.0rc5` — **both wrong now, see the README's correction 2** |
| Daemon status | re-enabled on the formitgo controller since 2026-06; **still disabled elsewhere** in the fleet |

**Feature 007 already landed here** — the node model and serializers were deleted
and this repository now imports `cuemsutils.tools.NodeList` at nine sites. Confirm
that; do not redo it (007 FR-030a-i). What is new is row 5: the network-map
*domain logic* that 008 moved into `cuems-utils` and that this daemon still
implements ad hoc.

**The daemon is disabled across most of the fleet.** That is context, not an
excuse to be careless: the adopt/unadopt chain it owns terminates in a
`cuems-frontend` component operators use today on the one controller where it
runs.

---

## 1. Branch and bootstrap

```bash
cd /disk/Projects/StageLab/cuems-nodeconf
git checkout feat/xml-refactor        # already exists, already current

specify init --here --integration claude --script sh --force
```

Commit the scaffold as its own commit before `/speckit.constitution`.

Spec-kit's sequential branch numbering will want its own branch. Stay on
`feat/xml-refactor`; let it name `specs/001-network-map-object-adoption/` only.

---

## 2. Constitution — write one, this repository has none

```
/speckit.constitution

Establish the constitution for cuems-nodeconf, grounded in what this repository actually is.
Read CLAUDE.md first; it is accurate, current, and unusually specific about failure modes.

WHAT THIS REPOSITORY IS: the node-side discovery and adoption daemon. It uses Avahi
(_cuems_nodeconf._tcp.local) to publish each node's UUID/MAC/role/IP and to maintain
/etc/cuems/network_map.xml automatically. Python 3.11+, systemd service
cuems-nodeconf.service, PartOf=cuems-node.target, RUNS AS ROOT. When reactivated it also
owns node identity: assigning <role_id> on adoption and applying the OS-side identity chain
(hostnamectl, /etc/hosts, avahi-daemon.conf). It does NOT touch network plumbing —
/etc/network/interfaces, dhcpd/dhclient and hostapd are explicitly out of its remit.

PRINCIPLES THE CODE AND ITS HISTORY ALREADY IMPLY — derive from these, and note that
CLAUDE.md records five load-bearing bugs fixed during the Phase-1 re-enable, every one of
which is a principle waiting to be written down:
- It RUNS AS ROOT ALONGSIDE NON-ROOT SERVICES. The single worst bug in this repository's
  history was creating /tmp/nodeconf.ipc root-owned, which crash-looped the cuems-user
  engine whenever nodeconf won the boot race. Anything this daemon creates that another
  service touches is a permissions decision, and permissions decisions are correctness.
- It is a DISTRIBUTED-STATE daemon whose output is a FILE OTHER SERVICES READ.
  network_map.xml is the cluster's topology; a write that is wrong, duplicated, or
  half-finished is a cluster that misbehaves, not a process that fails.
- IDENTITY IS KEYED BY UUID, never by a name-derived value. The duplicate-node bug came
  from merging by a mac derived from the avahi service name. State this as a rule.
- ITS RPC RESPONSES ARE A CONTRACT WITH A LIVE ANGULAR UI. nodelist_modify -> engine_callback
  -> adopt/unadopt terminates in cuems-frontend's settings.component.ts, which operators use
  today. The {'OK': bool, 'error'?: str} response shape is a contract, not an internal
  detail free to change silently.
- IT IS ONE CLASS DOING TEN THINGS, deliberately and temporarily. CuemsNodeConf.py is 756
  lines covering daemon lifecycle, interface discovery, Avahi orchestration, role election,
  network-map logic, OS network reconfiguration, service-template files, alias publishing,
  the master lock file and engine IPC dispatch. A future feature splits it; the basis is
  already written (see the atomization document referenced in the migration context). State
  the direction of travel so new code does not add an eleventh responsibility to the pile.
- SHUTDOWN AND BOOT ORDERING ARE PRODUCT BEHAVIOUR, not lifecycle plumbing — two of the five
  recorded bugs were shutdown/boot-race bugs.

Testing: 16 test files exist. State a gate this repository can meet, and be explicit that
Avahi/zeroconf behaviour is largely characterized rather than unit-tested — which is the
honest description of what the existing tests do.

Do NOT weaken any rule to accommodate the migration that follows.
```

---

## 3. Context block — paste verbatim into `/speckit.specify` and `/speckit.plan`

```
CONTEXT — read these before writing anything. They live in the SIBLING checkout
/disk/Projects/StageLab/cuems-utils, not in this repository:
  .../cuems-utils/specs/008-rebuild-extension/migration-guide.md      ITEM C = THIS REPO'S INVENTORY,
                                                                      incl. T050 and T052's call-site table
  .../cuems-utils/specs/008-rebuild-extension/data-model.md §5        the ported API's shape
  .../cuems-utils/tests/contract/test_nodeindex_characterization.py   THE YARDSTICK — read it
  .../cuems-utils/specs/planning/nodeconf-atomization.md              the ten-responsibility basis
  .../cuems-utils/specs/planning/xml-rebuild/xml-rebuild-09-consumer-audit.md   C4, C6, C9, C10 are this repo's
  .../cuems-utils/specs/planning/xml-rebuild/xml-rebuild-07-speckit-prompts.md  §2 = the FULL decision list

SETTLED — the decisions that bind THIS repository. Do not reopen. Anything
outside this subset: read §2 of the prompts file above.
  D11 the node model moved in from here in feature 007. It lives in cuemsutils ONLY.
      Feature 007 is DONE in this repository -- confirm it, do not redo it.
  D22 network-map config-object logic (merge/adopt/unadopt/refresh/signature/write
      orchestration) lives in cuems-utils on NodeIndex/CuemsNetworkMapType, mirroring
      ConfigManager/ConfigBase -- not reimplemented ad hoc on this daemon. Equivalence with
      today's behaviour was MEASURED IN 008 by characterization tests ported from this
      class; those tests are the yardstick. The swap is done when they still pass against
      the new API, NOT when the code looks equivalent.
  D23 the full atomization of this class (the other nine responsibilities) is NOT this
      feature's work. 008 recorded the target-design basis; feature 010 consumes row 5 only.
      Leave that basis intact for whoever picks it up; do not execute it, and do not
      invalidate it.
  D33 the Avahi TXT-record vocabulary (node_type=master|slave|firstrun) is renamed in BOTH
      this repository AND cuems-common, inside feature 010, as ONE coordinated cutover. It
      cannot be half-renamed: a listener reading node_role against a publisher writing
      node_type discovers nothing.
  D34 the descriptor and the config objects reach this repository through PUBLIC paths
      (feature 010 flow 00). cuemsutils.xml declares __all__ == [].
  D27 nothing in the ecosystem releases until every 010 flow lands
  Q14 -> (i) cuemsutils.xml is internal machinery

MEASURED STARTING STATE — verified against live files 2026-09-03, not transcribed.
CuemsNodeConf.py is 756 lines, one class:
  ROW 5 — the nine methods this feature replaces with calls into cuems-utils.
  RE-MEASURED 2026-09-07 against feat/xml-refactor @ e1f027b. Every line moved +18 from the
  2026-09-03 audit, and the file grew 756 -> 774 lines, because two commits landed in between.
  The 2026-09-03 numbers are shown in brackets so the shift is visible rather than silent:
    :247 refresh_network_map [229]      :299 _map_signature [281]
    :431 write_network_map [413]        :458 merge_discovered_nodes [440]
    :508 set_master_always_adopted [490] :519 check_missing_adopted_nodes [501]
    :534 adopt_node [516]               :555 unadopt_node [537]
    :580 read_network_map [562]
  engine_callback — routes nodelist_modify ADD/REMOVE to adopt_node/unadopt_node.
  CHANGED since the audit by 21c2875 "fix(ipc): answer every engine request, not just
  nodelist_modify": it used to reply only for that one action, leaving the engine BLOCKED on
  any other well-formed message. Verified 2026-09-07 that the RPC response shape this feature
  treats as a contract -- {'OK': bool, 'error'?: str} -- is UNCHANGED by that fix. The dispatch
  is now broader, so the row-5 swap must not regress the other branches while migrating this one.
      and returns {'OK': bool, 'error'?: str}. The ported methods return a BARE BOOL, so the
      error strings ("Node {uuid} not found", "node is offline", "Cannot unadopt master
      node") must be RECONSTRUCTED here from the False return and which check failed. 008's
      migration guide T052 says exactly what has to be reconstructed.
  :579-581  cleanup() reads self.cm.show_lock_file. self.cm IS NEVER ASSIGNED anywhere in
      the class, so every call raises AttributeError before the try block's own
      `except FileNotFoundError` can help. 008 prescribed the fix; land it here, since both
      it and the NodeIndex adoption touch __init__.
  :22-23  from cuemsutils.xml.mapper import Mapper, read_config_document
          from cuemsutils.xml.settings import NetworkMap as _NetworkMapReader
      ^ INTERNAL IMPORTS. cuemsutils.xml declares __all__ == []. Flow 00 publishes the
        replacements; move onto them (D34/C4).
  :26  from cuemsutils.timeoutloop import Timeoutloop   (used :309, :617, :629)
      ^ RELOCATED after 008 closed. The class is now cuemsutils.tools.TimeoutLoop.TimeoutLoop
        and the old path is a warning shim (C10).
  THE AVAHI HALF (C6) — this repository owns MORE of it than cuems-common does, 30
  occurrences against 27:
    cuems.service.firstrun:12,19   cuems.service.master:12,19   cuems.service.slave:12,19
    CuemsSettings.py:27   the PUBLISHER: {'node_type': 'slave'}
    CuemsAvahiListener.py:96-155  the CONSUMER: two blocks (add_service, update_service)
        keyed on b'node_type', translated through _AVAHI_NODE_TYPE_TO_ROLE
    CuemsNodeConf._install_master_service_template + the inline slave-template copy in
        set_node_role  — the INSTALLER
    AvahiTool.py:12 and CuemsAvahiListener.py:19-24 both defer this "to feature 008" — a
        closed, cuems-utils-only feature (C9). Correct those comments.
  tests/test_avahi_listener.py:37-43,95-104,124   tests/test_node_type.py:21
  test_run_nodeconfig.py:58,61,69  — NON-SHIPPED dev script; see the counting question

007's DECLARED BREAK, closed: feature 004's FR-026d recorded that this repository's
namespace-injected node handlers silently stop being consulted. 007 closed it in cuems-utils
by building the write path; this feature closes it here by removing the ad hoc
implementation entirely.
```

---

## 4. Specify

```
/speckit.specify <PASTE CONTEXT BLOCK>

Swap this daemon's ad hoc network-map logic for cuems-utils' network-map object, and rename
this repository's half of the Avahi discovery vocabulary.

WHAT MUST BE TRUE WHEN DONE:
- Row 5's nine methods are GONE, replaced by calls into NodeIndex / CuemsNetworkMapType.
  merge_discovered_nodes (:440), set_master_always_adopted (:490) and
  check_missing_adopted_nodes (:501) collapse into CuemsNetworkMapType.refresh(discovered,
  path), called from refresh_network_map (:229-246) in place of its current four-step body.
  adopt_node (:516) and unadopt_node (:537) become NodeIndex.adopt/.unadopt. _map_signature
  (:281) becomes NodeIndex.signature. read/write_network_map (:562/:413) go through the
  config object's own load and save.
- 008's CHARACTERIZATION TESTS ARE THE YARDSTICK, and this is the acceptance criterion that
  matters most: the swap is done when
  cuems-utils/tests/contract/test_nodeindex_characterization.py still passes against the new
  API — not when the code looks equivalent. Those tests were written IN 008 by pinning THIS
  class's behaviour precisely so that equivalence would be measured here rather than
  asserted. Run them; do not reason about them.
- engine_callback's RPC contract is preserved exactly. The ported methods return a bare
  bool; the {'OK': bool, 'error'?: str} shape is this repository's concern, so the three
  error strings must be reconstructed from the False return and which check failed. That
  response shape is a contract with cuems-frontend's settings.component.ts, a UI operators
  use today — the chain nodelist_modify -> engine_callback -> adopt/unadopt must keep
  working end to end, and "the port compiles" is not evidence that it does.
- check_missing_adopted_nodes' WARNING LOG survives, or is deliberately dropped. Its logging
  is not part of refresh's orchestration, so it disappears unless this repository calls
  missing_adopted(discovered) itself. Decide; do not lose it by accident.
- cleanup()'s dead self.cm reference is fixed or the method is deleted. Every call currently
  raises AttributeError before its own exception handling runs. 008 prescribed assigning a
  ConfigManager in __init__, which is also where the NodeIndex adoption lands — do both in
  one change.
- The two internal cuemsutils.xml imports (:22-23) move onto the public paths flow 00
  publishes. cuemsutils.xml declares __all__ == []; this repository is currently the only
  one violating that, and the violation predates any decision to allow it.
- The Timeoutloop import moves. :26 imports from cuemsutils.timeoutloop, which is now a
  warning shim; the class is cuemsutils.tools.TimeoutLoop.TimeoutLoop, used at :309, :617
  and :629.
- This repository's half of the Avahi cutover lands (D33): its three service templates
  (cuems.service.{firstrun,master,slave}, lines 12 and 19 of each), the publisher at
  CuemsSettings.py:27, the consumer at CuemsAvahiListener.py:96-155 with
  _AVAHI_NODE_TYPE_TO_ROLE retiring alongside it, and the installer
  (_install_master_service_template plus the inline slave-template copy in set_node_role).
  Coordinate with flow 03, which owns cuems-common's four files and the filenames. THE TWO
  HALVES MERGE TOGETHER — a publisher and a listener disagreeing about the key is a cluster
  that cannot discover itself.
- AvahiTool.py:12 and CuemsAvahiListener.py:19-24's "deferred to feature 008" comments are
  corrected — that feature closed and was cuems-utils-only.

WHAT THIS FEATURE DOES NOT DO: the atomization of the other nine responsibilities (D23).
The basis is already written; leave it intact. Specifically, do not let row 5's removal
tempt a broader restructuring of CuemsNodeConf, and do not add an eleventh responsibility
to the class while the ninth is being removed.

DECIDE EXPLICITLY: whether the non-shipped test_run_nodeconfig.py (:58, :61, :69) counts
toward "zero node_type occurrences ecosystem-wide". 007 counted src/ only.

DO NOT re-implement or re-test the node model here (007 FR-030a-i). A node-model test
appearing in this repository is a regression, not coverage.
```

---

## 5. Clarify

```
/speckit.clarify
```

Force one question: **what exactly does `engine_callback` return in each of the
three failure cases**, now that the error strings are gone from the callee. The
Angular component on the far end reads those.

---

## 6. Plan

```
/speckit.plan <PASTE CONTEXT BLOCK>

Per-file scope:
- cuemsnodeconf/CuemsNodeConf.py — row 5's nine methods (:229, :281, :413, :440, :490,
  :501, :516, :537, :562); engine_callback (:113-144); cleanup (:579-581); imports
  (:22-23, :26); the Avahi installer.
- cuemsnodeconf/CuemsSettings.py:27 — the TXT publisher.
- cuemsnodeconf/CuemsAvahiListener.py:19-24, :96-155 — the TXT consumer and its comments.
- cuemsnodeconf/AvahiTool.py:12 — the stale comment.
- cuems.service.{firstrun,master,slave} — this repository's three templates.
- tests/test_avahi_listener.py, tests/test_node_type.py — fixtures.
- pyproject.toml / debian/control — bounded cuemsutils dependency (C7).

Sequencing: pairs with flow 03; their merges are simultaneous (D33). The row-5 swap itself
is independent and can land first.

Constitution check, against the constitution written in §2:
- The RPC-contract principle is what makes engine_callback's error-string reconstruction a
  requirement rather than a detail.
- The distributed-state principle governs the write path: refresh() now decides whether a
  write happens at all, via signature comparison.
- The one-class-ten-things principle is the reason D23's boundary is respected: this feature
  removes a responsibility and must not add one.
- Testing: 008's characterization tests are the equivalence gate, and they live in the
  sibling repository. Say how this repository's CI reaches them, or record the manual
  procedure honestly.
```

---

## 7. Tasks, checklist, analyze, implement

```
/speckit.tasks
```
```
/speckit.checklist Adoption readiness: 008's characterization tests RUN and PASS against
the new API — not reasoned about; all nine row-5 methods gone, counted; engine_callback's
{'OK': bool, 'error'?: str} shape preserved with all three error strings reconstructed, and
the nodelist_modify -> adopt/unadopt chain exercised end to end against the real UI path;
check_missing_adopted_nodes' warning log kept or deliberately dropped; cleanup()'s self.cm
fixed or deleted; both internal cuemsutils.xml imports moved to public paths; the Timeoutloop
import relocated; this repository's Avahi half renamed and verified against flow 03's half so
no half-renamed state ships; the stale "feature 008" comments corrected; the
test_run_nodeconfig.py counting question answered; and D23's atomization basis left intact —
no tenth responsibility restructured, no eleventh added.
```
```
/speckit.analyze
```
```
/speckit.implement
```

Then [Part 4 §9](../xml-rebuild-07-speckit-prompts.md)'s quality loop.

---

## 8. Exit criteria

`poetry run pytest` green; 008's characterization tests pass against the new API;
row 5's nine methods gone; `engine_callback`'s response shape and all three error
strings preserved, with the adopt/unadopt chain verified end to end; `cleanup()`
fixed; both internal `cuemsutils.xml` imports and the `Timeoutloop` import on
public/current paths; this repository's Avahi half renamed and merged
simultaneously with flow 03; the stale feature-number comments corrected; and
D23's atomization basis still valid for whoever picks it up.

**Does not ship alone** (D27).
