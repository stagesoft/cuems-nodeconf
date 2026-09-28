<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Research — feature 003, start-up readiness

**Measured** 2026-09-28 against this repository at `6f31a7a` (`feat/xml-refactor`), `cuems-utils` at
`73daab6` (branch `011-etc-cuems-first-install`, installed editable in `.venv`), `cuems-common` at
`3af31cc` (`feat/xml-refactor`) and `cuems-engine` `cf5c4ad`. Suite at baseline: **119 passed**;
yardstick **15 passed**, byte-identical to `cuems-utils` `tests/contract/test_nodeindex_characterization.py`.

Every item below is a decision with its rationale and the alternatives rejected. Items are numbered
R1–R13; the plan cites them by number.

---

## R1. The readiness flag, and where it lives

**Decision.** `self._ready = False` in `__init__`; set to `True` as the **last statement** of
`read_network_map()`, after both `self._document` and `self.network_map` are assigned; consulted at
the top of the `nodelist_modify` branch of `engine_callback`, which answers
`{'OK': False, 'error': 'nodeconf is still starting up'}` while it is false. The flag is never reset.

**Rationale.** The empty `NodeIndex` from `__init__` is the defect (brief §1): `adopt` iterates
nothing, `_find_node` returns `None`, and the daemon answers "Node … not found" about a node that is
present. A flag set after both halves of the map are installed is the smallest change that cannot
advertise a half-built state (spec FR-002). Only the adopt/unadopt path is gated: unknown, missing and
malformed actions are answered exactly as today (spec Story 1 scenario 2), so the gate cannot narrow
which requests get a reply (constitution IV).

**Rejected.**
- *A mutex across the writers* (`b53ee5f` on `feat/nodelist-modify-hardening`): serialises the threads
  but an adopt that waits for the lock and then reads an empty index still answers "not found".
- *Moving `set_comms()` after `read_network_map()`*: closes the window by not having a socket during it.
  But the engine's probe (`cf5c4ad`) then tells the operator the daemon is *not running* and to enable
  it, for a daemon that is starting — option C's cost from the spec, and the message is the engine's,
  not ours. The spec settled that the socket exists and the daemon answers honestly (Story 1
  scenario 5, decision D). `set_comms()` stays first; only the provisioning refusal (R3) moves ahead of it.
- *A new action for the engine to ask "are you ready?"*: a new key in the contract, and decision D
  needs no consumer change. Not proposed.

**The string.** `nodeconf is still starting up`. Contains neither "not found" nor the uuid, so no
consumer can mistake it for a statement about the node. Pinned by a test that asserts both the
positive (the phrase) and the negative (`'not found' not in error`).

---

## R2. Start-up order, and the race table (constitution VI)

Measured order in `start()` → `run()` today, with the phases this feature adds marked **new**:

| # | Step | Where | Socket exists? | Map loaded? | Answer to an adopt arriving now |
|---|---|---|---|---|---|
| 0 | process starts; **new** — pre-flight logs bus/avahi state (R7) | `run_nodeconf.main`, `start()` | no | no | engine: "not running, enable it" (`cf5c4ad`, unchanged) |
| 1 | **new** — read `settings.xml`; refuse if unprovisioned | `start()` before `set_comms()` | no | no | same as 0 |
| 2 | **new** — render the mDNS service record; reload avahi if changed | `start()` | no | no | same as 0 |
| 3 | `set_comms()` binds `/tmp/nodeconf.ipc`, `chmod 0666` | `start()` | **yes** | no | **new: "nodeconf is still starting up"** |
| 4 | `get_ips()` — up to `TimeoutLoop(timeout=10)` (R7 makes it configurable) | `run()` | yes | no | "still starting up" |
| 5 | `_seed_empty_map()` if the file is absent | `run()` | yes | no | "still starting up" |
| 6 | `read_network_map()`: `_document` assigned | `run()` | yes | half | "still starting up" (flag not yet set) |
| 7 | `read_network_map()`: `network_map` assigned; **`_ready = True`** | `run()` | yes | **yes** | pre-feature behaviour (adopted / already / offline / not found) |
| 8 | zeroconf, listener, wait for own registration, `retreive_local_node` (+ **new** uuid guard, R5) | `run()` | yes | yes | pre-feature |
| 9 | **new** — `ensure(self.node)` seeds the own row (R6) | `run()` | yes | yes | pre-feature; the row now exists |
| 10 | role decision, template render at the role sites (R4), aliases, first pass, `READY=1` | `run()` | yes | yes | pre-feature |

**Both race outcomes are correct.** If the engine sends before step 3 it gets the engine's own
refusal; between 3 and 7 it gets ours; after 7 it gets what it always got. There is no timing at which
the answer is "not found" for a present node. The flag is written once by the main thread and read by
the comms thread; a stale read can only see `False`, which yields the conservative answer.

**An exit during the window.** `get_ips()` timing out exits the process (`sys.exit(-1)`), as today.
The NNG ipc socket file **can survive the process** (`/tmp/nodeconf.ipc` is a filesystem object; the
`CLAUDE.md` recovery recipe removes it by hand). A stale file fools the engine's existence probe on
the next attempt — a pre-existing limitation of `cf5c4ad`'s signal, **out of this feature's scope**
and recorded for the engine flow in the start-up-order contract, not fixed here.

**Verification.** Steps 3–7 are exercised by tests (R8). Step 8–10 and the real dispatch path are
hardware-only (constitution IV, testing gate): ledger entries §5 and the new §6 (R11).

---

## R3. Provisioned identity: source, sentinel, refusal

**Where uuid and MAC come from.** `ConfigManager(config_dir=..., load_all=False)` — the constructor
the daemon already uses in `read_network_map` — runs `ConfigBase.load_base_settings` unconditionally,
so `manager.node_conf['uuid']` and `manager.node_conf['mac']` are available **without loading the
map**. Both fields are schema-required (`settings.xsd:61` for `mac`). No new library surface is
needed and no internal path is touched.

**The sentinel.** `cuems-utils` defines `SENTINEL_UUID = "00000000-0000-0000-0000-000000000000"` and
`SENTINEL_MAC = "000000000000"` in `cuemsutils.xml.seed_values` — an **internal** module
(`cuemsutils.xml` declares `__all__ == []`; constitution: public import paths only). **Decision:** the
daemon carries the two literals as its own module constants, and a test pins them to the values the
011 handover contract records. The sentinel is a wire-level constant shared by contract, like the TXT
key `node_role`; both sides pin it independently. A public re-export from `cuems-utils` would be
welcome and is noted as a follow-up for their flow, **not** a dependency of this one.

**What counts as unprovisioned** (spec FR-011, edge cases):

| Condition | Library behaviour | Daemon answer |
|---|---|---|
| `settings.xml` absent | `FileNotFoundError` (unwrapped `OSError`) | `NOT PROVISIONED: /etc/cuems/settings.xml is absent` |
| unreadable | `PermissionError` | `NOT PROVISIONED: … cannot be read: <errno>` |
| invalid against the schema | `SchemaError` | `NOT PROVISIONED: … does not validate: <element>` |
| uuid **or** mac equals its sentinel | loads fine | `NOT PROVISIONED: settings.xml carries the placeholder identity; run cuems-init-node` |

All four: `Logger.critical`, `sys.exit(-1)`, **before** `set_comms()` — so no socket is created (the
engine keeps saying "not running", which is true) and nothing is announced. Under the unit's
`Restart=on-failure` this cycles five times in 33 s and then settles as `failed` (R12) — the intended
end state for an unprovisioned node. The token
`NOT PROVISIONED` leads every message because `cuems-init-node --check` uses it (011 spec, its
exit-3 case) and an operator grepping the journal for it finds both tools. The library's own
distinction between "no config" and "corrupt config" (its FR-014b) is preserved after the token.

**Rejected.** Treating an absent `settings.xml` as "development checkout, carry on": the maintainer
confirmed the daemon is never standalone (memory), so absence means unprovisioned.

---

## R4. Rendering the mDNS service record

**One helper.** `_render_service_record(role: NodeRole) -> bool` (returns whether the bytes changed):

1. read `/usr/share/cuems/cuems.service.<role.value>` (the templates `cuems-common` ships;
   `TEMPLATES_PATH` already names the directory);
2. **require** the sentinel to appear in the template at least once (the shipped shape has two
   service blocks, so two occurrences). Zero occurrences means a template that carries a real uuid —
   a `cuems-common` older than `1.3.0-23`, which the package `Breaks` already refuses; the daemon
   refuses too (`Logger.critical`, exit) rather than announce someone else's identity. Defence in
   depth against a hand-restored template;
3. `bytes.replace(SENTINEL_UUID, settings_uuid)` — literal substitution, the contract's wording; no
   XML parsing, so the template's formatting is preserved byte for byte;
4. if the live file `/etc/avahi/services/cuems.service` exists and its bytes equal the rendered
   bytes: **return False, touch nothing**;
5. otherwise write atomically — `tempfile.mkstemp` in the same directory, `os.chmod(0o644)`,
   `os.replace` — the discipline `_seed_empty_map` already uses. `0644` because `avahi-daemon` runs as
   the `avahi` user and must read a file root wrote (constitution I);
6. reload `avahi-daemon.service` through the D-Bus systemd manager the daemon already drives
   (`ReloadUnit(...,'fail')` beside the existing `StartUnit`); on `DBusException` log an error and
   continue — the later `wait_for_local_service_registration` timeout bounds a record that is never
   served, and the promotion path already restarts avahi. Return True.

**Which role at start-up?** The start-up render (R2 step 2) must not *change* the role — role
decisions belong to `set_node_role` and the resume path and happen later. So it re-renders the role
the live record already has: parse `node_role=` from the live file's first TXT record; if the file is
absent or carries no recognisable role, use `firstrun` (what provisioning would have placed). The
start-up render therefore only ever corrects the **uuid**, which is the whole point.

**The three sites** (contract §4a's count): `_install_master_service_template` (controller; also the
resume path's only write) and the node branch of `set_node_role` both become one-line calls to the
helper with the role. `shutil.copy2` of a template disappears from the daemon.

**Reload semantics.** `avahi-daemon` re-reads `/etc/avahi/services` on SIGHUP, which is what
`systemctl reload` sends; it also watches the directory with inotify on Linux, so the explicit reload
is belt-and-braces rather than load-bearing. Neither can be verified on this checkout (no avahi here);
ledger §5 steps 4–6 are what prove the record is served. **Stated, not assumed.**

**Rejected.** Regex-replacing *any* `uuid=` value (would silently "fix" a template carrying a real
identity, which is exactly the failure 011 is closing); parsing and re-serialising the XML (changes
bytes the equality check depends on, for no benefit).

---

## R5. The self guard at discovery

**Decision.** `retreive_local_node` matches by IP **and** by `uuid == settings uuid`. A node seen at
our IP with a *different* uuid is logged at WARNING with both values (a stale record still being
served while avahi reloads, or a foreign template) and the loop keeps waiting. On timeout the message
is `Logger.critical` naming both uuids and the remedy (*restart cuems-nodeconf after re-provisioning;
cuems-init-node --check shows the disagreement*), then `sys.exit(-1)`.

**Rationale.** Plan 09 §4 asked for this guard. Matching *only* by IP would adopt the stale record's
uuid as our own on the first pass and build the map around it — the duplicate self that never merges.
Exiting on the *first* non-matching sighting would make the daemon lose the race against avahi's
reload every boot where the record changed (constitution VI: correct only when it wins is not
correct). Waiting for the matching one, bounded by the existing timeout, is correct in both orders.

---

## R6. Seeding the own row through `NodeIndex.ensure`

**The primitive exists.** `NodeIndex.ensure(entry) -> bool` landed in `cuems-utils` at **`73daab6`**
("feat(011): phases 1-2 — hermetic suite, seed values as TOML, NodeIndex.ensure", branch
`011-etc-cuems-first-install`, their task T014). Semantics, from its docstring and body: match by
`uuid`; if absent, insert **the caller's object** (by reference) keyed by `entry["mac"]`; never touch
another row; return whether it inserted. The yardstick file was **not** modified by that commit, so
the byte-identity gate holds after 011 lands. The `.venv` here already resolves it (`'ensure' in
dir(NodeIndex)` → True; 119 passed with it installed).

**Where and with what.** After `retreive_local_node` returns (R5 passed), and **before** the role
decision (`_should_resume_master` reads the map by `self.node['mac']`):

```
self.node['mac'] = settings_mac          # see below
self.network_map.ensure(self.node)
```

**Why the MAC is replaced first.** The listener keys and fills `mac` from the **service name's first
twelve characters** (`get_mac`, `CuemsAvahiListener.py:43`); the template names the service `%h`, the
hostname, so a controller's `mac` is the label `controller._` — the garbage key behind bug 1 in
`CLAUDE.md`. The announced record carries no MAC at all. The true MAC is in `settings.xml`, and the row
this daemon seeds must carry it (constitution III: labels are not identity). `merge` refreshes an
existing row in place and explicitly never clobbers `mac`, so the seeded key survives every later pass.
A side benefit: `_should_resume_master`'s map lookup by MAC now works for a controller too, instead
of relying on `master.lock` alone.

**Ordering with the first refresh.** The first `refresh_network_map` merges `listener.nodes` (self
included, under the listener's own key) into the index: matched by uuid to the seeded row → updated in
place, `online=True`, key untouched. No duplicate. Pinned by a test.

**Version detection (spec FR-016).** `0.1.0rc16` cannot express `73daab6`. A one-test module in the
manner of `tests/test_library_prerequisite.py` asserts `hasattr(NodeIndex, 'ensure')` and the
by-reference contract (insert, mutate through the caller's reference, see it in the index), so a stale
venv fails here rather than a node at boot.

**Rejected.** A daemon-side insert (plan 09 option 2): decided against by the maintainer (D2); it is
map logic in the daemon, which D22 exists to end.

---

## R7. Story 6 — the configured waits and the pre-flight

**Configuration source.** Two environment variables read once at start, with the current values as
defaults:

| Variable | Default | Governs |
|---|---|---|
| `CUEMS_NODECONF_IFACE_TIMEOUT` | `10` (s) | `get_ips()`'s `TimeoutLoop(timeout=…)` — the window's upper bound |
| `CUEMS_NODECONF_CONTROLLER_PAUSE` | `5` (s) | the controller's pre-first-pass sleep (finding 10) |

Set through a systemd drop-in (`Environment=`), documented in `README.md`. Both values logged at
start. Non-numeric or negative → log and use the default.

**Rejected.** Adding elements to `settings.xml`: the schema is `cuems-utils`' and this feature does not
change the library (spec Story 3 assumption; feature 002's FR-009 lineage). A CLI flag: the unit runs
the daemon with no arguments today, and a drop-in is what an operator on a slow node will actually
reach for.

**Pre-flight.** Before `set_comms()` (so the log line precedes any socket), the daemon checks:

- the **system bus**: `dbus.SystemBus()` succeeds;
- **avahi**: `org.freedesktop.Avahi.Server.GetVersionString()` on that bus answers — the same proxy
  `AliasPublisher._connect` acquires.

On failure: `Logger.error` naming the missing dependency, then **proceed**. Not an exit, and no
start attempt: the unit (`cuems-common` `etc/systemd/system/cuems-nodeconf.service`, R12) already
declares `Requires=avahi-daemon.service` and `After=avahi-daemon.service`, so systemd starts avahi
first and stops this daemon if avahi stops. The pre-flight cannot therefore be a race guard; it is a
**diagnostic** that puts the reason in the journal ahead of the later
`wait_for_local_service_registration` timeout, which is the exit that would otherwise be the first
symptom. A new exit path here would only add a way to fail while avahi is still acquiring its D-Bus
name (constitution VI). The suite stubs `dbus`, so the pre-flight is tested for "logs the right name
when the stub raises" and hardware-verified for the rest (ledger §5, journal step).

---

## R8. Test plan, measured against the existing suite

| Behaviour | New test file | How the window is exercised |
|---|---|---|
| Refusal before the map, exact string, no "not found" | `tests/test_startup_readiness.py` | `CuemsNodeConf()` + mocked comms thread (the pattern `test_engine_callback.py` uses); call `engine_callback` before `read_network_map()`; assert the response; then load with `cuems_conf_dir` and assert the pre-feature answers |
| Half-built state still refuses | same | `patch.object(nodeconf, '_index_from_document', side_effect=…)` fires an adopt from inside the load and captures the answer |
| Flag set only at the end of the load | same | assert `_ready is False` after `_document` is set, `True` only after `network_map`; and that a load that raises leaves it `False` |
| Other actions unaffected during the window | same | unknown/missing/non-dict requests before the load → today's answers |
| Render: real uuid, bytes equal → no write/no reload, atomic, `0644`, template read from `TEMPLATES_PATH` | `tests/test_service_record.py` | `monkeypatch` the two path constants to `tmp_path`; fixture templates carrying the sentinel; a stubbed reload counter |
| Render refuses a template without the sentinel | same | template with a real uuid → `SystemExit` |
| Unprovisioned: absent / unreadable / invalid / sentinel uuid / sentinel mac | same | new fixture `settings_sentinel.xml`; `pytest.raises(SystemExit)`; `set_comms` **not called**; no record written |
| Order: render before `set_comms` | same | a shared call log through `patch.object` on both |
| Role sites render, not copy | `tests/test_node_role.py` (setup only) | the 3 `patch('shutil.copy2')` sites (+1 in `test_integration.py`) become patches of the render helper — **setup only, no subject or assertion changes** |
| Pre-existing tests that bypass start-up keep passing | `tests/test_engine_callback.py`, `tests/test_adoption_flow.py` (setup only) | measured: these build the map directly and never call `read_network_map()`, so the flag would stay `False` and every adopt there would answer "still starting up". One setup line each, `nodeconf._ready = True`, in the two `_nodeconf` helpers and the four standalone tests, plus the adoption-flow file — listed in the commit (spec FR-004) |
| The self-lookup test keeps passing | `tests/test_service_discovery.py` (setup only) | `test_retreive_local_node` sets `nodeconf.settings_uuid` to its fixture node's uuid |
| Self guard: waits through a stale record, exits on timeout naming both uuids | `tests/test_startup_readiness.py` | listener pre-filled with a node at our IP and a foreign uuid; then the matching one appears; then never |
| `ensure` seeds by reference; no duplicate after the first merge; no-op when listed | `tests/test_self_seed.py` | empty-map fixture and populated fixture |
| Library prerequisite: `ensure` present and by-reference | `tests/test_library_prerequisite.py` (one test added) | `hasattr` + mutate-through-reference |
| Configured waits: defaults, override, garbage → default | `tests/test_startup_config.py` | `monkeypatch.setenv` |
| Pre-flight names the missing dependency | same | make the `dbus.SystemBus` stub raise |

Baseline **119 → ≈ 119 + 25**. No pre-existing test changes subject or assertion; the four
`shutil.copy2` patches move their target, and the setup lines above are added. Yardstick untouched.

---

## R9. The four root-level documents

Measured 2026-09-28: `ls *.md` → `BUGFIX_COMPLETE.md BUGFIX_NETWORK_MAP.md CLAUDE.md
DEPLOYMENT_STEPS.md README.md STARTUP_ANALYSIS.md`. `grep -nE 'write_network_map|ElementTree|getroot'
cuemsnodeconf/*.py` → no matches, confirming the three BUGFIX/DEPLOYMENT files describe a method that no
longer exists. **Decision:** `git mv STARTUP_ANALYSIS.md specs/planning/11-startup-analysis.md`,
prepend a dated status block and a per-finding status column from the brief's §5.2 (re-measured line
numbers: the brief's coordinates were checked against `6f31a7a` and hold); `git rm` the other three
with the reason in the commit message. Feature 001's `tasks.md:133` reference is left as written.

---

## R10. Packaging and the re-cut

- `debian/changelog` head is `0.1.0-8 UNRELEASED`; two bullets are **added to that entry**, no new
  version (011's `test_no_version_bump.py` pins `0.1.0-8` on our side).
- Pins do not move: `cuemsutils (>= 0.1.0rc16, << 0.1.1~)` in both files; `Breaks: cuems-common
  (<< 1.3.0-23~)` already covers the template transition (contract §2).
- The tag: `xml-refactor-merge-candidate` → **`6c0cca7`** here (annotated, object `4e53d58`;
  **present on `origin`**, contrary to the 2026-09-21 memory note, corrected today), `3af31cc` in
  `cuems-common`, `d5c4226` in `cuems-power-bridge`. This feature changes `cuemsnodeconf/CuemsNodeConf.py`
  (packaged), so after it merges into `feat/xml-refactor` the tag is re-cut **once** — by the
  maintainer, never by an agent (memory rule) — and the re-cut is announced: `cuems-utils` 011's T080
  already plans to record both re-cuts in its migration guide, so the announcement is one message to
  the `cuems-common`, `cuems-power-bridge` and `cuems-utils` flows plus the changelog wording.

---

## R11. Hardware verification

Ledger §5 (written 2026-09-28) covers the identity half: unmask/enable/start, `--check` exit 0,
`avahi-browse` once, reboot. It does **not** cover the readiness half against the real dispatch path
(constitution IV). **Decision:** add ledger **§6 — Feature 003, the start-up refusal on the real
dispatch path**: on a controller with the UI, restart `cuems-nodeconf` and click "add node" within the
first seconds; expected: the settings page shows *nodeconf is still starting up* (decision D relays it
verbatim), never "Node not found"; a retry after `READY=1` adopts. Recorded as "Not performed" until
someone books the time; silence is not an option (spec FR-020).

---

## R12. The unit file

Measured: `cuems-common` ships it (`debian/install:79` → `etc/systemd/system/cuems-nodeconf.service`).
Facts that bear on this feature:

| Directive | Value | Consequence here |
|---|---|---|
| `Requires=` / `After=` | `avahi-daemon.service` | avahi is up before step 1; the pre-flight is diagnostic (R7) |
| `After=` / `Wants=` | `network-online.target` | the interface wait (R7) is a second bound, not the first |
| `Type=notify`, `NotifyAccess=main` | | `READY=1` still comes after the first pass; the render adds one read, one compare, at most one write and a reload before the socket — inside the 60 s `TimeoutStartSec` |
| `Restart=on-failure`, `RestartSec=10` | | an **unprovisioned refusal** (exit non-zero, R3) is restarted every 10 s |
| `StartLimitBurst=5`, `StartLimitIntervalSec=33` | | …until the fifth failure, after which the unit settles as `failed`. That is the intended "refuse to start" state; `cuems-init-node --check` (exit 3) names the remedy, and the `NOT PROVISIONED` line appears in the journal five times, not forever |

**Not changed by this feature**: the unit is `cuems-common`'s. Adding `RestartPreventExitStatus=` for
the unprovisioned case would be a `cuems-common` change and is noted for their flow as optional polish.

---

## R13. Constitution V — no eleventh responsibility

Readiness (R1) is lifecycle. The render (R4) replaces the existing "Avahi service-template files"
responsibility's three `copy2` sites with one helper. The guard (R5) and the seed (R6) are node
identity, which the daemon already owns (plan 09 §5's note). The configured waits and pre-flight (R7)
are lifecycle. Nothing new joins the inventory; the atomization basis' rows stay valid, and row
"Avahi service-template files" gets *smaller*.

---

## R14. Consumer check (spec Story 4, their T096 gate) — measured 2026-09-28

Neither consumer compensates for the refusal string, and neither interprets it.

- **`cuems-engine`**: the checkout is on `rc_1`, which does not contain `cf5c4ad`; the commit is on
  `origin/feat/nodelist-modify-dispatch`. Read at the commit itself:
  `git grep -nE 'starting up|retry|retries|not found' cf5c4ad -- src/cuemsengine/ControllerEngine.py`
  → no matches. What it does carry: `NODECONF_IPC_PATH = "/tmp/nodeconf.ipc"` (:23), the existence
  probe `if not os.path.exists(NODECONF_IPC_PATH)` (:857) and an explicit `timeout=NODECONF_TIMEOUT_S`
  on the request (:867). One probe, one timeout, no retry, no reading of the error string.
- **`cuems-editor`**: flat layout (`*.py` at the repository root);
  `grep -nE 'starting up|nodeconf|retry' *.py` → no matches. The editor relays whatever the engine
  answers.

Decision D therefore requires **no change in either repository**. The gate is recorded here rather
than in their trees.
