<!-- REPO-ORIGINAL — not vendored from cuems-utils.
     Written 2026-09-07 in cuems-nodeconf during feature 001's preparation, after
     deleting set_master_always_adopted's is_first_run branch. Line numbers measured
     against feat/xml-refactor with that deletion applied (CuemsNodeConf.py = 792 lines).
     Re-measure before relying on any coordinate here. -->

# "First run" in `cuems-nodeconf` — three signals, one word

## Why this file exists

Feature 001 deleted a first-run branch. Establishing that the deletion was safe took
tracing three *different* things this repository calls "first run", only one of which
the deleted code was actually about. That trace is worth keeping: the next person who
needs first-boot behaviour will otherwise re-derive it, and the cheapest wrong answer
is to reach for whichever of the three signals is nearest to hand.

Nothing here is a decision about future work. It is the map of what exists, what each
signal can honestly answer, and which shapes are available if a real first-boot
requirement appears.

---

## The three signals

| | Signal | Actually means | Scope |
|---|---|---|---|
| **1** | `self.is_first_run` | no `/etc/cuems/network_map.xml` on disk **at the moment `run()` started** | this process, this host |
| **2** | `NodeRole.firstrun` | this node has not been assigned a role yet | the cluster, over the wire |
| **3** | `check_first_run()` | "am *I* currently advertising the firstrun role?" | this host — **and nothing calls it** |

They are not interchangeable, and none of them means "this node has never been
configured".

### 1. `self.is_first_run` — a filesystem fact with a boot-shaped lifetime

```python
:176   self.is_first_run = not os.path.isfile(self.map_path)
:177   if not self.is_first_run: ...read_network_map()... else: ...NodeIndex()...
```

Computed **once**, in `run()`, before discovery has produced anything. Never
recomputed, never reset — including after `refresh_network_map` writes the very file
whose absence defined it. So from the first write onward the flag is *false as a
statement about the world* and still `True` as a variable, for the rest of the
process's life.

That gap is harmless while its only consumer is `:177`, which reads it immediately
at the point it is computed. It is **not** harmless for anything the resident loop
touches — see "What was deleted".

**What it can honestly answer:** "should `run()` load a map from disk, or start
empty?" Nothing else, and only at `:177`.

### 2. `NodeRole.firstrun` — the real cluster-visible signal

An enum member of `cuemsutils.tools.NodeList.NodeRole` (`controller`, `node`,
`firstrun`), carried in the Avahi TXT record and persisted in `network_map.xml`.
This is the authoritative "not yet assigned" signal, and it is the one that is
visible to other nodes.

Read at:

- `:203` — if the local node advertises `firstrun`, either resume the controller role
  (`_should_resume_master()`, `:377`) or run the election (`set_node_role()`, `:396`)
- `:225`, `:230`, `:233` — wait up to 30 s for other `firstrun` nodes to resolve
  before the first map pass, so an election settles before anything is written
- `CuemsAvahiListener` / `AvahiTool` — translated in from the TXT record

Published by the `cuems.service.firstrun` Avahi template. Note this is **role**
state, not **boot** state: a node that has been running for a week and has never been
assigned a role is still `firstrun`, and a node on its very first boot that resumes a
controller role never is.

**What it can honestly answer:** "has this node been given a role yet?" — for any
node, from any node.

### 3. `check_first_run()` — dead code

```python
:641   def check_first_run(self):
           for node in self.listener.nodes.by_role(NodeRole.firstrun):
               if node.get('ip') == self.ip:
                   return True
           return False
```

**No callers anywhere in the package.** It answers "is my own IP among the
discovered firstrun nodes", which `:203`'s `self.node['node_role'] == NodeRole.firstrun`
already answers more directly and without an IP comparison.

Left in place deliberately: it belongs to row 3 (Avahi orchestration) of the
atomization basis, and D23 puts rows other than 5 outside feature 001's scope.
Whoever executes row 3 should delete it or wire it, and should not assume from its
existence that a first-run check is expected there.

---

## What was deleted, and the proof it was safe

`set_master_always_adopted` (`:508`) carried:

```python
if self.is_first_run:
    for mac, node in self.network_map.items():
        if node.get('node_role') != NodeRole.controller:
            node['adopted'] = False
```

**On the run it was written for it did nothing.** Every step is checkable:

- `is_first_run` is true only when no map file exists, so no adoption can be loaded
  from disk.
- With an empty map, `merge_discovered_nodes` takes its else-branch for every
  discovered node and sets `adopted = False` (`:498`).
- `CuemsAvahiListener` constructs every node with `adopted=False` hardcoded, in both
  `add_service` and `update_service`.
- `set_master_always_adopted` then sets `True` for controllers only — exactly the set
  the clear skipped.
- Nothing between the map's creation (`:180`) and the first `refresh_network_map`
  (`:237`) writes `adopted`. `check_nodes()` is logging only; `_should_resume_master`
  and `set_node_role` touch `self.node` and the OS, never the map.

So by the time the branch ran, every non-controller was already `False`.

**Its one live effect was a defect.** The daemon used to run a single pass and exit —
the Phase-1 re-enable made it resident (`_run_worker_loop`, `:266`), which calls
`refresh_network_map` every Avahi event or every 30 s. With `is_first_run` never
reset, a first-boot controller behaved like this:

1. operator adopts a node in `cuems-frontend`'s settings component
2. `nodelist_modify` → `engine_callback` → `adopt_node` sets `adopted=True`, writes,
   and answers `{'OK': True}`
3. next worker tick: `set_master_always_adopted` clears it back to `False` and rewrites
4. the adoption is gone within 30 s, silently, after the UI was told it succeeded

The branch was a one-shot policy that outlived the one shot.

**It also settles an open item upstream.** `cuems-utils`' `NodeIndex.set_controller_always_adopted()`
takes no first-run parameter, which feature 008 recorded as *"Not ported ... Left for
009 to reconcile"* (`05-network-map-api.md`). There is nothing to reconcile: the
omission was correct.

---

## The shape any future first-run logic has to fit

This daemon runs under `systemd` as `Type=notify`, `NotifyAccess=main`,
`TimeoutStartSec=60` (unit shipped by `cuems-common`,
`etc/systemd/system/cuems-nodeconf.service`). Two consequences constrain where
boot-phase logic can go:

- **`run()` is the pre-READY phase.** Everything from `:163` to `notify_systemd()`
  at `:244` runs inside the 60 s start window, and `run()` already commits up to 5 s
  (controller settle, `:221`) plus up to 30 s (waiting for other `firstrun` nodes,
  `:230`) — over half the budget before anything else. `:167`, `:194` and `:200`
  `sys.exit(-1)` on failure, so work added here **fails the unit** rather than
  degrading it.
- **`start()` is not a second phase.** It is `set_comms()` then `run()` (`:102`).
  There is no "initialise, then start" split to hang one-shot work on; the only
  boundary that exists is `notify_systemd()` / `_run_worker_loop()`.
- **The map is empty for most of `run()`.** It is not populated until
  `merge_discovered_nodes` inside the first `refresh_network_map` at `:237`. Any
  policy that inspects node state has to run after that point, not next to where
  `is_first_run` is computed.

---

## Options, if genuine first-boot behaviour is ever needed

Ordered by how well each survives the daemon being resident and restartable. Pick
by what the requirement actually asks, not by what is nearest.

**A. Ask the map, not a flag.** Most "is this a first run" questions are really
questions about content — "does the map contain any adopted non-controller?",
"has any node ever been adopted?". Answering from the data is idempotent, survives
restarts, needs no extra state, and cannot go stale. **Prefer this.** It is the only
option with no lifetime to get wrong.

**B. Use the role, if the question is about assignment.** "Has this node been given a
role?" is `NodeRole.firstrun`, already authoritative, already on the wire, already
cluster-visible. Do not rebuild it as a local boolean.

**C. A persistent marker file, if the question is genuinely "has this host ever
bootstrapped?".** Something like `/var/lib/cuems/nodeconf.bootstrapped`, written after
the first successful map write. Survives restarts and distinguishes "never
bootstrapped" from "no map at this instant" — which `is_first_run` cannot. **Cost:**
this daemon runs as root, so a new file other services might read is a permissions
decision under constitution principle I, and it is a second marker-file mechanism
alongside `master.lock`. Justify it before adding it.

**D. A consume-and-reset in-memory flag, for genuinely per-process concerns only.**
Set it, use it once, clear it — `self.is_first_run = False` after its single consumer
runs. Cheap and correct *within one process*, but a restart before the first write
re-arms it, so it must never gate anything whose effect is persistent. This is the
shape the deleted branch should have had if it had needed to exist at all.

## What not to do

- **Do not put boot-phase policy inside a function the resident loop calls.** That is
  precisely how the deleted branch became a bug: correct once, harmful forever after.
- **Do not add work to `run()` before `notify_systemd()`** without accounting for the
  60 s budget that already has ~35 s committed to it.
- **Do not read `is_first_run` anywhere except `:177`.** It is a snapshot of a
  filesystem fact taken before discovery, and it goes stale the moment the daemon
  writes its first map. If you need it later in the process, you need option A, C or D
  instead.
- **Do not conflate the three signals.** A node can be `firstrun` on its thousandth
  boot, and can have `is_first_run == True` while resuming a controller role it has
  held for months.
