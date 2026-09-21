# Hardware & manual verification ledger — features 001 and 002

**Created 2026-09-21 (feature 002, T018 — FR-012, SC-008).** One place for every check that
needs real hardware or a human, for **both** features, so the debt is countable instead of
spread across two features' prose.

**Nothing here is performed.** Every box is unchecked, and that is the accurate state as of
2026-09-21. The constitution accepts "verified" and "not verified"; it does not accept silence.

**Why a ledger at all.** Constitution IV requires the adopt/unadopt chain to be verified against
the real dispatch path — "it compiles" and "the unit test passes" are not evidence. That check is
**deferred by decision**, and a deferral recorded only in prose becomes an implied "later" and
then a PR description that reads as though it were done.

---

## 1. Feature 001 T050 — the operator outcome table (SC-003)

- [ ] **Not performed.**

**Do**: on the controller, work through all six rows of `specs/001-network-map-object-adoption/quickstart.md`
§3 from the frontend settings view (`cuems-frontend`'s `settings.component.ts`,
`confirmAddNode`/`confirmRemoveNode`): adopt an online node, adopt an already-adopted node, adopt
an offline node, adopt an unknown uuid, unadopt a node, unadopt an unknown uuid.

**Proves**: the `{'OK': bool, 'error'?: str}` contract still reaches the operator's button, and
**the map on disk changes immediately**. `NodeIndex.adopt` mutates without persisting, so a
dropped save looks correct in the UI and is lost on the next restart.

**Why the suite cannot**: the dispatch is mocked; no test drives the Angular component.

## 2. Feature 001 T051 — discovery across the rename (SC-006)

- [ ] **Not performed.**

**Do**: with both halves deployed (`cuems-nodeconf` 0.1.0-8 and `cuems-common` 1.3.0-23), confirm
a controller and a node discover each other; then deliberately pair a renamed daemon with an
un-renamed one and confirm it does **not** silently mis-role.

**Proves**: the `node_role` TXT cutover works on real mDNS, and the half-renamed state fails
loudly rather than discovering nothing.

**Why the suite cannot**: Avahi is characterized against mock `ServiceInfo` objects; nothing
exercises real mDNS, D-Bus or multi-node discovery. The packaging half (001's T047) **was**
demonstrated with real `.deb`s — that is the relationship gate, not the discovery gate, and does
not stand in for this.

## 3. Feature 002 — the operator chain against the kept document (FR-006, constitution IV)

- [ ] **Not performed. Deferred by decision, 2026-09-21.**

**Do**: on the controller, adopt and unadopt through the UI against a daemon running this
feature, and confirm the map on disk carries the change immediately.

**Proves**: keeping one document for the life of the process, and refilling it from the index,
did not change what the operator sees or what reaches disk. This is the specific risk the design
introduces: a refresh that serialised a stale document would silently undo an adoption.

**Why the suite cannot**: `tests/test_network_map.py::TestAnAdoptionIsNotLostToTheNextRefresh`
pins the seam, but through the daemon's own methods, not the operator's button.

**If it fails**: suspect `_network_map_document()` refilling — the index is the source of truth,
and `node_list` must be overwritten in full on every call.

## 4. Feature 002 — a genuine fresh node (FR-004, FR-005, SC-005)

- [ ] **Not performed.**

**Do**: install the package on a node whose `/etc/cuems/network_map.xml` is the shipped empty
conffile, and watch the first boot: the daemon starts (no `TypeError`, no restart loop), writes
itself into the map, and leaves the file **`0644`** so the `User=cuems` engine can read it.
Check the engine starts afterwards.

**Proves**: the path every fresh install takes, end to end, including the upstream fix
(`cuems-utils` `e363d03`) being present in the build that actually shipped — which no version pin
can express, since the fix landed inside `0.1.0rc16`.

**Why the suite cannot**: it was exercised in a temporary directory on a development checkout.
That is evidence for the code path, not for a node, and it cannot see which library build a
packaged host installed.

---

## Related records

- Feature 002's [evidence/verification-record.md](../evidence/verification-record.md) — what *was* verified.
- Feature 001's `specs/001-network-map-object-adoption/evidence/verification-record.md` — same, for that feature; it links here for the outstanding items.
- `specs/001-network-map-object-adoption/tasks.md` T050/T051 remain unticked, deliberately, and are the same debt as entries 1 and 2 above. Tick them in both places, or neither.
