<!--
SYNC IMPACT REPORT
Version change: (none) → 1.0.0
Rationale: initial ratification. No prior constitution existed in this repository;
the scaffold at .specify/memory/constitution.md was the unfilled core template.

Modified principles: none (initial adoption)

Added sections:
  - Core Principles I–VI
  - Operating Constraints
  - Testing Gate and Development Workflow
  - Governance

Removed sections: none

Principles derived from: CLAUDE.md (the five load-bearing bugs fixed during the
Phase-1 re-enable, the <online> ownership section, the mDNS field notes) and from
measurement of the live tree at feat/xml-refactor.

Follow-up TODOs: none. RATIFICATION_DATE is set to the date of this adoption
rather than marked TODO, because no earlier governance document exists to date
from.

Correction applied before ratification (no version bump — this document was not
yet committed): the scope statement originally reproduced this repository's
CLAUDE.md claim that the daemon does not touch network plumbing. Measured against
CuemsNodeConf.py:396/:724/:766, that claim is false — set_node_role stops
networking.service, overwrites /etc/network/interfaces from interfaces.master, and
restarts the unit during controller promotion. cuems-common's CLAUDE.md and the
atomization basis (row 6) both already record the correction; this repository's
CLAUDE.md is the outlier and should be fixed to match.
-->

# cuems-nodeconf Constitution

`cuems-nodeconf` is the node-side discovery and adoption daemon of the CUEMS
ecosystem. It uses Avahi (`_cuems_nodeconf._tcp.local`) to publish each node's
UUID, MAC, role and IP, and to maintain `/etc/cuems/network_map.xml`
automatically. It is Python 3.11+, ships as `cuems-nodeconf.service`
(`PartOf=cuems-node.target`), and **runs as root**. When reactivated it also owns
node identity: assigning `<role_id>` on adoption and applying the OS-side identity
chain (`hostnamectl`, `/etc/hosts`, `avahi-daemon.conf`).

`dhcpd`, `dhclient` and `hostapd` are outside its remit, and a change that moves
work into this daemon from any of them is a scope violation, not a convenience.

It **does** touch one piece of network plumbing, on exactly one path.
`set_node_role` → `change_network_to_master` → `change_network_settings_to_master`
stops `networking.service` over D-Bus, copies `/usr/share/cuems/interfaces.master`
over `/etc/network/interfaces`, restarts the unit, and sleeps ten seconds on each
side of the copy. This is the daemon's most destructive operation and it runs
during controller promotion on a live cluster. It is named here because
`CLAUDE.md` in this repository asserts the opposite — that assertion is false, and
`cuems-common`'s `CLAUDE.md` and the atomization basis both record the correction.

## Core Principles

### I. Root Privilege Is a Correctness Concern, Not a Convenience

This daemon runs as root alongside services that do not. Every filesystem object
it creates that another process opens — sockets, lock files, config files,
templates — MUST have its ownership and mode decided deliberately, stated in the
change that creates it, and verified by a test or a documented manual check.

The worst defect in this repository's history was creating `/tmp/nodeconf.ipc`
root-owned. The `cuems-user` engine then failed its Communicator read/write check
and exited 1 in a restart loop, but only when nodeconf won the boot race — so it
presented as an intermittent cluster failure with no obvious cause. The fix was
one `chmod 0666` after binding.

Rationale: a permissions mistake made by a root process does not fail in the root
process. It fails somewhere else, later, non-deterministically, and the traceback
names the victim rather than the cause. Treating permissions as correctness is the
only way that class of bug gets caught by review.

### II. The Output Is a File Other Services Read

`network_map.xml` is the cluster's topology, not this process's private state.
Writes to it MUST be complete or absent — never partial, never duplicated, never
racing another writer. A write that is wrong is a cluster that misbehaves, not a
process that fails, and the failure surfaces in services this repository does not
own.

Where the daemon can determine that nothing changed, it MUST NOT write. The
signature comparison that gates the write path exists for this reason and MUST be
preserved by any refactor of the write path.

`<online>` is this daemon's field and no other writer's. It records what discovery
saw at boot or at an explicit reconfigure — it is a snapshot, deliberately stale
between those moments, and it is NOT a real-time liveness signal. Runtime
liveness belongs to the engine's in-memory cluster probe. Code that needs
"boot-time intent" reads `<online>`; code that needs "alive right now" MUST ask
the engine. Overwriting `<online>` with a liveness signal corrupts its semantics;
this was attempted once and reverted.

### III. Identity Is Keyed by UUID

Nodes are matched, merged, adopted and unadopted by `uuid`. A name-derived value
MUST NOT be used as an identity key anywhere in the merge or adoption paths.

The duplicate-node bug came from merging by a MAC parsed out of the Avahi service
name: the controller's service is named `controller`, so the parse produced a
garbage key, the merge created a second node, and the real node was flipped
offline. Service names are operator-facing labels and MAY be anything; `uuid` is
the stable key and the only permissible one.

Rationale: a key derived from a display string keeps resolving. It does not throw,
the suite stays green, and the answer is silently wrong — the most expensive
failure class this ecosystem has.

### IV. RPC Responses Are a Contract With a Live UI

The chain `nodelist_modify` → `engine_callback` → adopt/unadopt originates in
`cuems-frontend`'s `settings.component.ts` (`confirmAddNode` / `confirmRemoveNode`),
a UI operators use today on the controller where this daemon runs.

The response shape `{'OK': bool, 'error'?: str}` is a contract. It MUST NOT change
shape, drop its error strings, or silently narrow which actions produce a reply.
Every well-formed request over `/tmp/nodeconf.ipc` MUST be answered: this is an
NNG Req/Rep socket, and returning without responding leaves the engine blocked
until its own 15-second timeout, which reaches the operator as an unexplained
stall rather than an error.

Any change to this chain MUST be verified end to end against the real dispatch
path. "It compiles" and "the unit test passes" are not evidence that the operator's
button still works.

### V. One Class Doing Ten Things — Deliberately, Temporarily, and No More

`CuemsNodeConf.py` is a single class of 774 lines covering ten responsibilities:
daemon lifecycle, network-interface discovery, Avahi orchestration, role election,
network-map logic, OS network reconfiguration, Avahi service-template files, mDNS
alias publishing, the master lock file, and engine IPC dispatch.

This is a known, recorded state with a written atomization basis, not an accident.
Two rules follow, and they are non-negotiable:

- New code MUST NOT add an eleventh responsibility to this class. Work that does
  not belong to one of the ten belongs in a new module.
- The atomization basis MUST be left valid. A change may remove a responsibility
  or narrow one; it MUST NOT restructure the class in a way that invalidates the
  recorded inventory for whoever executes the split.

Rationale: the class is large enough that every additional concern raises the cost
of the eventual split superlinearly. Holding the line is cheaper than the split
and can be enforced at review time.

### VI. Shutdown and Boot Ordering Are Product Behaviour

Two of the five defects fixed during the Phase-1 re-enable were ordering bugs: an
`nng` panic on shutdown, fixed by cancelling the engine listener and closing the
loop in the owning thread; and the IPC-permissions crash loop, which only appeared
when this daemon won a boot race against the engine.

Startup order, shutdown order, thread and event-loop ownership, and the behaviour
of every service that starts concurrently with this one MUST be reasoned about
explicitly in any change that touches lifecycle, threading or IPC. A change that is
correct only when it wins or only when it loses a race is not correct.

Rationale: race-dependent behaviour is invisible on a developer checkout and
reproducible only on real hardware at real boot. It has to be caught by design,
because it will not be caught by the suite.

## Operating Constraints

**Scope.** Avahi/zeroconf discovery, `network_map.xml` maintenance, node identity
(the `<role_id>` assignment and the OS-side identity chain), engine IPC, and the
single `/etc/network/interfaces` rewrite on controller promotion described above.
`dhcpd`, `dhclient` and `hostapd` are out of scope, permanently. The interfaces
rewrite MUST NOT be widened: no second plumbing path may be added to this daemon
without amending this constitution first.

**Domain logic lives in `cuemsutils`.** The node model and the network-map
config-object logic (merge, adopt, unadopt, refresh, signature, write
orchestration) live in `cuems-utils` on `NodeIndex` / `CuemsNetworkMapType`. This
daemon consumes them; it MUST NOT reimplement them ad hoc, and it MUST NOT carry
its own tests for them.

**Public import paths only.** `cuemsutils.xml` declares `__all__ == []` and is
internal machinery. This repository MUST reach library functionality through
public paths (`cuemsutils.tools.*`, `cuemsutils.config.*`, `ConfigManager`).

**Dependency pins are bounded.** The `cuemsutils` requirement MUST agree between
`pyproject.toml` and `debian/control`, and MUST express an upper bound or a
`Breaks:` in addition to a floor. A floor alone cannot say "refuse a library that
has moved past me", which is what the release gate actually requires.

**mDNS facts that constrain design.** `avahi-publish -a` cannot scope a static A
record to one interface — interface-scoped records need the D-Bus
`EntryGroup.AddAddress(interface_index, ...)` API. `avahi-daemon`'s native
hostname publication is already per-interface-correct, so a static
`controller.local` MUST NOT be published when the hostname is already
`controller`. `.local` is link-scoped and does not resolve across routers.

**Coordinated wire changes are atomic.** The Avahi TXT-record vocabulary is shared
with `cuems-common`. A publisher and a listener that disagree about the key
discover nothing, and discovery failure is how a cluster loses its topology. Such
a change MUST land as one cutover across both repositories; a half-renamed state
MUST NOT ship.

## Testing Gate and Development Workflow

**The gate.** `pytest` MUST pass — 16 test files under `tests/`, currently 81
tests, all green. A change MUST NOT be merged with a failing or skipped-without-
justification test, and MUST NOT reduce coverage of the adopt/unadopt dispatch
chain.

**What the suite honestly is.** Avahi and zeroconf behaviour in this repository is
**characterized, not unit-tested against a live network**. The listener tests
construct mock `ServiceInfo` objects with fabricated TXT properties and assert the
translation the listener performs on them. `dbus` and `systemd.daemon` are stubbed
in `tests/conftest.py` so the module imports at all on a dev checkout. This pins
translation logic and regressions in it; it does **not** exercise real mDNS,
real D-Bus, real systemd, or real multi-node discovery. Nothing in the suite proves
the daemon works on a node.

Consequently: any change to discovery, role election, the identity chain, OS
network reconfiguration, or boot/shutdown ordering MUST additionally state how it
was verified on real hardware, or state plainly that it was not. Both are
acceptable answers; silence is not.

**Characterization tests are a measurement, not a suggestion.** Where behaviour was
pinned by characterization tests before being moved, those tests are the
equivalence gate. They MUST be run against the new implementation and MUST pass
unchanged. Editing a characterization test to accommodate a new API destroys the
guarantee it exists to provide; if such a test genuinely needs to change, it
changes at its source of truth and is re-imported, never patched in place.

**Measure, do not transcribe.** Line numbers, occurrence counts and version pins
recorded in planning documents MUST be re-measured against the live tree before
being relied upon. This project has found stale coordinates repeatedly.

**Deployment reality.** This daemon is re-enabled on the formitgo controller and
still disabled across most of the fleet. That is context, not licence: the one
place it runs is a production controller with an operator-facing UI at the end of
its dispatch chain.

## Governance

This constitution supersedes other practices for `cuems-nodeconf`. Where it and a
planning document disagree, this document governs, and the disagreement is
recorded rather than silently resolved.

**Amendment procedure.** Amendments MUST be proposed as a change to this file,
carry a Sync Impact Report at its head, and state the rationale for the principle
added, changed or removed. A principle MUST NOT be weakened to accommodate an
in-flight migration; if a migration cannot satisfy a principle, that is a finding
about the migration.

**Versioning policy.** Semantic versioning of the document itself:
- **MAJOR** — a principle is removed or redefined incompatibly.
- **MINOR** — a principle or section is added, or guidance materially expanded.
- **PATCH** — clarification, wording, or non-semantic refinement.

**Compliance review.** Every feature plan MUST include a constitution check naming
which principles bear on it and how they are satisfied. Reviews MUST verify
compliance, and any complexity introduced against a principle MUST be justified in
writing rather than assumed. `CLAUDE.md` remains the runtime development guidance
for this repository and is expected to stay consistent with this document.

**Version**: 1.0.0 | **Ratified**: 2026-09-07 | **Last Amended**: 2026-09-07
