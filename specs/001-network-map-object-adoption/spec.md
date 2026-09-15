# Feature Specification: Network-map object adoption and the Avahi vocabulary cutover

**Feature Branch**: `feat/xml-refactor` *(this repository does not branch per feature; the spec directory name and the branch name are independent)*

**Created**: 2026-09-07

**Status**: Draft

**Input**: `specs/planning/00-runnable-flow.md` §4, plus the decisions settled 2026-09-07 during its preparation (recorded under "Decisions already taken" below).

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The operator adopts and unadopts nodes, and it keeps working (Priority: P1)

An operator opens the settings view in `cuems-frontend`, sees the nodes the controller
has discovered, and adds or removes one from the cluster. Today that works. After this
feature the daemon computes the same answer using the shared network-map object instead
of its own copy of the logic, and the operator cannot tell the difference — including
when the answer is "no".

**Why this priority**: this is the only part of the feature a human interacts with, it
terminates in a UI in use today on the one controller where this daemon runs, and it is
the part that fails loudest if the migration is wrong. It is also self-contained: it can
ship without the vocabulary change.

**Independent Test**: run the vendored characterization tests against the new API, then
drive `nodelist_modify` ADD and REMOVE through the real dispatch path on the controller
and confirm both the success and the three failure responses reach the UI unchanged.

**Acceptance Scenarios**:

1. **Given** a discovered, online, unadopted node, **When** the operator adds it,
   **Then** the response is `{'OK': True}`, the node is marked adopted, and the change
   survives the next discovery pass.
2. **Given** a node that is known but currently offline, **When** the operator adds it,
   **Then** the response is `{'OK': False, 'error': 'Cannot adopt node {uuid}: node is offline'}`.
3. **Given** a uuid absent from the map, **When** the operator adds or removes it,
   **Then** the response is `{'OK': False, 'error': 'Node {uuid} not found'}`.
4. **Given** the controller's own node, **When** the operator removes it, **Then** the
   response is `{'OK': False, 'error': 'Cannot unadopt master node'}` and the controller
   stays adopted.
5. **Given** an already-adopted node, **When** the operator adds it again, **Then** the
   response is `{'OK': True}` and nothing changes.
6. **Given** a well-formed request carrying any action other than `nodelist_modify`,
   **When** the engine sends it, **Then** a response is still returned rather than the
   engine blocking until its own timeout.

---

### User Story 2 - The cluster still discovers itself after the vocabulary changes (Priority: P2)

Nodes find each other over mDNS by reading a TXT record off each other's Avahi service.
That record's key is being renamed from the retired master/slave vocabulary to the
controller/node vocabulary the rest of the system already uses. A node running the new
publisher and a node running the new listener must find each other exactly as before.

**Why this priority**: discovery failure is how a cluster loses its topology, and it
fails silently — nothing errors, nodes simply never appear. It ranks below P1 only
because it is a same-behaviour rename with no user-visible surface of its own.

**Independent Test**: with both this repository's half and `cuems-common`'s half applied,
confirm a controller and a node discover each other, resolve roles, and appear in
`network_map.xml`. With only one half applied, confirm they do **not** — the failure mode
must be understood before it is prevented.

**Acceptance Scenarios**:

1. **Given** a publisher and a listener both on the new vocabulary, **When** discovery
   runs, **Then** every node resolves its peers' roles correctly.
2. **Given** a listener on the new vocabulary and a publisher still on the old one,
   **When** discovery runs, **Then** no node is silently mis-roled — the mismatch is
   logged as an unrecognised value rather than absorbed.
3. **Given** a node being promoted to controller, **When** the role template is
   installed, **Then** the installer resolves the renamed template file and the
   published record carries the renamed key.

---

### User Story 3 - Upgrading a node cannot produce a broken combination (Priority: P3)

A maintainer upgrades a node. The packages that must move together do, and any
combination that would leave one component writing a vocabulary another cannot read is
refused by the package manager rather than discovered at runtime.

**Why this priority**: it protects the other two stories rather than delivering value
itself, and its blast radius is an upgrade window rather than a running show.

**Independent Test**: attempt an out-of-order install of the built packages and observe
the refusal.

**Acceptance Scenarios**:

1. **Given** a `cuems-common` carrying the new vocabulary, **When** an older
   `cuems-nodeconf` is installed alongside it, **Then** the package manager refuses.
2. **Given** a library older than the one this daemon's public-path usage requires,
   **When** installation is attempted, **Then** it is refused rather than failing at
   import or at first use.

---

### Edge Cases

- **A discovery pass changes nothing.** The map must not be rewritten. The write decision
  moves inside the shared object's refresh, and "no change, no write" must survive that move.
- **No map file exists at boot.** The daemon starts from an empty index and populates it
  from discovery. Adoption state is whatever discovery and the operator produce — see
  "Decisions already taken", item 4.
- **An adopted node is absent from a discovery pass.** It stays in the map, marked not
  online, and the warning naming it is still emitted. It is not removed and its identity
  record is not lost.
- **The controller's Avahi service is named `controller`, not a MAC.** Merging must key on
  uuid; a name-derived key produces a duplicate node and flips the real one offline.
- **Only one half of the vocabulary cutover reaches a node.** Must be impossible to install;
  see User Story 3. Must also be impossible to *merge* — the package constraint protects a
  node installing both packages, not a repository that releases from one renamed half.

---

## Requirements *(mandatory)*

### Functional Requirements — the network-map object (User Story 1)

- **FR-001**: The daemon MUST NOT carry its own implementation of network-map merge,
  adopt, unadopt, controller-always-adopted, missing-adopted, signature, refresh
  orchestration, or map read/write. All nine of the methods implementing them today MUST
  be gone, replaced by calls into the shared network-map object.
- **FR-002**: The refresh pass MUST delegate to the shared object's `refresh(discovered, path)`,
  which merges, applies controller-always-adopted, compares the signature and writes only
  on change — in place of the daemon's current four-step body.
- **FR-003**: Adoption and unadoption MUST go through the shared object's `adopt` / `unadopt`.
- **FR-004**: The map signature MUST come from the shared object, not a local computation.
- **FR-005**: Reading and writing `network_map.xml` MUST go through the shared config
  object's own load and save paths.
- **FR-006**: Discovered nodes MUST be passed in as an argument. The shared object MUST NOT
  reach into the daemon's listener; discovery remains this daemon's responsibility.
- **FR-007**: The warning naming adopted-but-absent nodes MUST survive. Since it is not part
  of refresh's orchestration, the daemon MUST call `missing_adopted(discovered)` itself.
- **FR-008**: The pre-save `required_fields` check MUST NOT be reproduced. The shared save
  path already rejects the same documents through schema validation; the local check is a
  duplicate of that with a friendlier message and a different exception type.

### Functional Requirements — the RPC contract (User Story 1)

- **FR-009**: The response shape `{'OK': bool, 'error'?: str}` MUST be preserved exactly.
  It is a contract with a live Angular component, not an internal detail.
- **FR-010**: The shared object returns a bare boolean. The daemon MUST reconstruct all
  three error strings — `Node {uuid} not found`, `Cannot adopt node {uuid}: node is offline`,
  and `Cannot unadopt master node` — from the false return and which precondition failed.
- **FR-011**: Every well-formed request over the engine socket MUST receive a response,
  including actions other than `nodelist_modify` and including the unknown-action branch.
  The migration MUST NOT narrow this back to a single answering path.

### Functional Requirements — correctness debts touched by the same change

- **FR-012**: The daemon MUST NOT retain a method that raises before its own error handling
  can run. `cleanup()` is that method, and it has **no callers**; it MUST be removed rather
  than repaired. Repairing it would make configuration the daemon does not otherwise need a
  requirement of its *construction*, which trades a dead method for a boot-time failure
  mode. If a caller ever needs it, it returns with its collaborator resolved lazily.
- **FR-013**: The daemon MUST reach library functionality only through public paths. The two
  imports from the library's internal XML package MUST go: one is replaced by the public
  config-manager accessor, and the other two names have no call site at all and are deleted
  outright rather than given public synonyms.
- **FR-014**: The timeout-loop import MUST move off the deprecation shim onto the current
  class, at all three of its use sites.

### Functional Requirements — the Avahi cutover (User Story 2)

- **FR-015**: The discovery TXT-record key MUST become `node_role`, carrying
  `controller` / `node` / `firstrun`.
- **FR-016**: Every place **this repository** resolves an Avahi service template by name
  MUST follow the rename to `cuems.service.{controller,node,firstrun}`, including the
  installer's path construction for both the controller and the inline node case. The
  shipped template **files** are renamed in `cuems-common`, not here — this repository
  ships none (FR-018). So this requirement is on the *resolution*, and it depends on the
  file rename landing in the same window (FR-019); resolving a renamed name against
  un-renamed files is a controller that cannot promote itself.
- **FR-017**: The listener's translation table from the retired vocabulary MUST be retired
  with it. No mapping from the old values may remain.
- **FR-018**: This repository's three root-level copies of the service templates MUST be
  deleted, not renamed. They ship nothing — the files the daemon reads at runtime are
  installed by `cuems-common` — so keeping a second copy of a wire contract that can drift
  is the duplication this work exists to end.
- **FR-019**: No half-renamed state may ship. This repository's half and `cuems-common`'s
  half MUST merge together.
- **FR-020**: The two source comments deferring the TXT-record change to a feature that has
  since closed MUST be corrected.

### Functional Requirements — packaging and documentation (User Story 3)

- **FR-021**: This package MUST land at a version satisfying the constraint `cuems-common`
  already publishes against it, so the two cannot be installed in a combination that
  half-renames the vocabulary.
- **FR-022**: The library dependency MUST be expressed identically in the Python and Debian
  metadata, which currently disagree, and MUST carry an upper bound or a break constraint in
  addition to a floor — a floor alone cannot express "refuse a library that has moved past me".
- **FR-023**: This repository's own architecture documentation MUST stop asserting that the
  daemon does not touch network plumbing. It does, on the controller-promotion path, and two
  other documents already record the correction.

### Scope boundaries

- **FR-024**: The daemon's other nine responsibilities MUST NOT be restructured. This feature
  removes one responsibility; it MUST NOT add another, and it MUST leave the recorded
  atomization basis valid for whoever executes the split.
- **FR-025**: No test of the node model may be added to this repository. The model and its
  testing live in the library exclusively; a test of it appearing here is a regression, not
  coverage.

### Key Entities

- **Node record** — one cluster member's identity and state: uuid (the only stable key),
  MAC, name, role, address, adopted, online. Persisted per node in the network map.
- **Network map** — the cluster's topology as a document other services read. Its `online`
  field is a discovery-pass snapshot recording what this daemon last saw, not a liveness
  signal, and only this daemon writes it.
- **Discovery record** — what mDNS reports about a peer at one moment: uuid, role, address.
  Carries no adoption state; adoption is map state, never wire state.
- **Modify request** — the operator's add/remove instruction, arriving over the engine
  socket and answered with the success/error shape User Story 1 protects.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The characterization tests written to pin this behaviour before it moved pass
  **unchanged** against the new API. Editing them to accommodate the API voids the result —
  the swap is done when they pass, not when the code looks equivalent.
- **SC-002**: Zero of the nine replaced methods remain, counted, not asserted.
- **SC-003**: An operator add and an operator remove are each driven through the real
  dispatch path on the controller and observed to work end to end, plus each of the three
  failure responses. "It imports" and "the suite is green" do not satisfy this.
- **SC-004**: Zero occurrences of the retired TXT key remain in this repository outside the
  vendored planning snapshots — shipped source, templates and developer scripts alike.
- **SC-005**: The full test suite passes, with no test disabled or skipped to achieve it.
- **SC-006**: A controller and a node, both carrying the renamed vocabulary, discover each
  other and resolve roles. Verified against the counterpart repository's half, not asserted
  from this side alone.
- **SC-007**: An out-of-order package installation is attempted and observed to be refused.
  A gate that has never been demonstrated is a claim.
- **SC-008**: Zero imports from the library's internal XML package remain, and zero imports
  from the deprecated timeout-loop path.

---

## Decisions already taken

Settled 2026-09-07 before this spec was written. Recorded so they are not re-litigated:

1. **Package version** — this feature lands at `0.1.0-8`, carrying both the object adoption
   and the Avahi half, satisfying the constraint `cuems-common` already ships.
2. **Vocabulary** — TXT key `node_role`; values `controller` / `node` / `firstrun`; templates
   `cuems.service.{controller,node,firstrun}`. Chosen to match the role enumeration, the
   map's own field name, and the counterpart repository's existing role-suffix convention.
3. **Duplicate templates** — deleted here, not renamed (FR-018).
4. **The first-run adoption clear** — already deleted, ahead of this spec, in its own commit.
   It had no reachable correct effect and one harmful one: it silently reverted operator
   adoptions on a first-boot controller. The full analysis, and the three distinct signals
   this repository calls "first run", are recorded in `specs/planning/08-firstrun-signals.md`.
   This also closes the library's "not ported, left to reconcile" note — there was nothing
   to reconcile.
5. **The developer script** that publishes the retired key is updated along with everything
   else. It ships in no package, but a developer script advertising a vocabulary the cluster
   no longer speaks misleads whoever next runs it, so it counts toward SC-004.
6. **"master" deliberately survives in three places**, as exemptions rather than oversights.
   The RPC error string `Cannot unadopt master node` is byte-for-byte fixed by the UI
   contract (FR-010). The master-lock mechanism — `CUEMS_MASTER_LOCK_FILE`,
   `update_master_lock_file` and `/etc/cuems/master.ip` — is a marker-file mechanism, not the
   XML field, and `cuems-common` records it as needing its own coordinated migration. And
   `interfaces.master` is a network-interfaces template, unrelated to discovery. SC-004
   counts only the retired TXT key, so none of these conflict with it today; they are named
   so a later master/slave sweep does not mistake them for work this feature missed.

## Assumptions

- The counterpart repository's half of the vocabulary cutover is planned and readable but
  **not yet executed**; the field rename that already landed there is a different rename
  that happens to share a word. This feature's half is written against that plan and merges
  with it.
- The library version carrying the public replacements is present in the development
  environment; the packaged floor moves to match it.
- The daemon runs on one controller today and is disabled across the rest of the fleet.
  That bounds the blast radius; it does not reduce the care the one live controller needs.
- Avahi and zeroconf behaviour in this repository is characterized against mocks, not
  exercised against a live network. SC-003 and SC-006 therefore require verification on real
  hardware and cannot be satisfied by the suite alone.
- The dead role-check helper with no callers is left in place: it belongs to a different
  responsibility, outside this feature's boundary under FR-024.
