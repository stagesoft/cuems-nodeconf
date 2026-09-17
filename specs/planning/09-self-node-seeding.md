<!-- REPO-ORIGINAL — not vendored from cuems-utils.
     Written 2026-09-17 in cuems-nodeconf. Research only: nothing here is scheduled,
     and feature 001 does not implement it. Measured against cuemsutils 0.1.0rc16
     (cuems-utils d0340fc), cuems-common feat/xml-refactor e149089, cuems-engine as
     checked out that day. Re-measure before relying on any coordinate. -->

# Self-node seeding — can nodeconf fill in its own entry at start-up?

## The question

`ConfigManager` resolves "this node" by the uuid in `settings.xml` and raises
`ValueError: Node with uuid <uuid> not found` when the document does not list it. Feature
001 hit this in `read_network_map` and answered it defensively: catch that one lookup
(research D-G). The question this document answers is the constructive alternative —
**should nodeconf instead write its own entry, so the lookup succeeds for everyone?**

Short answer: **yes, and on a properly provisioned node it is now sufficient** — but it
has preconditions, it does not belong to feature 001, and the library cannot currently
express it.

---

## 1. There are two eager lookups, not one

Both key off `settings.xml`'s uuid; both raise the same `ValueError`.

| # | Lookup | Site | Reached by |
|---|---|---|---|
| 1 | this node in `network_map.xml` | `ConfigManager.py:202` (`node_network_map` setter, from `load_network_map`) | **nodeconf's** `read_network_map`, and the engine at start-up |
| 2 | this node in `mappings.xml` / `default_mappings.xml` | `ConfigManager.py:336` (`load_net_and_node_mappings`) | the **engine** only (`load_all=True`) |

Measured: seeding a node into `network_map.xml` clears lookup 1 — and the engine then
failed at lookup 2, with both nodes present in the map on disk. Lookup 2 is not
nodeconf's to satisfy.

**Resolved for lookup 2 (maintainer, 2026-09-17):** provisioning writes this node's uuid
into `/etc/cuems/default_mappings.xml` as well as `settings.xml`. So on a properly
provisioned node the engine's mappings lookup succeeds, and `network_map.xml` — which no
package provisions per node — is the **only** document that can be missing this node.
That is what makes seeding sufficient rather than partial.

---

## 2. The seed is buildable at start-up

`network_map.xsd` requires only five fields per node; the rest are optional:

| Field | Required | Where nodeconf gets it at boot |
|---|---|---|
| `uuid` | yes (`UuidType` pattern) | `settings.xml`, via `ConfigManager.node_uuid` |
| `mac` | yes (non-empty) | `settings.xml`, via `ConfigManager.node_conf['mac']` |
| `name` | yes (non-empty) | the identity contract's `<mac>._cuems_nodeconf._tcp.local.` |
| `node_role` | yes (enum) | `firstrun` — the honest value before the election |
| `ip` | yes (non-empty) | `get_ips()`, the **first** step of `run()` |
| `adopted` / `online` | optional | `False` / `True` |

Measured: such a seed saves schema-valid, and inserting it leaves every other node's
`<online>` untouched.

**`merge` cannot be used for this.** It marks every node absent from its argument
offline, so seeding through `merge({self})` would assert "nobody else is here" before
discovery has run — corrupting `<online>`'s meaning (CLAUDE.md: a discovery-pass
snapshot). A plain insert works because `NodeIndex` is a `dict`, but see §5.

---

## 3. It fits what the rest of the system already assumes

- **The engine expects a self entry.** It de-duplicates its own uuid because it "appears
  in both `node_conf` and `network_map['node_list']`" (`ControllerEngine.py:216-217`).
- **`cuems-cluster-poweroff` looks itself up in the map** by `settings.xml` uuid, to avoid
  SSH-ing a poweroff to itself; its comment notes a missed self-entry "burns the whole
  `node_wait_s` on every single poweroff".
- **The identity contract** makes `uuid` the primary key, sourced from provisioning, and
  has `apply-identity` look the local node up in `network_map.xml` by it.
- **Discovery merges onto it cleanly.** `merge` matches by uuid, so the discovered self
  updates the seeded entry in place and **keeps the seed's MAC key** — which is more
  correct than today's key, `name[:12]` from the mDNS service name. That is only the MAC
  while the hostname is the MAC; under the node-identity hostnames (`controller`,
  `nodeNN`) it is the same name-derived garbage that caused the duplicate-node bug.

---

## 4. Preconditions

**The announced uuid must equal the `settings.xml` uuid.** Discovery keys self by the TXT
`uuid` record of `/etc/avahi/services/cuems.service`. If that differs from `settings.xml`,
discovery adds a *second* self beside the seed, and the two never merge.

Confirmed safe by provisioning (maintainer, 2026-09-17): the active file is copied from a
`/usr/share/cuems/cuems.service.*` template **after** `cuems-config-node` has rewritten the
uuid into those templates. The ordering is the load-bearing part — a copy taken *before*
that rewrite leaves the node announcing the template's shipped uuid.

A seeding implementation should still verify it at run time (read the TXT `uuid` from the
active service file, compare with `settings.xml`) and refuse loudly on a mismatch, rather
than write a self entry that discovery will duplicate.

---

## 5. Where the logic would belong

"Ensure the local node is present" is network-map domain logic, which D22 puts in
`cuems-utils`. The library has no way to express it: `NodeIndex` offers `merge`, `adopt`,
`unadopt`, `set_controller_always_adopted`, `missing_adopted`, `signature` — nothing that
adds a single node without touching the others.

Options, in preference order:

1. **Add it upstream** — e.g. `NodeIndex.ensure(node) -> bool` (add if no node carries that
   uuid; return whether it added). The daemon supplies identity; the library owns the rule.
   Costs a `cuems-utils` release, which moves the dependency floor.
2. **Daemon-side insert** — `if not any(n['uuid'] == own for n in index.values()): index[mac] = node`.
   Two lines, measured working, but it is map logic living in the daemon again, which is
   what D22 exists to end. Acceptable as an interim only if recorded as such.

Note this is **not** an eleventh responsibility (constitution V): nodeconf already owns
node identity — assigning `role_id` on adoption and applying the OS-side identity chain.
Writing this node's own identity row is that same remit.

---

## 6. What seeding does *not* fix

**The placeholder controller.** `cuems-common` ships `etc/cuems/network_map.xml` as a
conffile listing one controller, uuid `0367f391-…-0001`, ip `192.168.1.10`. Discovery never
removes unknown nodes (by design — they are "known but absent"), and
`set_controller_always_adopted` keeps it adopted, so it survives forever and stays first in
document order. Consumers that take the **first** `node_role='controller'` therefore
resolve to it on any node whose real controller was discovered later:

- `scripts/cuems-write-chrony-source` → the slave's chrony time source
- `scripts/cuems-log-collector-url` → the slave's journal-upload target

Both select with the XPath `./node_list/node[node_role='controller']/ip`, on the converted
vocabulary, so they genuinely resolve to the placeholder.

**The engine does not — for a worse reason.** `BaseEngine._controller_ip_from_map`
(`BaseEngine.py:344-357`), the fallback `get_controller_ip` uses when mDNS cannot resolve
`controller.local`, matches `node.get('node_type') == "NodeType.master"` — the pre-007
spelling. Against a converted map it matches nothing, raises, and `set_controller_ip` turns
that into `exit(-1)`. `find_hosts` (`:360-387`) carries the same stale spelling plus
`online == 'True'` against a now-boolean field, and has **no callers at all**, so its
`Multiple controllers found in network map` guard cannot fire today. Both are cuems-engine's
to migrate — `cuems-common`'s CLAUDE.md records `CONTROLLER_NETWORK_FLAG` as feature 010's,
"once the readers move" — and the placeholder becomes reachable by that guard the moment
they do.

Measured after seeding: the first `node_role='controller'` in the written map was still
`0367f391-…-0001` at `192.168.1.10`.

**An empty map is schema-valid** — `node_list` is `minOccurs="0"` and so is `node`, and a
document with an empty `node_list` saves and loads. So `cuems-common` could ship an empty
map instead of a placeholder, leaving the first entry on any node to be the seed or a real
discovery. That is a `cuems-common` decision, recorded here because it is the other half of
making a fresh node's map correct.

---

## 7. Provisioning requirements this research fixes in place

Confirmed by the maintainer 2026-09-17, and a **hard requirement for the future
`cuems-utils` self-provisioning package**:

1. `/etc/cuems/settings.xml` carries this node's uuid.
2. `/etc/cuems/default_mappings.xml` carries a node entry with **the same** uuid.
3. `/etc/avahi/services/cuems.service` is installed from a `/usr/share/cuems` template
   **after** the template's uuid has been rewritten.

All identity carriers must agree on one uuid; both `ConfigManager` lookups and mDNS
self-identification depend on it. `network_map.xml` is deliberately *not* on this list —
it is the cluster's shared topology, not per-node provisioning, which is why seeding it at
run time is the proposal here.

### The provisioning utility needs work for the Avahi rename

Independently of seeding, `cuems-config-node` and the sudoers grants hardcode the template
filenames and break when feature 001's US2 / flow 03 renames them:

| File | What breaks |
|---|---|
| `cuems-common/usr/bin/cuems-config-node:64` | `service_files = ['cuems.service.firstrun', 'cuems.service.master', 'cuems.service.slave']` — parses each by name; a rename makes provisioning fail on a missing file |
| `cuems-common/etc/sudoers.d/99-cuems:3-5` | three `cp /usr/share/cuems/cuems.service.<role> /etc/avahi/services/cuems.service` grants naming the old paths — after a rename the copy is no longer permitted |

Both are `cuems-common`'s, and its own feature
`specs/001-node-role-and-conversion-ordering` already covers them: plan lines 109-115 name
the sudoers file and `cuems-config-node:64`, T007 writes a test that every file naming a
template names one that exists, and T008 performs the renames. No action for this
repository beyond the merge coordination feature 001 already carries (T041/T042).

---

## 8. Recommendation

Worth building, as **its own feature**, not inside 001:

- 001 is the network-map object adoption; seeding is new behaviour with its own risk
  surface (it writes at boot, before discovery).
- It needs either the upstream `ensure` (§5) or a recorded interim.
- Its value is concrete: on a fresh node the engine currently exits and retries every 10 s
  until nodeconf's first refresh lands, which can be a minute or more on a controller that
  gets promoted (registration wait, election, a networking restart, settle sleeps). A seed
  written seconds after `get_ips()` clears that on the engine's next retry.
- The `ValueError` catch in `read_network_map` stays either way: the read that precedes the
  seed is itself lookup 1. Seeding narrows it to one boot, rather than removing it.

Feature 001 leaves the defensive catch in place and this document as the constructive
follow-up.
