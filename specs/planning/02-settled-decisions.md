<!-- EXTRACTED from cuems-utils@b7598d5
     specs/planning/xml-rebuild/xml-rebuild-07-speckit-prompts.md §2 (D1-D36, Q11, Q14)
     Only the decisions that BIND this repository are reproduced. -->

> **Status (2026-10-13): PARTLY IN FORCE — D11, D22, D34, Q14 and FR-030a-i/ii still bind; D33 is executed; D23 bound feature 010 only, and a dedicated atomization feature needs the maintainer to lift it explicitly.** See `README.md` for the index.

# Settled decisions that bind `cuems-nodeconf`

**Do not reopen, do not propose alternatives.** These were settled across features 004–010 of the
XML rebuild. The full list (D1–D36, Q11, Q14) lives in `xml-rebuild-07-speckit-prompts.md` §2 in the
`cuems-utils` checkout; the seven below are the ones that constrain work in *this* repository.

| # | Decision |
|---|---|
| **D11** | The node model **moved out of here** into `cuemsutils` in feature 007. It lives there **only**. Feature 007 is **done** in this repository — confirm it, do not redo it |
| **D22** | Network-map config-object logic (merge/adopt/unadopt/refresh/signature/write orchestration) lives in `cuems-utils` on `NodeIndex`/`CuemsNetworkMapType`, mirroring `ConfigManager`/`ConfigBase` — **not** reimplemented ad hoc on this daemon. Equivalence with today's behaviour was **measured in 008** by characterization tests ported from this class. Those tests are the yardstick: the swap is done when they still pass against the new API, **not** when the code looks equivalent |
| **D23** | The **full atomization** of `CuemsNodeConf` (the other nine responsibilities) is **not** this feature's work. 008 recorded the target-design basis; feature 010 consumes row 5 only. Leave that basis intact — do not execute it, and do not invalidate it |
| **D27** | Nothing in the ecosystem releases until every feature-010 flow lands. This repository does not ship independently |
| **D33** | The Avahi TXT-record vocabulary (`node_type=master\|slave\|firstrun`) is renamed in **both** this repository **and** `cuems-common`, as **one coordinated cutover**. It cannot be half-renamed: a listener reading `node_role` against a publisher writing `node_type` discovers nothing, and discovery failure is how a cluster loses its topology |
| **D34** | The descriptor and the config objects reach this repository through **public** paths. `cuemsutils.xml` declares `__all__ == []` — reaching into it is the violation this work ends |
| **Q14** | `cuemsutils.xml` is internal machinery, by an explicit and tested decision |

## Two standing rules from the same source

- **FR-030a-i** — the node model and its testing live in `cuemsutils` **exclusively**. A node-model
  test appearing in this repository during migration is a regression, not coverage.
- **FR-030a-ii** — a caller that **keeps resolving but becomes wrong** is a distinct and more
  dangerous class than one that stops resolving. Nothing fails, the suite stays green, and the
  answer is silently wrong. These are **searched for**, not waited for.
