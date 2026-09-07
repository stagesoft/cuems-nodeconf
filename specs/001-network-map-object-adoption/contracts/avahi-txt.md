# Contract — the Avahi discovery TXT record

**Status**: changing in this feature, as one cutover across two repositories (D33).

This is a **wire contract between two daemons**. A listener reading `node_role` against a
publisher writing `node_type` discovers nothing — and discovery failure is silent: no
error, no exception, nodes simply never appear. That is how a cluster loses its topology.

---

## Before → after

| | Before | After |
|---|---|---|
| TXT key | `node_type` | **`node_role`** |
| Values | `master`, `slave`, `firstrun` | **`controller`**, **`node`**, `firstrun` |
| Template filenames | `cuems.service.{firstrun,master,slave}` | **`cuems.service.{firstrun,controller,node}`** |

The values now match `NodeRole`'s own members and `network_map.xml`'s `node_role` field,
so the wire, the model and the document finally spell the same thing the same way. The
translation table that existed to bridge them is deleted, not re-pointed.

**Rename only — no semantic change.** In particular the publisher's default
self-announcement stays "the non-controller role" (`slave` → `node`); it does not become
`firstrun`. Changing what a node announces before its role is determined is a different
decision and is not part of this feature.

## Services carrying the record

Each template publishes the record **twice**, once per service type:

| Service | Port | Records |
|---|---|---|
| `_cuems_nodeconf._tcp` | 9000 | `node_role=<value>`, `uuid=<node uuid>` |
| `_cuems_osc._tcp` | 9090 | `node_role=<value>`, `uuid=<node uuid>` |

Both must be renamed in every template. `uuid` is untouched.

## Ownership of the change

| Repository | Owns |
|---|---|
| **cuems-common** | `etc/avahi/services/cuems.service`; `usr/share/cuems/cuems.service.{firstrun,master,slave}` — the shipped templates, **including the filenames** and the `debian/install` entries that place them |
| **cuems-nodeconf** (this) | the publisher (`CuemsSettings.py:27`); the consumer (`CuemsAvahiListener.py:96-155`); **two** translation tables; the installer's template-path construction (`CuemsNodeConf.py:381`, `:419`); test fixtures; the non-shipped dev script |

**Two tables, not one.** The consumer audit named `CuemsAvahiListener`'s
`_AVAHI_NODE_TYPE_TO_ROLE`. `AvahiTool.py` carries **its own identical copy**. Both retire.

**This repository ships no templates.** Its three root-level `cuems.service.*` files are
unshipped duplicates — there is no `debian/install` here, and `debian/rules` strips the
staged tree to `cuemsnodeconf*`. The files the installer reads at
`/usr/share/cuems/` come from `cuems-common`. The duplicates are **deleted**, not renamed.

## Consumer behaviour on an unrecognised value

Preserved: a value outside the accepted set is **logged and the service is skipped**, not
absorbed as a default. This is what makes a half-renamed cluster diagnosable rather than
merely broken — the log names the unexpected value and the accepted set.

Without the translation table the check becomes membership in `NodeRole`; the logging must
survive that simplification.

## The cutover rule

1. Both repositories' halves are developed independently.
2. Their **merges are simultaneous**. Neither lands alone.
3. The package constraint enforces it for installations: `cuems-common` already ships
   `Breaks: cuems-nodeconf (<< 0.1.0-8)`, so a node cannot end up with a renamed
   `cuems-common` beside an un-renamed `cuems-nodeconf`. This feature lands at `0.1.0-8`
   to make that constraint true rather than aspirational.

## Verification

Cross-repository and not satisfiable from this side alone. See `quickstart.md` §4 —
spec SC-004 and SC-006, and SC-007 for the package refusal.
