# cuems-nodeconf
## Node identity and the mDNS service record

`cuems-nodeconf` is the sole writer of `/etc/avahi/services/cuems.service`. At every start, before
it binds its request socket, and again at every role change, it renders the role template
`cuems-common` ships (`/usr/share/cuems/cuems.service.{controller,node,firstrun}`, which carry a
placeholder uuid) over the identity in `/etc/cuems/settings.xml`, writes the record atomically and
reloads `avahi-daemon` only when the bytes changed. Nothing else may write that file.

- **After re-minting an identity** (`cuems-init-node --force-new-identity`, or a re-mint by a later
  tool): **restart `cuems-nodeconf`**. Until then `cuems-init-node --check` exits **1**, because the
  live record disagrees with `settings.xml`.
- **An unprovisioned node** (`settings.xml` absent, unreadable, invalid, or carrying the placeholder
  identity): the daemon logs `NOT PROVISIONED …`, exits non-zero, announces nothing and creates no
  socket. `cuems-init-node --check` exits **3** in the same state and names the fix. The unit's
  `Restart=on-failure` retries five times in 33 s and then settles as `failed`; that is the intended
  end state, not a crash loop to chase.
- **A discovered self with the wrong uuid** (a stale record still served while avahi reloads, or a
  foreign template): the daemon waits it out and, on timeout, refuses with both uuids in the log.

Contract: `specs/003-startup-readiness/contracts/service-record-render.md`.

## Configuration

The daemon takes no arguments. Two start-up waits can be set through the unit's environment
(feature 003); both default to the values the daemon has always used.

| Variable | Default | What it bounds |
|---|---|---|
| `CUEMS_NODECONF_IFACE_TIMEOUT` | `10` (seconds) | how long start-up waits for a usable cluster interface. This is also the upper bound of the window in which an adopt is answered *nodeconf is still starting up* |
| `CUEMS_NODECONF_CONTROLLER_PAUSE` | `5` (seconds) | the pause a controller takes before its first discovery pass, so slaves can appear |

A non-integer or negative value is logged and the default used. Set them with a drop-in:

```
systemctl edit cuems-nodeconf.service
# [Service]
# Environment=CUEMS_NODECONF_IFACE_TIMEOUT=20
```

At start the daemon also logs a pre-flight: whether the system bus is reachable and whether
`avahi-daemon` answers on it. A failure there is named in the journal but never fatal on its own; the
unit already orders this daemon after `avahi-daemon.service` and requires it.
