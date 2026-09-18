# Feature Specification: Reach the network map through public paths only

**Feature Branch**: `002-public-network-map-path`

**Created**: 2026-09-18

**Status**: Draft

**Input**: User description: "Properly develop the changes described in @specs/planning/04a-cuems-nodeconf-public-path.md, use option A for section 3 and keep the test import for section 4. Try to focus exclusively on the task at hand so the SDD proceeding consists of the minimal steps possible."

**Source**: `specs/planning/04a-cuems-nodeconf-public-path.md` (vendored from `cuems-utils@9e5e79f`, validated against this tree at `b3f5bb0`). This feature closes out feature 001; it is deliberately one story.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The daemon reaches the network map only through the library's public surface (Priority: P1)

The CUEMS maintainers want the node daemon to depend on the shared library **only** through its public paths (decision D34), so that the library can reorganise its internals without breaking the daemon. Feature 001 met that for everything except one reference to an internal network-map class, added because no public way to obtain a network-map document seemed to exist. One does: the library's public configuration manager already hands back the live document when the map is loaded.

The daemon therefore stops building its own documents and instead keeps the one it already loads at start-up, refilling it from its in-memory index before every save and refresh. When no map file exists at start-up, it first writes a minimal empty map — the same shape `cuems-common` ships — and loads that, so there is always a loaded document to keep (option A).

Operators and downstream services see no change: adoptions persist exactly as before, and the map file other services read keeps its content and its readability.

**Why this priority**: It is the whole feature. Nothing else is in scope.

**Independent Test**: Search the shipped daemon for references into the library's internal configuration package (expect none), run the full suite and the vendored equivalence yardstick (expect all green, with no existing test's subject or assertion changed), and start the daemon once with a map present and once without.

**Acceptance Scenarios**:

1. **Given** the shipped daemon source, **When** it is searched for references into the library's internal configuration package, **Then** there are none.
2. **Given** a map file on disk, **When** the daemon starts, **Then** it keeps the document that the load produced, and every later save and refresh uses that same document.
3. **Given** an operator adopts a node between two discovery passes, **When** the next pass runs, **Then** the adoption appears in the map on disk — the kept document never overrides the in-memory index.
4. **Given** no map file at start-up, **When** the daemon starts, **Then** it writes an empty map with the shape `cuems-common` ships, loads it through the same path as an existing map, and proceeds exactly as it would on a node shipped with that empty map.
5. **Given** the empty map written in scenario 4, **When** another service running as a non-root user reads it, **Then** it can: the file is not owner-only.
6. **Given** the test suite, **When** it is inspected after the change, **Then** tests still refer to the internal class to stop saves reaching the real filesystem, and that choice is recorded along with the reason for it.

---

### Edge Cases

- **No map file, and the directory cannot be written**: start-up fails loudly with a message naming the path, the same way start-up already fails when its other preconditions are missing. It does not carry on with an in-memory map that could never be saved.
- **The map exists but does not list this node yet** (every freshly provisioned node): the existing tolerance from feature 001 still applies, and the document is still kept.
- **The map fails validation**: start-up still fails loudly (unchanged).
- **A save fails**: it is still retried on the next refresh (unchanged), now through the kept document.
- **Nothing changed since the last write**: the map is still not rewritten (unchanged).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The shipped daemon MUST NOT reference anything in the library's internal configuration package. It reaches the network-map document only through the library's public configuration manager.
- **FR-002**: The daemon MUST keep the network-map document produced by the load it already performs at start-up, for its whole lifetime, and MUST NOT construct network-map documents itself.
- **FR-003**: Before every save and every refresh, the kept document's node list MUST be replaced in full from the in-memory index. The index remains the single in-memory source of truth, as feature 001 established.
- **FR-004** *(option A, §3)*: When no map file exists at start-up, the daemon MUST write a minimal empty map with the same shape `cuems-common` ships (an empty node list), and then load it through the same path used for an existing map.
- **FR-005**: The empty map written under FR-004 MUST be readable by non-root services (constitution I and II). If it cannot be written, start-up MUST fail with a message naming the path.
- **FR-006**: All other behaviour MUST stay as it is: the adopt/unadopt response contract with the UI (constitution IV), writing only when the map changed, retrying a failed write, tolerating a map that does not yet list this node, and failing loudly on an invalid map.
- **FR-007** *(§4)*: Test files MUST keep their existing references to the internal class they patch to stop saves reaching the real filesystem, and all 28 patch sites MUST remain. **Reason:** a test patching a collaborator is not a consumer using an API; D34 governs what the shipped daemon reaches for at runtime, not how its tests isolate the filesystem.
- **FR-008**: The vendored equivalence yardstick MUST NOT be edited and MUST stay byte-identical to the library's copy. It is an enumerated exemption from any count of internal references, and it is permanently out of scope.
- **FR-009**: This feature MUST NOT change the shared library, request a public alias from it, derive the internal class from a live object's type, or reimplement the library's refresh orchestration in the daemon.
- **FR-010**: The two decisions — option A for §3 and keeping the test references for §4 — MUST be recorded with their reasons in this feature's artefacts.

### Key Entities

- **Network-map document**: the library's live object for `/etc/cuems/network_map.xml`. It is obtained through the public configuration manager, kept by the daemon, refilled from the index before use, and is what saves and refreshes operate on.
- **Node index**: the daemon's in-memory map of known nodes, keyed by MAC. It is the source of truth that the document is refilled from.
- **Empty map**: an XML network map with an empty node list, byte-for-byte the shape `cuems-common` ships as its conffile. It exists on disk before any document is loaded.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero references from the shipped daemon into the library's internal configuration package (was 1).
- **SC-002**: The full suite and the yardstick pass — 95 local tests plus 15 yardstick tests at the baseline, plus any tests this feature adds. No pre-existing test has its subject or assertion changed.
- **SC-003**: The vendored yardstick is byte-identical to the library's copy, verified by comparing the files rather than assumed.
- **SC-004**: An adoption made between two discovery passes is on disk after the next pass, shown by a test.
- **SC-005**: Starting with no map file yields a running daemon and an empty map readable by non-root services, shown by a test.
- **SC-006**: Both decisions (FR-010) are written down, with their reasons.

## Assumptions

- On any packaged host the map exists: `cuems-common` ships it as a conffile with an empty node list (`debian/install:204`, verified at `1a00159`), and this package depends on `cuems-common`. So FR-004 is reached only on a development checkout or where the file was deleted by hand. Option A keeps that path working without keeping an internal reference.
- The public configuration manager returning the live document is established library behaviour: its own save already depends on it, and `cuems-utils` documented it at the assignment (its T083). It is present throughout the pinned range `>= 0.1.0rc16, << 0.1.1~`, so there is no version floor change.
- Keeping a saved map's existing mode is the library's guarantee (`cuems-utils` `6fe2d3f`), not this feature's. FR-005 covers only the file this daemon creates itself.
- D23 holds: no other responsibility of the daemon class is touched.
- **Merge path** (maintainer instruction): this branch is **never pushed**. When done it is merged locally into `feat/xml-refactor`, because it is part of that branch's merge candidate. This repository's `xml-refactor-merge-candidate` tag is created only after that merge (feature 001, T042).
