"""The library behaviour this daemon cannot boot without (feature 002, FR-011).

`cuems-nodeconf` reads `/etc/cuems/network_map.xml` through `ConfigManager`, and
`cuems-common` ships that file with an **empty** `<node_list/>`. Loading it must
raise `ValueError` — "this node is not in the map" — which `read_network_map`
catches, because a freshly provisioned node is never listed in its own map yet.

Until `cuems-utils` **e363d03** it raised `TypeError` instead: `get_node`
iterated `node_list`, which an empty `<node_list/>` decodes to as `None`. That
is not caught, so the daemon failed start-up on every fresh install and systemd
retried it every 10 s forever — and only `cuems-nodeconf` writes a node into the
map, so nothing broke the loop.

**Why this test lives here rather than only upstream**: the fix shipped *inside*
`0.1.0rc16`, which was never released, so `cuems-utils (>= 0.1.0rc16)` is
satisfied by a build that still crashes. No pin can express the difference. This
test is how a stale checkout or venv fails here, on a developer's machine,
instead of on a node at boot. If it fails: rebuild the library
(`pip install -e ../cuems-utils` from a checkout at e363d03 or later).
"""
import pytest
from cuemsutils.tools.ConfigManager import ConfigManager


def test_an_empty_map_raises_value_error_not_type_error(cuems_conf_dir_empty):
    """The shipped empty map loads far enough to raise the documented error."""
    manager = ConfigManager(config_dir=str(cuems_conf_dir_empty), load_all=False)

    with pytest.raises(ValueError):
        manager.load_network_map()

    # Loading got far enough to populate the document before resolving this
    # node — which is what read_network_map relies on when it catches.
    assert hasattr(manager, 'network_map')
