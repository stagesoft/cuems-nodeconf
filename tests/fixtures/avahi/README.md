# Avahi service-template fixtures

Mirrors of `cuems-common`'s `usr/share/cuems/cuems.service.{controller,node,firstrun}` in the
shape its `1.3.0-23` handover ships them (cuems-utils feature 011, contract §4): every
`uuid=` TXT record carries the sentinel `00000000-0000-0000-0000-000000000000`, two per file.

`cuems-nodeconf` renders these into `/etc/avahi/services/cuems.service` by literal substitution
of the sentinel with the uuid from `/etc/cuems/settings.xml` (feature 003, contract
`specs/003-startup-readiness/contracts/service-record-render.md`).

Refresh them from `cuems-common` when its templates change; never hand-edit. The `avahi_dirs`
fixture in `tests/conftest.py` copies them into a per-test directory and points the daemon's
`TEMPLATES_PATH` / `AVAHI_SERVICES_PATH` there.
