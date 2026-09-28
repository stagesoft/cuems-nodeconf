<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Feature Specification: Start-up readiness — answer honestly while the daemon is still coming up

**Feature Branch**: `003-startup-readiness`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "using @specs/planning/10-readiness-window.md"

**Source**: `specs/planning/10-readiness-window.md` (written 2026-09-28 against `2e2ae40`; its
coordinates re-measured against `6f31a7a` while writing this spec — all hold). It folds in the three
decisions the maintainer took on 2026-09-28 (D1–D3, brief §9.4): the Avahi-record work from
`cuems-utils` feature 011 is **in** this feature, the library primitive `NodeIndex.ensure` is consumed
rather than reimplemented, and hardware verification lives in this repository's ledger, entry §5.

**What this feature is.** The daemon starts answering requests from the engine **before** it has
loaded the cluster map. For up to ten seconds after boot (longer on a slow interface) an operator who
clicks "add node" gets a confident, specific, wrong answer: *"Node … not found"*, for a node that is
present and adoptable. Nothing in the log says anything was amiss. In the same start-up sequence, the
daemon currently announces an identity copied from a package template rather than the identity the
node was provisioned with, and learns its own uuid from that announcement — the reverse of the identity
contract. This feature makes the daemon **say what state it is in**: a distinguishable "still starting
up" refusal until the map is loaded, an identity announced only from the node's own provisioning, and
a refusal to start at all when the node has no provisioning to announce. It also settles the four
stale analysis documents at the repository root, and triages the live remainder of the start-up
backlog explicitly.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An operator's adopt during start-up is refused for the right reason (Priority: P1)

An operator on the controller opens the settings page shortly after boot and adds a node. If the
daemon has not yet finished loading the cluster map, the operator's request must be refused with a
message that says the daemon is **still starting up** — never *"Node not found"*, which is a
statement about the node and is false. The refusal stays inside the response contract the engine and
the UI already understand (`OK` false, plus an `error` string), so nothing upstream has to change to
keep working, and the operator can simply try again a few seconds later.

**Why this priority**: It is the operator-visible defect and the core of the feature. Before
`cuems-engine`'s instant-refusal change the operator got a fifteen-second stall; now they get a
definite wrong answer, which is worse because it is believable.

**Independent Test**: Deliver a well-formed adopt request to the daemon's engine callback after the
request socket is live but before the map has been loaded, and assert the answer names start-up and
not the node. Deliver the same request after the map is loaded and assert the pre-existing behaviour
(adopted, or refused for a real reason) is unchanged. Both without touching real hardware.

**Acceptance Scenarios**:

1. **Given** the daemon has bound its request socket but not yet loaded the cluster map, **When** an
   adopt or unadopt request for any uuid arrives, **Then** the answer is `OK: false` with an error
   string that says the daemon is still starting up, and the string does not contain *"not found"*.
2. **Given** the same window, **When** any other well-formed request arrives (unknown action, missing
   action, malformed body), **Then** it is answered exactly as it is today — every request over the
   socket is answered, before and after readiness.
3. **Given** the cluster map has been fully loaded (both the live document and the in-memory index
   are installed), **When** an adopt request arrives, **Then** the answer is whatever it was before this
   feature: adopted, already adopted, offline node refused, or genuinely not found.
4. **Given** a request that arrives after the document is installed but before the index is
   installed, **When** it is processed, **Then** it is still answered with the start-up refusal — a
   half-built state is never advertised as ready.
5. **Given** the daemon loses the race and the engine's request arrives before the daemon has bound
   its socket at all, **When** the engine checks for the socket, **Then** the engine's existing
   "not running" refusal applies (unchanged by this feature) and the daemon, once up, behaves as in
   scenario 1 or 3 depending on timing. The change is correct whether the daemon wins or loses.

---

### User Story 2 - The daemon announces only the identity the node was provisioned with (Priority: P2)

When the daemon starts, the identity it publishes on the local network (its uuid and MAC in the mDNS
record) must be the one recorded in the node's own settings file — not a value copied from a package
template that every upgrade resets and that, today, carries a real production controller's uuid. The
daemon renders the record from the settings file before it opens its request socket, so the engine's
"is nodeconf available?" probe never sees a socket in front of a daemon announcing the wrong self. If
the node has never been provisioned — no settings file, or the placeholder identity the templates now
ship with — the daemon refuses to start, says so in the provisioning tool's own words
(*NOT PROVISIONED*), announces nothing and opens no socket.

**Why this priority**: A node announcing another node's uuid is the "duplicate self that never
merges" failure the ecosystem already met once, and `cuems-utils` feature 011 has already moved the
minting of identity to install time on the assumption that this daemon will honour it. Without this
half, 011's contract is one-sided. It is P2 only because the readiness refusal is what the operator
sees first.

**Independent Test**: Start the daemon against a settings file with a real uuid and a role template
containing the placeholder; assert the live record carries the real uuid, was written before the
request socket was created, and that a second start with identical content does not reload the mDNS
daemon. Start it against a placeholder settings file and assert it exits non-zero, writes no record and
creates no socket. All with the filesystem and the mDNS daemon stubbed.

**Acceptance Scenarios**:

1. **Given** a provisioned node (settings file with a real uuid and MAC) and a role template carrying
   the placeholder token, **When** the daemon starts, **Then** the live mDNS service record equals the template
   with the placeholder replaced by the settings uuid, it is written before the request socket exists,
   and the mDNS daemon is reloaded once.
2. **Given** the live record already equals what would be rendered, **When** the daemon starts,
   **Then** the record is not rewritten and the mDNS daemon is not reloaded.
3. **Given** no settings file, **When** the daemon starts, **Then** it logs *NOT PROVISIONED*, exits
   non-zero, writes no mDNS service record and creates no request socket.
4. **Given** a settings file whose uuid is the placeholder, **When** the daemon starts, **Then** the
   outcome is identical to scenario 3.
5. **Given** the daemon changes role (elects itself controller, stays a node, or resumes a previous
   controller role), **When** it installs the role's record, **Then** that record is rendered from the
   settings file the same way, never copied verbatim.
6. **Given** discovery has completed, **When** the daemon identifies its own entry among the
   discovered nodes, **Then** that entry's uuid equals the settings uuid; if it does not, the daemon
   refuses loudly rather than adopting a foreign identity as its own.
7. **Given** an operator re-mints the node's identity with the provisioning tool, **When** they
   restart the daemon, **Then** the record follows the new identity, and the provisioning tool's check
   reports agreement; until the restart, that check reports disagreement. This consequence is written
   down for operators.

---

### User Story 3 - The node's own map entry comes from the shared library, not a private insert (Priority: P3)

When the daemon seeds this node's own row into the cluster map, it does so through the library
primitive added for exactly this purpose by `cuems-utils` feature 011, inserting the daemon's own node
record by reference so that later updates to it are seen by the map. The daemon adds no private
equivalent while waiting for that primitive to land; the plan names the library commit it depends on.
The existing fallback for a map that is absent altogether stays.

**Why this priority**: It is a correctness-by-construction item that closes plan 09's open option
rather than an operator-visible defect; it rides on the same start-up sequence and the same package
re-cut, so landing it separately would cost a second coordinated release for no benefit.

**Independent Test**: With a map that does not list this node, start the daemon and assert the row
appears in the map, is the same object the daemon holds for itself, and that no daemon-side insertion
code exists. With a map that already lists this node, assert the seeding is a no-op.

**Acceptance Scenarios**:

1. **Given** a map that does not list this node, **When** the daemon has identified itself, **Then**
   this node's row is present in the index through the library primitive, aliased to the daemon's own
   node record.
2. **Given** a map that already lists this node, **When** the same step runs, **Then** nothing is
   inserted and nothing is rewritten.
3. **Given** no map file at all, **When** the daemon starts, **Then** the existing empty-map fallback
   from feature 002 still applies, and seeding then proceeds as in scenario 1.

---

### User Story 4 - The consumers of the refusal know what to do with it (Priority: P2)

The engine relays this daemon's answers to the editor and on to the operator's screen. Today the
engine decides whether this daemon is available by checking that its request socket exists — a signal
that is true for the whole start-up window. This feature gives the engine a distinguishable answer;
what the engine and the UI then **do** with it is a decision that crosses four repositories and must
be recorded, not left to whoever touches the engine next.

**Why this priority**: Without a recorded decision the readiness refusal is a string nobody consumes
correctly, and the two consumer repositories already carry prohibitions (no deeper reliance on the
socket as readiness in the engine; no client-side retry or string interpretation in the editor) that
constrain the answer.

**Independent Test**: The feature's artefacts state the decision, the alternatives rejected and why,
and restate the two consumer prohibitions verbatim. That is a review check, not a runtime one.

**Acceptance Scenarios**:

1. **Given** this feature's plan, **When** it is reviewed, **Then** it records which of the candidate
   behaviours the engine and UI adopt for a start-up refusal, and names the repositories that carry
   the follow-up work.
2. **Given** the engine's instant-refusal behaviour when the socket is absent, **When** this feature
   lands, **Then** that behaviour is unchanged — its *signal* is what this feature corrects, not its
   decision.

**The decision (taken 2026-09-28, option D)**: the engine and the editor **relay the refusal string
verbatim** as the error, with no retry and no new UI affordance. The operator reads *"nodeconf is
still starting up"* on the settings page and tries again by hand. Rejected: (A) a brief retry in the
engine — contradicts its deliberate, hardware-measured instant refusal; (B) a distinct "starting up"
affordance in the UI — new work in `cuems-frontend` with no adoption-tier UI scheduled; (C) treating
the refusal as "nodeconf unavailable" — tells the operator to enable a daemon that is already
running. Option D is the minimum the two consumer prohibitions permit and requires **no code change
in any consumer repository**; the plan records it and names `cuems-engine` and `cuems-editor` as the
repositories that must simply keep relaying error strings unmodified.

---

### User Story 5 - The repository root carries no stale analysis, and the live backlog is triaged (Priority: P4)

A maintainer picking this repository up on a fresh checkout finds planning and analysis under
`specs/planning/`, nothing else at the root beyond the readme and the development guide. The one
start-up analysis that still has live content moves there, dated, with a per-finding status column
showing which of its findings are already closed (nine of twelve), which is moot, which is half-closed
and which cannot be closed as written. The three documents describing a fix to a method that no longer
exists are deleted. The live remainder of that backlog — two findings and four runtime issues — is
sorted into or out of this feature explicitly, per item.

**Why this priority**: Housekeeping, but housekeeping the brief measured: scoping it as "move one
file" leaves three superseded siblings in place, and an untriaged backlog is how the same item comes
back. It is independent of the code change and can land first.

**Independent Test**: List the markdown files at the repository root and expect exactly two. Open the
relocated analysis and expect a measurement date and a status per finding. Read the triage and expect
a disposition for each live item.

**Acceptance Scenarios**:

1. **Given** the repository after this feature, **When** the root-level markdown files are listed,
   **Then** only `CLAUDE.md` and `README.md` remain.
2. **Given** the relocated analysis at `specs/planning/11-startup-analysis.md`, **When** it is read,
   **Then** it states when it was measured and carries a status for each of its twelve findings and
   five runtime issues, matching the brief's §5.2.
3. **Given** the three deleted documents, **When** their subject is searched for in the daemon source,
   **Then** the method they describe does not exist, which is the recorded reason for deletion.
4. **Given** feature 001's task list, which names all four files as they were, **When** this feature
   lands, **Then** that historical reference is left as written.
5. **Given** the live backlog items, **When** this feature's artefacts are read, **Then** each has a
   written disposition (in this feature, its polish phase, a separate maintenance pass, its own
   feature, or retired), with the reason.

**The triage (taken 2026-09-28, option B)**, one disposition per live item:

| Item | Disposition | Reason |
|---|---|---|
| Runtime issue 1 — the ten-second interface wait | **In, core** | It bounds the very readiness window of Story 1; Story 6 below |
| Finding 10 — hardcoded five-second controller sleep | **In, polish phase** | Small, independent, same file, same re-cut |
| Runtime issue 2 — no mDNS-daemon pre-flight check | **In, polish phase** | Same |
| Runtime issue 4 — no D-Bus availability check | **In, polish phase** | Same; the suite stubs D-Bus, so this is hardware-verified only (FR-020) |
| Runtime issue 5 — simultaneous boot, several nodes elect themselves controller | **Out — its own feature** | A real election protocol; Principle VI territory far larger than this window |
| Finding 12 — "network/subprocess/D-Bus operations lack error handling" | **Retired** | Unfalsifiable as written; any named site becomes its own item when found |

Findings 1–9 are closed and finding 11 is moot; none is work.

---

### User Story 6 - The start-up window is bounded on purpose, and its neighbours are tidied (Priority: P5)

The length of the window in Story 1 is set by how long the daemon waits for a usable network
interface. That wait, and three small start-up concerns next to it, are made deliberate rather than
incidental: the interface wait and the controller's pre-discovery pause become configurable with
their current values as defaults and a stated justification; the daemon checks up front that the mDNS
daemon and the system message bus it depends on are reachable, and says so plainly when they are not,
instead of failing later inside an unrelated operation.

**Why this priority**: Option B of the triage. Cheap, independent, in the same file and the same
re-cut; landing them here avoids a second coordinated release for four one-line changes. They are
polish and MUST NOT delay Stories 1–3.

**Independent Test**: Configure a shorter interface wait and assert start-up honours it; leave it
unset and assert the current ten seconds. Stub the mDNS daemon and the message bus as unreachable and
assert the daemon reports which one is missing before it opens its socket.

**Acceptance Scenarios**:

1. **Given** no configuration, **When** the daemon starts, **Then** the interface wait is ten seconds
   and the controller's pre-discovery pause is five seconds, as today.
2. **Given** either value configured, **When** the daemon starts, **Then** it uses the configured value
   and logs it.
3. **Given** the mDNS daemon or the message bus is unreachable at start, **When** the daemon starts,
   **Then** it logs which dependency is missing before creating its socket; whether it waits, exits or
   proceeds via the existing recovery path is decided in the plan and stated there.

---

### Edge Cases

- **Request arrives before the socket exists** (daemon lost the boot race): the engine's existing
  socket-absent refusal handles it; this feature changes nothing there. Once the socket exists, the
  daemon's own readiness answer takes over.
- **Request arrives between the document being installed and the index being installed**: still
  refused as "starting up" — readiness is asserted only after both are in place.
- **Interface discovery times out** during the window: the daemon exits, as today. Any request queued
  at that moment gets the socket-absent path on the engine side. The refusal must not mask the exit.
- **Readiness never reverts.** Once the map is loaded the daemon stays ready for its lifetime; a role
  change or a later map refresh does not reopen the window. If a future change needs to reopen it, that
  is a new decision.
- **Settings file present but unreadable or malformed**: treated as not provisioned — refuse to start,
  same message.
- **Role template missing** on a provisioned node: start-up fails naming the missing template, as it
  does today.
- **Rendered bytes unchanged from the live record**: no write, no mDNS reload — a restart is silent.
- **The mDNS daemon cannot be reloaded** after a changed record: logged loudly; the daemon proceeds,
  since the existing recovery path already restarts that service on failure.
- **Discovered self carries a uuid other than the settings uuid** (stale record from an earlier
  identity, or a foreign template): the daemon refuses loudly rather than continuing with the wrong
  self; the fix for operators is to restart after re-provisioning.
- **The map already lists this node**: the seeding primitive is a no-op; nothing is written.
- **The library build predates the seeding primitive**: the suite must detect it, in the same way
  feature 002's library-prerequisite test does, rather than a node discovering it at boot.
- **A second click while the first is being refused**: each request is answered independently and
  instantly; no queueing, no stall.

## Requirements *(mandatory)*

### Functional Requirements

**The readiness refusal (Story 1)**

- **FR-001**: The daemon MUST track whether it has finished loading the cluster map, and MUST answer
  any adopt or unadopt request that arrives before then with `OK: false` and an error string that
  names start-up (assumed wording: *"nodeconf is still starting up"*). That string MUST be
  distinguishable from every existing refusal and MUST NOT read as a statement about the node.
- **FR-002**: Readiness MUST be asserted only after **both** the live map document and the in-memory
  index are installed. A state with one but not the other MUST answer as not ready.
- **FR-003**: The response contract `{'OK': bool, 'error'?: str}` MUST NOT change: no new key, no
  silent return, no raised exception, and no narrowing of which requests receive a reply
  (constitution IV). Every well-formed request over the socket MUST be answered, during the window and
  after it.
- **FR-004**: The behaviour after readiness MUST be exactly what it was before this feature. The
  existing engine-callback and adoption-flow tests MUST pass with **no subject or assertion changed**;
  a test that bypasses start-up MAY gain one setup line asserting readiness, and every such line MUST
  be listed in the commit (feature 002's precedent for its document setup).
- **FR-005**: The start-up order — socket creation, interface discovery, map load, readiness — MUST be
  stated explicitly in the plan, and the change MUST be correct whether the daemon wins or loses the
  boot race against the engine (constitution VI).
- **FR-006**: The refusal MUST be covered by a test that **exercises the window** — delivers a request
  between socket creation and map load — not by inspection.
- **FR-007**: A mutual-exclusion lock around the map writers is explicitly NOT the fix and MUST NOT be
  introduced as one: it serialises the writers but does not make an empty index any less empty.

**The consumers' decision (Story 4)**

- **FR-008**: The plan MUST record the Story 4 decision — option D, relay the refusal string verbatim
  with no retry and no new affordance — with the three alternatives rejected and why, and MUST state
  that no consumer repository changes code for it.
- **FR-009**: The engine's instant refusal when the socket is absent MUST NOT be reverted or weakened
  by anything this feature asks of the engine. The two consumer prohibitions stand and MUST be
  restated in the plan: the engine must not deepen its reliance on socket existence as readiness, and
  the editor must not add client-side retry or interpretation of the string.

**The announced identity (Story 2)**

- **FR-010**: At every start, **before** the request socket is created, the daemon MUST read the
  node's uuid and MAC from the settings file through the configuration manager it already constructs,
  render the role's mDNS service template into the live record by literal substitution of the
  36-character placeholder token, write it atomically, and reload the mDNS daemon **only** when the
  bytes changed.
- **FR-011**: When the settings file is absent, unreadable, or carries the placeholder uuid, the daemon
  MUST log *NOT PROVISIONED* (the provisioning tool's own wording), exit non-zero, announce nothing and
  create no socket.
- **FR-012**: The same rendering MUST be used at every role change — controller election, staying a
  node, and resuming a previous controller role. No path may copy a template verbatim into the live
  record.
- **FR-013**: After discovery, the daemon MUST assert that the entry it identifies as itself carries
  the settings uuid, and MUST refuse loudly otherwise.
- **FR-014**: The operator consequences MUST be documented in this repository: after re-minting an
  identity the remedy is to restart the daemon; the provisioning tool's check exits 1 while the live
  record disagrees with the source and 3 while the source is the placeholder.

**The own-row seed (Story 3)**

- **FR-015**: This node's row MUST be seeded through the library's `NodeIndex.ensure` primitive,
  inserting the daemon's own node record by reference per the aliasing contract. The daemon MUST NOT
  add a private equivalent. The plan MUST name the `cuems-utils` commit that adds the primitive. The
  empty-map fallback from feature 002 stays for a map that is absent altogether.
- **FR-016**: The suite MUST detect a library build that lacks the primitive, in the manner of feature
  002's library-prerequisite test.

**The analyses and the backlog (Story 5)**

- **FR-017**: `STARTUP_ANALYSIS.md` MUST be relocated to `specs/planning/11-startup-analysis.md`
  (preserving history) and annotated with a measurement date and a per-finding status matching the
  brief's §5.2. `BUGFIX_NETWORK_MAP.md`, `BUGFIX_COMPLETE.md` and `DEPLOYMENT_STEPS.md` MUST be
  deleted, with the reason recorded (they describe a fix to a method that no longer exists). Feature
  001's historical reference to the four files MUST NOT be rewritten.
- **FR-018**: The six live backlog items MUST carry the dispositions in Story 5's table: runtime
  issue 1 in as core, finding 10 and runtime issues 2 and 4 in as a polish phase, runtime issue 5 out
  to its own feature, finding 12 retired. Findings 1–9 and 11 MUST NOT appear as work.

**The bounded window and its neighbours (Story 6, polish phase)**

- **FR-023**: The interface wait and the controller's pre-discovery pause MUST be configurable, with
  the current values (ten and five seconds) as defaults and their justification stated where they are
  defined.
- **FR-024**: Before creating its socket, the daemon MUST check that the mDNS daemon and the system
  message bus are reachable and MUST log which one is missing when either is not. The plan decides and
  states whether it then waits, exits, or proceeds through the existing recovery path.
- **FR-025**: The polish phase MUST be ordered after Stories 1–3 in the task list and MUST NOT block
  them; if it slips, it is dropped to the maintenance pass, not the stories.

**Gates and release (all stories)**

- **FR-019**: `pytest` MUST stay green with no skips introduced, adopt/unadopt coverage MUST NOT be
  reduced, and the vendored yardstick MUST stay unchanged and byte-identical to the library's copy.
- **FR-020**: Verification against the real dispatch path (operator UI → editor → engine → daemon) and
  on real hardware MUST be either performed and recorded, or recorded plainly as not performed. The
  record is entry §5 of the hardware-verification ledger in feature 002's checklists, already written;
  silence is not an acceptable state.
- **FR-021**: Because packaged content changes, the merge-candidate tag MUST be re-cut **once** for
  both the readiness change and the identity render, inside the unreleased `0.1.0-8` changelog entry,
  and the re-cut MUST be announced to the `cuems-common` and `cuems-power-bridge` flows before merge.
- **FR-022**: This feature MUST NOT add a responsibility to the daemon's main class (constitution V):
  readiness belongs to lifecycle, and rendering the record belongs to the existing Avahi
  service-template responsibility. The plan's constitution check MUST say so.

### Key Entities

- **Readiness state**: whether the daemon has finished loading the cluster map. Set once, after both
  the live document and the index are installed; never reverts; consulted by every adopt or unadopt.
- **Engine request / response**: a message over the daemon's request socket carrying an action and,
  for adoption, a uuid and an add/remove verb; answered with `OK` and an optional `error` string. The
  contract with the operator UI.
- **Provisioned identity**: the uuid and MAC in the node's settings file, minted once at install by
  the provisioning tool. The sole source of what the daemon announces.
- **Placeholder identity**: the all-zeros uuid the role templates now ship with; its presence in a
  settings file means "not provisioned".
- **mDNS service record**: the file the mDNS daemon publishes for this node, rendered from the role
  template and the provisioned identity; owned solely by this daemon.
- **Own node record**: the daemon's in-memory record of itself, seeded into the index by reference
  through the library primitive.
- **Start-up analysis**: the relocated, dated document carrying the boot-order narrative and a status
  per finding; the only written boot-order narrative this repository has.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero adopt or unadopt requests arriving before the map is loaded are answered with
  *"not found"* — shown by a test that exercises the window. Today every such request is.
- **SC-002**: 100% of well-formed requests are answered, before and after readiness, with the response
  shape unchanged; the 16 existing engine-callback tests pass with no subject or assertion changed
  (setup lines only, listed).
- **SC-003**: The full suite passes with no skips added (119 tests at baseline plus those this feature
  adds), and the yardstick file is byte-identical to the library's copy.
- **SC-004**: A node without provisioning exits non-zero at start with no socket and no mDNS service record —
  shown by a test for each of: no settings file, unreadable settings file, placeholder uuid.
- **SC-005**: A provisioned node's live mDNS service record carries the settings uuid at every start and after
  every role change, and an unchanged record causes no reload — shown by tests covering all four sites.
- **SC-006**: On real hardware, a second node sees this node exactly once with the settings uuid, and
  the provisioning tool's check exits 0 before and after a reboot — recorded in ledger §5, or recorded
  there as not performed.
- **SC-007**: The repository root lists exactly two markdown files.
- **SC-008**: Every one of the six live backlog items has a written disposition; none of the nine
  closed findings appears as work.
- **SC-009**: Exactly one re-cut of the merge-candidate tag and one announcement to the other flows.
- **SC-010**: The plan's constitution check names principles I, IV, V and VI and states how each is
  satisfied; the Story 4 decision (option D) is recorded with its three rejected alternatives.
- **SC-011**: With no configuration the interface wait and the controller pause are unchanged (ten
  and five seconds); with configuration they follow it — shown by tests. A missing mDNS daemon or
  message bus is named in the log before the socket exists — shown by a test with both stubbed.

## Assumptions

- **Wording of the refusal**: *"nodeconf is still starting up"*. Any wording is acceptable that names
  start-up and cannot be read as being about the node; this one is used unless the Story 4 decision
  needs a different token.
- **Readiness is set once and never reverts.** The window exists only between socket creation and the
  first map load. Role changes and later refreshes do not reopen it.
- **The window's length becomes a configured value** (Story 6) but its default does not change; this
  feature makes the wait deliberate, it does not tune it.
- **The library primitive lands first.** `cuems-utils` feature 011 adds `NodeIndex.ensure` inside the
  already-pinned `0.1.0rc16`; the version string cannot express the difference, which is why FR-016
  exists. Implementation of Story 3 waits for that commit; Stories 1, 2, 4 and 5 do not.
- **Templates carry the placeholder.** `cuems-common 1.3.0-23` ships the role templates with the
  all-zeros uuid and no longer mints identity itself; the mutual `Breaks` between it and
  `cuems-nodeconf 0.1.0-8` already exist and no version moves.
- **The settings file is always present on a provisioned node** (maintainer-confirmed: the daemon is
  never standalone), so "absent" genuinely means "not provisioned", not "wrong path".
- **The hardware-verification ledger entry §5 is the single record** for every on-node check this
  feature owes (decision D3); `cuems-utils` points at it and keeps no second list.
- **The engine's socket probe stays as it is.** The decision in Story 4 is about what the consumers do
  with a refusal they can now distinguish, not about replacing the probe.
- **Dev checkout cannot prove hardware behaviour**: D-Bus and systemd are stubbed in the suite, so
  FR-020 is the honest gate, not the suite.

## Out of Scope

- A real controller-election protocol (runtime issue 5): its own feature, by the Story 5 triage.
- Finding 12 as a work item: retired as unfalsifiable; named sites become their own items when found.
- Any change to `cuems-engine`, `cuems-editor` or `cuems-frontend` — this feature records the decision
  and delivers the string; the consumer work is theirs.
- The `apply-identity` CLI and the OS-side identity chain (hostname, hosts file, mDNS daemon config).
- `dhcpd`, `dhclient`, `hostapd`, and any second network-plumbing path (constitution).
- Merging `feat/nodelist-modify-hardening`; its surviving finding is this feature, the rest is
  superseded or does not reproduce (brief §6).
