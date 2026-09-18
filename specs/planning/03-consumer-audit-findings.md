<!-- EXTRACTED from cuems-utils@b7598d5
     specs/planning/xml-rebuild/xml-rebuild-09-consumer-audit.md, findings C4/C6/C9/C10.
     C10 cites tools-external-consumers-and-timeoutloop-migration.md (Track 2, item 5) as the
     place the TimeoutLoop relocation was first recorded; that document is NOT reproduced here
     because C10 and 07-public-surface.md together carry everything it says about this repo. -->

# Consumer-audit findings that belong to `cuems-nodeconf`

Measured against live files **2026-09-03**. Re-verify line numbers before relying on them —
this project has twice found coordinates that had moved.

## C4 — the schema descriptor has no public import path

010 requires `cuems-editor` to serve the descriptor over WS (D25/D26), but it
lives at `cuemsutils.xml.descriptor` (`SchemaDescriptor`, `generate_script_example`,
`generate_settings_example`) and `cuemsutils.xml.__all__` is `[]` — Q14's
"`xml/` is internal machinery", asserted by 006's FR-019 and SC-005.

The erosion is not hypothetical: `cuems-nodeconf` **already** imports
`cuemsutils.xml.mapper` (`Mapper`, `read_config_document`) and
`cuemsutils.xml.settings` (`NetworkMap as _NetworkMapReader`) today, from
`CuemsNodeConf.py:22-23`. No feature recorded that as a violation.

**Decision (D34, 2026-09-03):** the descriptor becomes reachable **through
`ConfigManager`**, the existing public config object (D15), rather than through
a new public module. Two things follow, and the spec states them deliberately
rather than leaving them to be inferred:

1. `ConfigManager`'s descriptor accessor covers **all six schemas**, `script`
   included. `ConfigManager` is otherwise a config-domain object, so serving
   the show schema's descriptor from it is a deliberate widening of its role —
   justified because the alternative is two public paths for one mechanism,
   and because the editor that serves config forms is the same one that serves
   the script template.
2. `cuems-nodeconf`'s two internal imports move onto public equivalents in the
   same feature, so 010 ends the Q14 erosion rather than extending it.

---


## C6 — the Avahi TXT-record vocabulary has two owners, and §8 assigns one

§8 hands 010 `cuems-common`'s four files. But the retired vocabulary lives in
**both** repositories, and the TXT key is the wire between two daemons:

**`cuems-common`** (27 `node_type` occurrences total):
`etc/avahi/services/cuems.service:6,13`,
`usr/share/cuems/cuems.service.{firstrun,master,slave}:6,13` — the last two
carry the retired word in the **filename**, so `debian/install` and anything
resolving a template by name moves too.

**`cuems-nodeconf`** (30 occurrences — *more* than common):
its own copies at repo root, `cuems.service.{firstrun,master,slave}:12,19`;
the producer `CuemsSettings.py:27`
(`settings_dict['properties'] = {'node_type': 'slave'}`); the consumer
`CuemsAvahiListener.py:96-155` (two blocks, `add_service` and
`update_service`, both keying on `b'node_type'` through
`_AVAHI_NODE_TYPE_TO_ROLE`); and the installer
`CuemsNodeConf._install_master_service_template` + the inline slave-template
copy in `set_node_role`.

`AvahiTool.py:12` and `CuemsAvahiListener.py:19-24` both carry comments
deferring this "to feature 008" — the pre-renumbering name. 008 was
cuems-utils-only, so the work is currently assigned to a feature that has
closed.

**Decision (D33, 2026-09-03):** both halves land **inside 010**, as one
coordinated cutover. The TXT key cannot be half-renamed: a listener reading
`node_role` against a publisher writing `node_type` discovers nothing, and
discovery failure is how a cluster loses its topology. This is the largest
single sub-scope 010 acquires from this audit; the plan sequences it as one
unit (publisher, template files, filenames, `debian/install`, listener,
`_AVAHI_NODE_TYPE_TO_ROLE`'s removal) rather than per-repo.

---


## C9 — three stale documents that are 010's own inputs

1. **`cuems-utils/CLAUDE.md`** states the cuems-common node-identity field
   contract is *"not yet updated for the rename"*. **False as of 2026-08-24**:
   `cuems-common`'s local `007-node-model-migration` branch carries four
   commits — schema mirror + shipped-map conversion (`9fc738e`), the conversion
   script wired into `postinst` with three tools updated (`f4a8b3c`), versioned
   package dependencies (`6a9ec7f`), and the documentation pass (`78b89ad`).
   `etc/cuems/network_map.xml:9` already reads `<node_role>controller</node_role>`;
   `debian/postinst:35-58` runs `cuems-migrate-network-map` over both the live
   file and its `.dpkg-new` sibling; `tests/test_network_map_conversion.py`
   covers it. Unmerged and unreleased — but "landed on a branch", not
   "not started".
2. **`cuems-common/CLAUDE.md:88`** says `CONTROLLER_NETWORK_FLAG` and the enum
   constants are *"migrated in feature 008"*. The 2026-08-25 renumbering makes
   that **010**.
3. **`cuems-nodeconf/cuemsnodeconf/AvahiTool.py:12`** and
   **`CuemsAvahiListener.py:19-24`** defer the TXT-record change *"to feature
   008"* — see C6; now 010's, by D33.

All three are read by whoever executes 010. Correcting them is part of the
feature, not housekeeping after it.

---

## C10 — work landed after 008 closed, in no plan

Three commits on `feat/xml-refactor` post-date 008's close-out (`f740711`) and
carry consumer impact §8 predates:

- **`7c5896c`** — `Timeoutloop` relocated to `cuemsutils.tools.TimeoutLoop.TimeoutLoop`,
  with a `deprecated_alias` shim at `cuemsutils.timeoutloop`.
  `cuems-nodeconf/cuemsnodeconf/CuemsNodeConf.py:26` still imports the old
  path and uses it at `:309, :617, :629`. Recorded as an open follow-up in
  `specs/planning/tools-external-consumers-and-timeoutloop-migration.md`
  (Track 2, item 5) — the only remaining open item in that document.
  > **✅ Closed here by feature 001** (annotated 2026-09-18): `CuemsNodeConf.py` imports
  > `cuemsutils.tools.TimeoutLoop`, and no `cuemsutils.timeoutloop` import remains (SC-008).
  > `cuems-utils`' import census recorded it gone (`b6b5eb5`).
- **`573daa0`** — `xml/_deprecation.py` promoted to `cuemsutils/_deprecation.py`.
  No consumer imports it directly (checked); recorded so the shim's own import
  path is not mistaken for stable.
- **`841ee3e`** — `StringSanitizer.sanitize_text_size`/`sanitize_name`
  off-by-one fixed (`[0:254]`/`[0:65534]` → the documented 255/65535).
  `cuems-editor` uses `StringSanitizer` on the user-string-to-filesystem-path
  route at three sites; names one character longer now survive sanitizing.

---

