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

**Feature 003 adds a second gate of the same kind**: `NodeIndex.ensure`, the
primitive the daemon seeds its own map row through, landed in `cuems-utils`
**73daab6** (its feature 011, T014), again inside `0.1.0rc16`. The pin cannot
express it either. If the second test fails: rebuild the library from a checkout
at 73daab6 or later. Never add a daemon-side insert instead (decision D2).
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


def test_node_index_ensure_is_present_and_inserts_by_reference():
    """`ensure` exists (cuems-utils 73daab6) and honours the aliasing contract."""
    from cuemsutils.tools.NodeList import NodeIndex

    assert hasattr(NodeIndex, 'ensure')

    index = NodeIndex()
    own = {'uuid': '0367f391-ebf4-48b2-9f26-000000000001', 'mac': '2cf05d21cca3',
           'name': 'self', 'adopted': False, 'online': True}

    assert index.ensure(own) is True
    assert index['2cf05d21cca3'] is own          # the caller's object, not a copy

    own['adopted'] = True                          # mutate through the caller's reference
    assert index['2cf05d21cca3']['adopted'] is True

    other = dict(own, mac='ffffffffffff')          # same uuid, different key
    assert index.ensure(other) is False
    assert list(index) == ['2cf05d21cca3']         # nothing inserted, nothing touched
