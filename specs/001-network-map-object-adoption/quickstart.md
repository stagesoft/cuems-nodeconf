# Quickstart — how each success criterion is actually verified

The constitution's testing gate requires this feature to say how it is verified on real
hardware, or to record the manual procedure honestly. This is that record.

**Read this first**: the suite here characterizes Avahi behaviour against mock
`ServiceInfo` objects, with `dbus` and `systemd.daemon` stubbed in `conftest.py`. It pins
translation logic. **Nothing in it proves the daemon works on a node.** SC-003 and SC-006
are therefore manual, on the live controller, and no amount of green suite substitutes.

---

## Prerequisites

- `.venv` on Python 3.11 with `cuemsutils >= 0.1.0rc16` installed editable from the
  sibling checkout. If the runtime version and `pip show` disagree, re-run
  `.venv/bin/pip install -e /path/to/cuems-utils` — editable installs freeze the version
  in their metadata at install time, and the packaged floor cannot be validated against a
  stale one.
- For §4 only: the sibling `cuems-common` checkout carrying flow 03's half.
- For §3 and §4: SSH to the controller running this daemon.

---

## 1. The equivalence gate — SC-001

```bash
.venv/bin/python -m pytest specs/planning/yardstick/ -q
```

**Expected**: `15 passed`.

Run it **unchanged**. If it fails, the port is wrong — the yardstick was written by
pinning this class's behaviour before it moved, precisely so equivalence could be measured
here. If you find yourself editing it to accommodate the new API, stop: that is the moment
the guarantee is lost. Its fixes belong in `cuems-utils` and are re-vendored from there.

## 2. The suite and the counts — SC-002, SC-004, SC-005, SC-008

```bash
.venv/bin/python -m pytest -q                       # expect: all pass, none skipped

# SC-002 — none of the nine replaced methods survive
grep -nE 'def (refresh_network_map|_map_signature|write_network_map|merge_discovered_nodes|set_master_always_adopted|check_missing_adopted_nodes|adopt_node|unadopt_node|read_network_map)' \
  cuemsnodeconf/CuemsNodeConf.py                    # expect: refresh_network_map, adopt_node, unadopt_node,
                                                    #   read_network_map — thin adapters, no ad hoc logic

# SC-004 — the retired key is gone outside the vendored snapshots
grep -rn 'node_type' --exclude-dir=.git --exclude-dir=.venv \
  --exclude-dir=specs . | grep -v '^\./specs/'      # expect: no output

# SC-008 — no internal or deprecated imports remain
grep -n 'cuemsutils\.xml\|cuemsutils\.timeoutloop' cuemsnodeconf/*.py   # expect: no output
.venv/bin/python -m pytest -q 2>&1 | grep -i 'deprecat'                 # expect: no output
```

The deprecation-warning check matters: nine `TimeoutLoop` warnings fire today, and their
disappearance is the evidence FR-014 landed at all three call sites rather than one.

## 3. The operator's chain, end to end — SC-003

**Manual, on the controller. Not satisfiable by the suite.** The RPC shape is a contract
with an Angular component; "the port compiles" is not evidence the button works.

Deploy the built package to the controller, then, for each row of
`contracts/engine-rpc.md`'s outcome table, drive the case from the **frontend settings
view** — not by calling the method directly, which skips the dispatch the contract lives in.

| Case | Set up by | Expect in the UI | Expect on disk |
|---|---|---|---|
| adopt an online node | a discovered, unadopted node | success | `<adopted>True</adopted>` **immediately**, before the next discovery pass |
| adopt an already-adopted node | repeat the above | success, no change | unchanged |
| adopt an offline node | power a node down, wait for a discovery pass | `Cannot adopt node {uuid}: node is offline` | unchanged |
| adopt/remove an unknown uuid | craft the request | `Node {uuid} not found` | unchanged |
| unadopt a node | any adopted non-controller | success | `<adopted>False</adopted>` immediately |
| unadopt the controller | the controller's own entry | `Cannot unadopt master node` | unchanged |

```bash
# watch the daemon while driving the UI
journalctl -u cuems-nodeconf -f
# confirm persistence is immediate, not deferred to the next tick
watch -n1 'grep -A2 "<uuid>TARGET" /etc/cuems/network_map.xml'
```

**The persistence check is the one most likely to be missed.** `NodeIndex.adopt` mutates
without writing; if the explicit save is dropped, every case above still *looks* correct in
the UI and the state is lost on restart.

Also confirm no request stalls: send a well-formed message with an action other than
`nodelist_modify` and check a response returns rather than the engine waiting out its 15 s
timeout.

## 4. Discovery across the rename — SC-006, SC-007

**Cross-repository. Cannot be verified from this side alone.**

With **both** halves applied (this repository's and flow 03's):

```bash
avahi-browse -rt _cuems_nodeconf._tcp        # expect: txt = ["node_role=controller"|"node_role=node", "uuid=..."]
grep node_role /etc/cuems/network_map.xml     # expect: every node resolved to a real role
journalctl -u cuems-nodeconf | grep -i unrecognised   # expect: nothing
```

A controller and a node must discover each other, resolve roles, and both appear in the
map.

With **only one** half applied — do this deliberately once, in the lab, so the failure mode
is known rather than theoretical: the mismatched side must **log the unrecognised value and
skip the service**, not silently default it. Confirm nodes fail to appear rather than
appearing mis-roled. Silent mis-roling would be the worse bug and is what the logging
exists to prevent.

**SC-007 — the package refusal.** Build `.deb`s of both packages and attempt the
out-of-order install:

```bash
sudo dpkg -i cuems-common_*.deb              # carries the new vocabulary
sudo dpkg -i cuems-nodeconf_0.1.0-7_all.deb  # the pre-cutover version
# expect: refused — cuems-common Breaks: cuems-nodeconf (<< 0.1.0-8)
```

This demonstration was deferred once already, because no releasable `.deb` of any of the
three repositories existed. This feature is the release, so the excuse has expired: **a
gate that has never been demonstrated is a claim.**

## 5. Recovery, if the daemon misbehaves after deployment

The known crash-loop and its recovery, unchanged by this feature but worth having to hand:

```bash
sudo systemctl disable --now cuems-nodeconf
sudo rm -f /tmp/nodeconf.ipc
sudo systemctl restart cuems-controller-engine
```

The engine tolerates an *absent* socket; only a root-owned one kills it.

---

## What "done" looks like

§1 and §2 green in CI. §3 walked on the controller with all six rows observed, including
the persistence check. §4 walked with both halves present, plus the deliberate
half-renamed check and the package refusal. Anything in §3 or §4 that was not actually
performed is recorded as not performed — the constitution accepts "verified" and "not
verified", and treats silence as a failure.
