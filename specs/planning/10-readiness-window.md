<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Feature brief — the start-up readiness window, and the startup-analysis backlog

**Written** 2026-09-28, measured against `feat/xml-refactor` @ `2e2ae40`
(`cuemsnodeconf/CuemsNodeConf.py` 806 lines, 20 test files, suite 119 passed).

**Written for** whoever picks this up on a fresh checkout, on any machine, with no memory of how it
got here. **This file is self-contained**: everything the flow needs is in this repository, which is
the promise [`README.md`](README.md) makes for the rest of this bundle and which did not hold for
this item until now. The `cuems-utils` checkout is useful but **not required**.

**It names a new feature: `003-startup-readiness`.** Numbering follows `001-network-map-object-adoption`
and `002-public-network-map-path`.

**Status**: spec, plan and tasks written 2026-09-28 — see `specs/003-startup-readiness/`. (Was: brief only.) Two of the three work items below are
already measured and need no research; the third is a backlog that needed researching before it could
be scoped, and §5 is that research.

---

## 0. Why this is a feature and not a patch

The code change at the centre of this is about **eight lines**. What makes it a feature is the
decision surface, and this repository's own constitution says so in four places:

| Gate | Where | What it demands |
|---|---|---|
| **Principle IV** — RPC responses are a contract with a live UI | `.specify/memory/constitution.md` | *"Any change to this chain MUST be verified end to end against the real dispatch path. 'It compiles' and 'the unit test passes' are not evidence that the operator's button still works."* This **is** the `nodelist_modify → engine_callback → adopt/unadopt` chain |
| **Principle VI** — boot ordering is product behaviour | same | *"Startup order … MUST be reasoned about explicitly in any change that touches lifecycle, threading or IPC. **A change that is correct only when it wins or only when it loses a race is not correct.**"* This is a boot race |
| **Testing gate** | same | *"any change to discovery, role election, the identity chain, OS network reconfiguration, or boot/shutdown ordering MUST additionally state how it was verified on real hardware, or state plainly that it was not. Both are acceptable answers; silence is not."* |
| **Governance** | same | *"Every feature plan MUST include a constitution check naming which principles bear on it and how they are satisfied."* A constitution check lives in a plan |

Plus a decision that is **not this repository's alone** (§3), and a packaging consequence that makes
it a coordinated release event (§4).

---

## 1. The defect — a spurious "Node not found" during start-up

**Measured, and reproducible by reading:**

```
__init__      :66   self.network_map = NodeIndex()      # EMPTY
              :72   self._document   = None
start()       :130  self.set_comms()                    # the NNG responder goes live
              :131  self.run()
run()         :192    self.get_ips()                    # TimeoutLoop(timeout=10, interval=1) at :428
              :209    self._seed_empty_map()            # only when /etc/cuems/network_map.xml is absent
              :212    self.read_network_map()           # <-- index and document finally populated
```

`set_comms()` starts the responder **before** `run()` installs the map. So for as long as
`get_ips()` takes — up to **10 seconds**, longer on a slow or renegotiating interface — an
`adopt`/`unadopt` arriving over `/tmp/nodeconf.ipc` reaches `adopt_node` with an **empty**
`NodeIndex`:

- `self.network_map.adopt(uuid)` iterates nothing and returns `False`
- `self._find_node(uuid)` returns `None`
- the daemon answers `{'OK': False, 'error': f'Node {node_uuid} not found'}`

A **confident, specific, wrong** answer about a node that is present and adoptable. Nothing logs that
anything is amiss beyond a warning that reads exactly like a genuine missing node.

### What is already fixed, and must not be re-fixed

Feature 002 closed the **crash** variant of this same race, deliberately and with the cause named.
`read_network_map` carries:

```python
# Keep the document BEFORE installing the index, not after. set_comms()
# starts the IPC listener before run(), so an adopt arriving between
# these two lines would mutate a populated index and then try to save
# through a document that is not there yet (constitution VI).
self._document = manager.network_map
self.network_map = self._index_from_document(manager.network_map)
```

So an adopt landing between those two lines no longer raises `RuntimeError`. **The wrong-answer
variant is what remains**, and it is the operator-visible one.

### Provenance

First recorded on `feat/nodelist-modify-hardening` (`61b759f`, Ion Reguera, 2026-09-04) as *"the
startup map load is the third writer, and it was unguarded"* — that branch counted **three** writers
where the lock's own comment had claimed two. That branch is **unmerged**, 47 commits behind, and
absent from this branch's candidate tag `6c0cca7`. Two of its four findings are superseded and one
does not reproduce; see §6.

---

## 2. Why the fix is a readiness flag and **not** a lock

`b53ee5f` on the same branch added a `threading.RLock` (`_map_lock`) across both write paths. **It
would not fix this**, and the reason is worth stating so it is not proposed again:

> A mutex serialises the two threads. It does not make an empty index any less empty. An adopt that
> waits politely for the lock and *then* reads an unpopulated `NodeIndex` still answers "not found".

The shape that does work:

- a `self._ready = False` in `__init__`
- set `True` at the end of `read_network_map()` — after **both** `_document` and `network_map` are
  installed, so it cannot advertise a half-built state
- guarded in `engine_callback`, answering a **distinguishable** refusal until then

**It must stay inside the existing response contract.** Principle IV: *"The response shape
`{'OK': bool, 'error'?: str}` is a contract. It MUST NOT change shape, drop its error strings, or
silently narrow which actions produce a reply. Every well-formed request over `/tmp/nodeconf.ipc`
MUST be answered."* A refusal of the form
`{'OK': False, 'error': 'nodeconf is still starting up'}` satisfies that; a new key, a silent
return, or a raised exception does not.

---

## 3. The clarification the spec must force — and it crosses four repositories

**What should the engine and the UI *do* with "not ready"?** This is open, it is not this
repository's to settle alone, and it is the single reason this cannot ship as a patch.

The chain is `cuems-frontend` → (WS :9092) → `cuems-editor` → (NNG `/tmp/editor.ipc`) →
`cuems-engine` → (NNG `/tmp/nodeconf.ipc`) → **here**. Three candidate answers, each with a cost:

| Option | Cost |
|---|---|
| The engine **retries** briefly | Contradicts `cuems-engine`'s `cf5c4ad`, which deliberately made refusals **instant** (measured 0.00 s against ~15 s) because a queued second click hit the editor's own 25 s timeout and read *"Engine did not respond"* |
| The UI shows **"starting up, try again"** | Needs a new affordance in `cuems-frontend`, which has no adoption-tier UI work scheduled. Different from an error |
| Treat it as **unavailable**, like a missing socket | Simplest, and tells the operator to `systemctl enable --now cuems-nodeconf` for a daemon that is *already running* — actively misleading |

### The interaction that makes this urgent, and it is counter-intuitive

`cuems-engine`'s `cf5c4ad` — *"refuse instantly when nodeconf is not running"* — decides availability
by **checking that `/tmp/nodeconf.ipc` exists**. That socket is created by `set_comms()`, at `:130`,
**before the window opens**.

So during start-up the engine's probe reports nodeconf **available**, forwards the adopt, and relays
this daemon's wrong answer to the operator. **Before `cf5c4ad` they got a stall; now they get a
definite "Node not found" for a node that is present.**

`cf5c4ad` is **correct and must not be reverted** — the 15 s stall on a fleet where this daemon ships
disabled was the worse failure, and it was measured on real hardware. What is wrong is the *signal it
trusts*. Fixing that is this side's job: a readiness answer is what lets the engine distinguish
"not installed" from "not yet up".

**Two prohibitions already recorded in the consumer repositories**, so the spec should not
re-litigate them:

- `cuems-engine` must not deepen its dependency on socket-existence-as-readiness
  (`specs/planning/xml-refactor/04-findings-new-to-this-pass.md` F2a there)
- `cuems-editor` must not add client-side retry or interpretation to compensate for the wrong string
  (`specs/planning/xml-refactor/00-runnable-flow.md` §0a there)

---

## 4. Packaging — this one re-cuts the candidate

`cuemsnodeconf/CuemsNodeConf.py` **is** packaged (`pyproject.toml`:
`[[tool.poetry.packages]] include = "cuemsnodeconf"`). So unlike T093/T097, which landed in
`tests/` and `CLAUDE.md` and left the tag alone, this changes packaged content and therefore
**re-cuts `xml-refactor-merge-candidate`** — currently `6c0cca7`.

By the shared convention the tag moves **only** for packaged-content changes, and **a re-cut is
announced to the other flows**. `cuems-common` and `cuems-power-bridge` hold the counterpart tags.
Budget a release-coordination step; do not discover it at merge.

---

## 5. `STARTUP_ANALYSIS.md` — relocate it, and what its twelve findings are actually worth

### 5.1 The relocation is work for this feature

The convention — planning and analysis documents live in `specs/planning/`, not `docs/` and not the
repository root — is stated in `cuems-utils`' `CLAUDE.md` rather than in this repository's, but this
repository already **follows** it everywhere else: the whole bundle you are reading sits under
`specs/planning/`.

**And `STARTUP_ANALYSIS.md` is not alone up there.** Scoping this as "move one file" would leave three
siblings behind, which is how the item comes back. Measured 2026-09-28 — four non-standard root-level
markdown files, all four named together in `specs/001-network-map-object-adoption/tasks.md:133` as
*"the root-level historical analyses"*:

| File | Lines | Last touched | Disposition |
|---|---|---|---|
| `STARTUP_ANALYSIS.md` | 190 | 2026-09-17 | **relocate + annotate** — §5.2 shows 9 of 12 findings closed, but the five runtime issues are live, so it is not spent |
| `BUGFIX_NETWORK_MAP.md` | 129 | 2026-06-11 | **delete** |
| `BUGFIX_COMPLETE.md` | 91 | 2026-06-11 | **delete** |
| `DEPLOYMENT_STEPS.md` | 104 | 2026-06-11 | **delete** |

`CLAUDE.md` and `README.md` are legitimately root-level and stay.

**Why the three deletions are safe, measured rather than assumed.** All three document one bug —
`'NoneType' object has no attribute 'tag'` when writing `network_map.xml` — and all three describe the
fix as *"enhanced `write_network_map()`"*. That method **no longer exists**:

```
$ grep -nE 'write_network_map|ElementTree|getroot' cuemsnodeconf/*.py
(no matches)
```

Features 001 and 002 replaced the entire write path with `CuemsNetworkMapType.save()`, and the
adjacent empty-document decode behaviour was reported upstream and fixed in `cuemsutils` (its T085–T090,
inside `0.1.0rc16`). So these three describe a fix to code that is gone, superseding a defect that is
also gone. That is exactly the case the ecosystem's deletion policy names:

> a planning document whose content has been fully implemented — and whose resolution is captured
> elsewhere — MUST be **deleted**, not left behind as stale, redundant history. Git history preserves
> it.

**One reference exists, and it is deliberately not rewritten.**
`specs/001-network-map-object-adoption/tasks.md:133` names all four files while enumerating exceptions
to a `grep` for the retired TXT key. A landed feature's spec is a frozen historical record: per the
ecosystem convention, its cross-references to a file *as it was named and located at the time* are
**not** retroactively rewritten when that file later moves or goes — no more than a past commit message
would be. Leave it. An earlier draft of this brief claimed nothing referenced these files at all; that
was wrong, and finding the reference is what turned up the other three.

It is also **undated in its own title** and carries exactly one dated update note, on finding #7.
Whatever survives relocation must say when it was measured, because §5.2 shows how much of it aged.

### 5.2 Research: all twelve findings re-measured 2026-09-28

The document was written against a tree that predates features 001 and 002. **Nine of its twelve
findings are already fixed**, one is moot, one is half-closed and one is a standing concern. Measured
per finding, not transcribed:

| # | Finding | Status 2026-09-28 | Evidence |
|---|---|---|---|
| 1 | `update_service()` can use an unbound `ip` | **FIXED** | `CuemsAvahiListener.py:117` `ip = None`; `:135-136` `if not ip: ip = addresses[0]` |
| 2 | `stop_requested = True` missing `self.` | **FIXED** | `communicate.py:54` `self.stop_requested = True` |
| 3 | `self_controller_ip = None` typo | **FIXED** | `CuemsNodeConf.py:425` `self.controller_ip = None`; no `self_controller_ip` in the tree |
| 4 | `get_ips()` `TimeoutError` caught but execution continues | **FIXED, at all three call sites** | `:192-195` `sys.exit(-1)` plus an `self.ip is None` guard; `:396-399` warn-and-continue in the resident loop; `:509-512` re-raise after a network change |
| 5 | `retreive_local_node()` loop logic confusing | **FIXED** | `:678-687` returns on match, raises `TimeoutError` after the loop. Explicit |
| 6 | listener started, local node sought immediately | **FIXED** | `:221` interposes `wait_for_local_service_registration()` (defined `:662`, `TimeoutLoop(timeout=5, interval=0.2)`) between `start_avahi_listener()` and `retreive_local_node()`, with its own timeout and `sys.exit(-1)` — exactly the retry step the finding asked for |
| 7 | TXT property read by position | **FIXED** — the document already says so | All access is by name: `info.properties[b"node_role"]`, `[b"uuid"]` (`CuemsAvahiListener.py:95,102,148,155`; `AvahiTool.py:79,81,93,97`) |
| 8 | `add_service()` lacks validation | **FIXED** | `:59-71` — `ip = None`, `info is None` check, empty-`addresses` check |
| 9 | `update_service()` lacks validation | **FIXED** | `:117-127`, same three guards |
| 10 | `time.sleep(5)` hardcoded *"without justification"* | **HALF-CLOSED** | Still hardcoded at `:252`, but the comment is now a real justification — *"If I am master, give slaves a moment to appear before the first pass."* The finding **as written** is answered; the improvement (configurable or event-based) is open |
| 11 | `while self.listener.nodes.firstruns:` has no timeout | **MOOT** | `firstruns` **does not exist** anywhere in the codebase. It named the retired masters/slaves/firstruns vocabulary; feature 007's `NodeIndex` explicitly did not migrate it |
| 12 | network/subprocess/dbus operations lack error handling | **PARTIALLY, and unfalsifiable as stated** | Broad by construction — no single site to check. `dbus.exceptions.DBusException` is caught at `:789`; map-write failure is tracked and retried through `_map_write_pending` (8 sites). Not a finding a feature can close; **retire it or split it into named sites** |

**The five "Potential Runtime Issues" are architectural and mostly open:**

| | Issue | Status |
|---|---|---|
| 1 | interface timing; *"the 10-second timeout may not be sufficient on slow systems"* | **OPEN.** Still `TimeoutLoop(timeout=10, interval=1)` at `:428`. **Directly relevant to this feature** — it is the same 10 s that bounds §1's window |
| 2 | no check that avahi-daemon is running | **OPEN.** No pre-flight health check. There is a recovery path (`StartUnit('avahi-daemon.service')` at `:779`) and `AliasPublisher.py:90` handles a stale group handle after a restart, but nothing validates up front |
| 3 | `/etc/cuems/network_map.xml` write permissions, no error handling | **LARGELY ADDRESSED** by features 001/002 — `_map_write_pending` defers a failed write to the next refresh, and the library preserves the target's mode (a defect this repository reported upstream) |
| 4 | no validation that DBus is available | **PARTIAL.** Errors are caught, availability is not checked. Note the suite **stubs** `dbus` in `tests/conftest.py`, so nothing here exercises it — the constitution says so |
| 5 | simultaneous boot → several nodes elect themselves master | **OPEN, and the closest neighbour to this feature.** Mitigated by `_should_resume_master()` and the `:252` sleep, neither of which is a real election. **Principle VI territory** |

### 5.3 What this means for scoping

- **Do not budget work for findings 1–9.** They are done. A spec that lists them will be rejected at
  review for the same reason the constitution warns about: *"line numbers, occurrence counts and
  version pins recorded in planning documents MUST be re-measured against the live tree before being
  relied upon."*
- **Runtime issues 1 and 5 are genuinely adjacent** to §1 and both sit under Principle VI. Deciding
  whether they are in or out of `003` is a scoping question for `/speckit.clarify`, not an
  assumption. Taking issue 1 in is cheap and coherent — it bounds the very window §1 is about.
  Issue 5 is a much larger piece (a real election protocol) and probably wants its own feature.
- **Findings 10, and runtime 2 and 4, are small and independent.** Candidates for this feature's
  polish phase or a separate maintenance pass. State which.
- **Finding 12 should be retired or split.** As written it cannot be closed, which makes it permanent
  noise in any backlog that inherits it.

### 5.4 Two options for the document itself

1. **Relocate and annotate** — `git mv` to `specs/planning/11-startup-analysis.md`, add a status
   column from §5.2, and keep it as the dated historical record.
2. **Fold and delete** — carry the three live items into this brief and delete the file, per the
   ecosystem's deletion policy: *a planning document whose content has been fully implemented, and
   whose resolution is captured elsewhere, MUST be deleted rather than left behind as stale,
   redundant history. Git history preserves it.*

**Option 1 is recommended**, narrowly: nine of twelve findings are closed but the *five runtime
issues* are not, so the document is not yet spent — and its startup-sequence map (§"Startup Flow
Simulation") is the only written narrative of the boot order this repository has, which Principle VI
demands be reasoned about explicitly. Deleting it would remove the very artefact `003` needs. Revisit
deletion once runtime issues 1 and 5 are resolved.

---

## 6. For context — the rest of the branch this came from

Do **not** merge `feat/nodelist-modify-hardening`. It is 47 commits behind, predates the
`NodeList` refactor, and `21c2875` recorded that merging it auto-merges its tests into a file whose
imports no longer define `CuemsNodeDict`. Its four findings, measured:

| | Finding | Verdict |
|---|---|---|
| A | `engine_callback` answers only `nodelist_modify`; the engine stalls 15 s | **superseded** — ported verbatim as `21c2875` |
| B | two writers share the temp path `f"{map_path}.tmp.{os.getpid()}"` → truncated map, cluster will not boot | **superseded by construction** — this daemon renders no temp file now; the library's `write_tree` allocates a unique name per call. Measured upstream: 6 distinct temp names over 6 saves. Worst case degrades to last-writer-wins with a **complete, valid** document |
| C1 | an adoption lost between the two threads | **does not reproduce** — 0 of 60 concurrent trials. The node dictionaries are aliased end to end, so there is no private copy to lose the write into. Now pinned on both sides: `tests/test_node_aliasing.py` here, `tests/contract/test_node_aliasing.py` in `cuems-utils` |
| C2 | **this brief** | **open** |
| D | `CLAUDE.md`'s `<online>` cadence was false | **closed** 2026-09-28 — two lines, not one |

---

## 7. Scope, and exit criteria

**Three work items.** Two are measured and ready; the third is §5's decision.

1. **The readiness refusal** (§1–§3) — the flag, the guard, the distinguishable error, and the
   cross-repo decision recorded.
2. **The four root-level analyses resolved** (§5.1): `STARTUP_ANALYSIS.md` relocated to
   `specs/planning/11-startup-analysis.md` and annotated with §5.2's status per finding;
   `BUGFIX_NETWORK_MAP.md`, `BUGFIX_COMPLETE.md` and `DEPLOYMENT_STEPS.md` deleted, since all three
   document a fix to a method that no longer exists.
3. **The live remainder of that backlog triaged into or out of this feature** (§5.3) — explicitly,
   per item, not by silence.

**Exit criteria, measured:**

| | Criterion |
|---|---|
| 1 | An adopt arriving before `read_network_map()` completes answers a **distinguishable** refusal, never *"Node not found"*. Tested by exercising the window, not by inspection |
| 2 | The response still matches `{'OK': bool, 'error'?: str}` — no new key, no silent return, no raised exception (Principle IV) |
| 3 | **Every** well-formed request is still answered, including during the window. `tests/test_engine_callback.py` stays green |
| 4 | The flag is set only after **both** `_document` and `network_map` are installed — a half-built state is never advertised as ready |
| 5 | Verified **end to end against the real dispatch path** (Principle IV, which rules out "the unit test passes" as evidence), or recorded plainly as not verified |
| 6 | The start-up order reasoned about **explicitly** in the plan, and the change correct whether it wins or loses the race (Principle VI) |
| 7 | Hardware verification **stated** — performed or plainly not. Silence is not an acceptable third state |
| 8 | `pytest` green with no skips introduced, and adopt/unadopt coverage **not reduced** |
| 9 | The vendored yardstick at `specs/planning/yardstick/` still passes **unchanged** and byte-identical to `cuems-utils`' copy |
| 10 | No non-standard analysis document left at the repository root — one relocated with a status per finding, three deleted. `ls *.md` returns `CLAUDE.md` and `README.md` only |
| 11 | The candidate tag **re-cut** and the re-cut **announced** to the other flows (§4) |

---

## 8. Traps

**A mutex is not the fix.** §2. It will be proposed, because the branch this came from had one.

**`cuems-engine`'s `cf5c4ad` is correct — do not revert it.** §3. Its readiness *signal* is wrong,
not its behaviour.

**Nine of `STARTUP_ANALYSIS.md`'s twelve findings are already fixed.** §5.2. Its line numbers are
from 2026-09-17 and every one of them has moved.

**The root-level cleanup is four files, not one.** §5.1. Scoping it as "move `STARTUP_ANALYSIS.md`"
leaves three superseded siblings in place, and they are named together in feature 001's task list —
which is where the fourth was found.

**Measure, do not transcribe.** The constitution's own words. This brief's coordinates were measured
on 2026-09-28 against `2e2ae40`; re-measure before relying on them.

**The suite proves nothing about a node.** `dbus` and `systemd.daemon` are stubbed in
`tests/conftest.py`; Avahi is characterized against mock `ServiceInfo` objects. Nothing exercises
real mDNS, D-Bus, systemd or multi-node discovery — which is exactly why criteria 5 and 7 exist.

**Commits are GPG-signed.** On `gpg failed to sign`, retry — never `--no-gpg-sign`.

---

## 9. Inputs from `cuems-utils` features 010 and 011 (added 2026-09-28)

**Added from the `cuems-utils` side**, so that `/speckit.specify` for `003-startup-readiness` sees
every requirement that lands on this daemon's start-up sequence in one place. Measured against
`cuems-utils` `011-etc-cuems-first-install` (local branch, rebased onto `feat/xml-refactor` `0ba239b`)
and this repository at `a4ee51b`. **The three decisions at the end were taken by the maintainer on
2026-09-28** (all three as recommended); the items below that once said *pending* now state the
decision.

### 9.1 From feature 010 — the carried items this feature owns (its `tasks.md` T093–T098)

| 010 task | What this feature must deliver | Status |
|---|---|---|
| T093 | this repository's half of the aliasing contract (links 1 and 2) | **done** — `tests/test_node_aliasing.py`, `2e2ae40` |
| T094 | C2: the readiness flag and the distinguishable refusal (§1–§3 above) | open — **this feature's core** |
| T095 | the `cf5c4ad` readiness-contract gap recorded (their guide) | theirs; input to §3's decision |
| T096 | flows 01/02 did not compensate for the wrong string | gate on the engine/editor flows; this feature's spec restates the two prohibitions |
| T097 | `CLAUDE.md`'s `<online>` cadence | **done** — `2e2ae40` |
| T098 | why the cadence line is a release item (their guide) | theirs |
| T025 | the **over-the-wire** discovery check, two hosts | in this repository's hardware ledger, `specs/002-public-network-map-path/checklists/hardware-verification.md` §2 — still "Not performed" |

### 9.2 From feature 011 — the Avahi record becomes this daemon's, derived from `settings.xml`

`cuems-utils` feature 011 (`/etc/cuems` first install) decided on 2026-09-28, with the maintainer,
that **`cuems-nodeconf` is the sole writer of `/etc/avahi/services/cuems.service` and derives it from
`/etc/cuems/settings.xml`** (its research R7, shape B of R7a; contract
`specs/011-etc-cuems-first-install/contracts/cuems-common-handover.md` §4a). The measured reasons:

- Today this daemon copies `/usr/share/cuems/cuems.service.<role>` verbatim, and **learns its own
  uuid from its own announcement** (`retreive_local_node` matches by IP and trusts the TXT `uuid=`).
  So the identity flow runs template → Avahi → nodeconf → map, the reverse of the identity contract,
  and a template that disagrees with `settings.xml` produces the duplicate self that never merges.
- The templates are `cuems-common` package content: every upgrade resets them. They currently carry a
  **production controller's uuid** (`a3811d78-…`), so an unmodified copy announces a real node's identity.
- `cuems-config-node` in `cuems-common` mints its own `uuid1()` — a second minter. 011's handover
  strips it; the templates ship with the sentinel `00000000-0000-0000-0000-000000000000`; the dead
  `sudo cp` rules are retired. `cuems-init-node` (new, `cuems-utils`) becomes the only minter and
  writes `settings.xml`, `network_map.xml` (this node's row) and `default_mappings.xml` at install.

**What this daemon must do** — delivered by **this feature** (D1, decided: the render, the refusal
and the guard are in `003-startup-readiness`'s scope, since it is the same start-up sequence, the same
packaged file and the same re-cut):

1. At start, **before `set_comms()`**: read `uuid`/`mac` from `settings.xml` through the
   `ConfigManager` it already constructs; render the role template into the live record by literal
   substitution of the 36-character sentinel token; write atomically; reload `avahi-daemon` only if
   the bytes changed. Rendering before `set_comms()` matters because of §3: a refusal *after* the
   socket exists reads as "available" to the engine's probe.
2. **Refuse to start** when `settings.xml` is absent or carries the sentinel — log `NOT PROVISIONED`
   (the wording `cuems-init-node --check` uses), exit non-zero, announce nothing, create no socket.
3. Render the same way at every role change (the three template-copy sites:
   `_install_master_service_template`, the node branch of `set_node_role`, the resume path).
4. After discovery, assert the discovered self carries the `settings.xml` uuid; refuse loudly
   otherwise (this repository's own plan `09-self-node-seeding.md` §4 asked for this guard).
5. Seed this node's row through the library primitive **`NodeIndex.ensure(node)`** — added by 011
   inside `0.1.0rc16` (D2, decided), inserting the caller's dict **by reference** per the aliasing
   contract — instead of a daemon-side insert (plan 09 §5 option 1; D22). Until 011 lands, the
   yardstick at `specs/planning/yardstick/` does not know the method; this feature's plan MUST name
   the 011 commit it depends on and MUST NOT add a private equivalent in the meantime. `_seed_empty_map()` stays
   as the fallback for a map that is absent altogether.
6. Consequences 011 records for operators: after `cuems-init-node --force-new-identity` (and after
   feature 012's re-mint) the fix is **restart `cuems-nodeconf`**; `cuems-init-node --check` reads the
   live record and exits 1 while it disagrees, 3 while the source is the sentinel.

**Transition**: the mutual `Breaks` already exist (`cuems-common 1.3.0-23` ↔ `cuems-nodeconf 0.1.0-8`);
no version moves. Inside `0.1.0-8` the version cannot tell a pre-render build from a post-render one
(the T090 caveat) — harmless because nothing ships before the coordinated tag.

**Hardware verification** (011 step 6a, FR-045): unmask, enable and start this daemon on every fleet
node — it is masked at Medina and off elsewhere, and under this design the Avahi record is unmaintained
until it runs — then `cuems-init-node --check` exit 0, again after a reboot, and a second node sees this
one exactly once with the `settings.xml` uuid. D3, decided: recorded as entry **§5** of this
repository's hardware-verification ledger
(`specs/002-public-network-map-path/checklists/hardware-verification.md`), which `cuems-utils`' plan
points at; no second list exists in `cuems-utils`.

### 9.3 Packaging — one re-cut, announced once

Both §1's readiness flag and §9.2's render change `cuemsnodeconf/CuemsNodeConf.py`, packaged content.
Landing them in one feature means **one** re-cut of `6c0cca7` and one announcement (§4), inside the
unreleased `0.1.0-8` entry. `cuems-common`'s `3af31cc` is re-cut by 011's handover at the same time.

### 9.4 Decisions — taken by the maintainer, 2026-09-28

| | Question | Decision |
|---|---|---|
| D1 | Does §9.2's render/refuse/guard work fold into `003-startup-readiness`? | **Yes.** One start-up sequence, one re-cut of `6c0cca7`, one hardware verification |
| D2 | `NodeIndex.ensure` added in `cuems-utils` (011, inside `0.1.0rc16`) and consumed here? | **Yes.** Plan 09 option 1; `cuems-init-node` needs it regardless. No daemon-side insert |
| D3 | The unmask/enable/start hardware task lives in this repository's ledger, §5? | **Yes.** One ledger for every hardware-only check on a node; `cuems-utils` points at it |

**Consequences for the `/speckit.specify` prompt of `003-startup-readiness`**: one scope carrying
§1–§3, §7's exit criteria and §9.2's six items; §3's four-tier decision and §5.3's triage as the
clarifications to force; a dependency on the `cuems-utils` commit that adds `NodeIndex.ensure`,
named in the plan; and the ledger entry §5 written before hardware time is booked.
