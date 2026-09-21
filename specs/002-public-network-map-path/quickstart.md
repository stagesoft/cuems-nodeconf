# Quickstart — validating 002

How to prove this feature works. Every command is runnable from the repository root on a
development checkout; §4 is the part that needs hardware, and it is expected to be answered
"not performed" unless someone actually does it (constitution: silence is a failure).

## 0. Prerequisites

```bash
# cuemsutils MUST be a build at e363d03 or later. The version string cannot say so —
# the empty-node_list fix shipped INSIDE 0.1.0rc16 — so rebuild from the checkout:
.venv/bin/pip install -e ../cuems-utils

# the discriminator: if this fails, the installed build predates the fix
.venv/bin/python -m pytest -q ../cuems-utils/tests/contract/test_empty_node_list.py
```

## 1. The gate

```bash
./run-tests.sh          # the suite, then the yardstick — two separate invocations
```

**Expected**: `both green`. The suite count rises from 95 by the tests this feature adds; the
yardstick stays at 15 and its file stays byte-identical:

```bash
diff specs/planning/yardstick/test_nodeindex_characterization.py \
     ../cuems-utils/tests/contract/test_nodeindex_characterization.py && echo IDENTICAL
```

## 2. The feature's own claims

| Claim | Command | Expected |
|---|---|---|
| **SC-001** no internal import in shipped code | `grep -rn "from cuemsutils.config" cuemsnodeconf/` | no output |
| The tests still name it (FR-007, deliberate) | `grep -rc "patch.object(\s*CuemsNetworkMapType" tests/*.py` | the 28 sites remain |
| **SC-002** no pre-existing test changed in substance | `git diff <base> -- tests/` | only added setup lines and new tests; no assertion or test name altered |
| **SC-004** an adoption between passes survives | `pytest tests/ -k "between_passes or stale"` | passes |
| **SC-005** fresh-node boot | `pytest tests/test_fresh_node_boot.py` | passes |

## 3. The fresh-node path by hand

The path every fresh install takes, and the one nothing in the suite covered before this
feature (`cuems-utils`' §3). Run it against a **temporary** directory — never the real
`/etc/cuems`:

```bash
.venv/bin/python - <<'PY'
import os, sys, shutil, tempfile
sys.path.insert(0, "tests"); import conftest          # dbus/systemd/netifaces stubs
from cuemsutils.tools.NodeList import node as Node, NodeRole
with tempfile.TemporaryDirectory(dir=".venv") as d:
    shutil.copy("tests/fixtures/etc_cuems/settings.xml", d)
    os.environ["CUEMS_CONF_PATH"] = d
    from cuemsnodeconf import CuemsNodeConf as M
    nc = M.CuemsNodeConf(); nc.map_path = os.path.join(d, "network_map.xml")
    # a) no map at all -> the daemon seeds one and loads it
    nc._seed_empty_map(); nc.read_network_map()
    print("seeded and read :", len(nc.network_map), "nodes")
    print("mode            :", oct(os.stat(nc.map_path).st_mode & 0o777))   # expect 0o644
    # b) first write, then re-read
    nc.network_map['aabbccddeeff'] = Node(
        uuid='0367f391-ebf4-48b2-9f26-0000000000aa', mac='aabbccddeeff',
        name='aabbccddeeff._cuems_nodeconf._tcp.local.', node_role=NodeRole.node,
        ip='192.168.1.11', adopted=False, online=True)
    nc._save_network_map()
    nc2 = M.CuemsNodeConf(); nc2.map_path = nc.map_path; nc2.read_network_map()
    print("after re-read   :", len(nc2.network_map), "nodes")
PY
```

**Expected**: `seeded and read : 0 nodes`, `mode : 0o644`, `after re-read : 1 nodes`.

Also check the seed is the shipped shape, not a bare root:

```bash
diff <(git -C ../cuems-common show f2fc0f5:etc/cuems/network_map.xml) \
     tests/fixtures/etc_cuems/network_map_empty.xml && echo "fixture == shipped map"
```

## 4. On real hardware — state the answer, whichever it is

The suite characterizes Avahi against mock `ServiceInfo` objects and mocks the RPC dispatch. It
cannot show the operator's button working (constitution IV) or a node booting. So record both
of these explicitly, as performed or not performed:

1. **The operator chain (SC-003-equivalent).** On the controller, adopt and unadopt a node from
   the frontend settings view, and confirm the map on disk changes **immediately**. `NodeIndex.adopt`
   mutates without persisting, so a dropped save looks correct in the UI and is lost on restart.
2. **A genuine fresh node.** Install on a node whose `/etc/cuems/network_map.xml` is the shipped
   empty conffile, and confirm the daemon starts — no `TypeError`, no restart loop — writes itself
   into the map, and that the map stays `0644` so the `User=cuems` engine can read it.

> **As of 2026-09-21 neither has been performed.** The empty-map boot was verified only in a
> temporary directory on a development checkout, against `cuemsutils` at `ce5b5b0`. That is
> evidence for the code path, not for a node.
