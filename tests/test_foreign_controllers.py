# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""
Foreign controllers on a shared LAN.

Several clusters share the workshop LAN (test2, test, test3), and every
controller announces itself over mDNS. A host's map must only ever hold ITS
cluster's controller: on 2026-10-01 test2's nodeconf merged test3 into its map
and marked it adopted.

The four scenarios are origin/rc_1 80ccc83's regression tests, translated to
this branch, where the merge is cuemsutils' (D22). Keeping new foreign
controllers out is done here, as an interim filter on what discovery hands to
refresh. Removing one an earlier pass already saved needs the library, and is
the strict xfail at the bottom; see
specs/upstream-reports/foreign-controller-scoping.md.
"""
import re

import pytest

from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener
from cuemsutils.config.network_map import CuemsNetworkMapType
from cuemsutils.tools.NodeList import NodeIndex, NodeRole, node as Node

OUR_CONTROLLER = '0367f391-ebf4-48b2-9f26-0000000000c1'
OUR_NODE = '0367f391-ebf4-48b2-9f26-0000000000b1'
FOREIGN_1 = '0367f391-ebf4-48b2-9f26-0000000000f1'
FOREIGN_2 = '0367f391-ebf4-48b2-9f26-0000000000f2'


def _controller(uuid, mac, ip, **fields):
    return Node(uuid=uuid, mac=mac, name=f'{mac}._cuems_nodeconf._tcp.local.',
                node_role=NodeRole.controller, ip=ip, **fields)


def _node(uuid=OUR_NODE, mac='112233445566', ip='169.254.0.2', **fields):
    return Node(uuid=uuid, mac=mac, name=f'{mac}._cuems_nodeconf._tcp.local.',
                node_role=NodeRole.node, ip=ip, **fields)


def _nodeconf(tmp_path, own):
    nodeconf = CuemsNodeConf()
    nodeconf._document = CuemsNetworkMapType()
    nodeconf.network_map = NodeIndex()
    nodeconf.listener = CuemsAvahiListener(ip=own['ip'])
    nodeconf.map_path = str(tmp_path / 'network_map.xml')
    nodeconf.node = own
    return nodeconf


def _uuids(nodeconf):
    return {n['uuid'] for n in nodeconf.network_map.values()}


def test_a_controller_ignores_foreign_controllers(tmp_path):
    own = _controller(OUR_CONTROLLER, 'aabbccddeeff', '169.254.0.1', adopted=True, online=True)
    nodeconf = _nodeconf(tmp_path, own)
    nodeconf.network_map['aabbccddeeff'] = own

    # The controller announces itself as 'controller', not its mac (CLAUDE.md, bug 1).
    nodeconf.listener.nodes['controller._'] = _controller(
        OUR_CONTROLLER, 'controller._', '169.254.0.1', online=True)
    nodeconf.listener.nodes['112233445566'] = _node(online=True)
    nodeconf.listener.nodes['controller-2._'] = _controller(
        FOREIGN_1, 'controller-2._', '10.16.10.4', online=True)
    nodeconf.listener.nodes['ac2b6e046d5c'] = _controller(
        FOREIGN_2, 'ac2b6e046d5c', '10.16.10.2', online=True)

    nodeconf.refresh_network_map()

    assert _uuids(nodeconf) == {OUR_CONTROLLER, OUR_NODE}
    assert nodeconf.network_map['aabbccddeeff']['adopted'] is True
    assert nodeconf.network_map['112233445566']['adopted'] is False  # waits for the operator
    assert FOREIGN_1 not in open(nodeconf.map_path).read()


def test_a_node_keeps_its_recorded_controller_and_ignores_others(tmp_path):
    own = _node(adopted=True, online=True)
    nodeconf = _nodeconf(tmp_path, own)
    nodeconf.network_map['aabbccddeeff'] = _controller(
        OUR_CONTROLLER, 'aabbccddeeff', '169.254.0.1', adopted=True, online=False)
    nodeconf.network_map['112233445566'] = own

    nodeconf.listener.nodes['controller._'] = _controller(
        OUR_CONTROLLER, 'controller._', '169.254.0.1', online=True)
    nodeconf.listener.nodes['112233445566'] = _node(online=True)
    nodeconf.listener.nodes['controller-2._'] = _controller(
        FOREIGN_1, 'controller-2._', '10.16.10.4', online=True)

    nodeconf.refresh_network_map()

    assert _uuids(nodeconf) == {OUR_CONTROLLER, OUR_NODE}
    assert nodeconf.network_map['aabbccddeeff']['online'] is True


def test_a_fresh_node_with_no_recorded_controller_accepts_the_first_one(tmp_path):
    # First-join behaviour is unchanged: with no controller in the map there
    # is nothing to compare against, so the discovered controller is taken.
    nodeconf = _nodeconf(tmp_path, _node())

    nodeconf.listener.nodes['controller._'] = _controller(
        OUR_CONTROLLER, 'controller._', '169.254.0.1', online=True)
    nodeconf.listener.nodes['112233445566'] = _node(online=True)

    nodeconf.refresh_network_map()

    assert _uuids(nodeconf) == {OUR_CONTROLLER, OUR_NODE}
    controller = next(n for n in nodeconf.network_map.values() if n['uuid'] == OUR_CONTROLLER)
    assert controller['adopted'] is True


def test_the_filter_passes_node_objects_through_uncopied(tmp_path):
    # The library's merge relies on aliasing (tests/test_node_aliasing.py).
    own = _controller(OUR_CONTROLLER, 'aabbccddeeff', '169.254.0.1', adopted=True, online=True)
    nodeconf = _nodeconf(tmp_path, own)
    nodeconf.network_map['aabbccddeeff'] = own
    discovered_node = _node(online=True)
    nodeconf.listener.nodes['112233445566'] = discovered_node
    nodeconf.listener.nodes['controller-2._'] = _controller(
        FOREIGN_1, 'controller-2._', '10.16.10.4', online=True)

    kept = nodeconf._without_foreign_controllers(nodeconf.listener.nodes)

    assert kept['112233445566'] is discovered_node
    assert 'controller-2._' not in kept


@pytest.mark.xfail(
    strict=True,
    reason='removing a saved foreign controller needs cuemsutils '
           '(specs/upstream-reports/foreign-controller-scoping.md, T3/T4)',
)
def test_a_controller_removes_a_foreign_controller_saved_earlier(tmp_path):
    # A map written by an unfiltered pass already holds a peer controller as
    # adopted (test2's real map on 2026-10-06). It must be removed, not just
    # flipped offline: offline means "ours, currently absent".
    own = _controller(OUR_CONTROLLER, 'aabbccddeeff', '169.254.0.1', adopted=True, online=True)
    nodeconf = _nodeconf(tmp_path, own)
    nodeconf.network_map['aabbccddeeff'] = own
    nodeconf.network_map['ac2b6e046d5c'] = _controller(
        FOREIGN_2, 'ac2b6e046d5c', '10.16.10.2', adopted=True, online=False)
    nodeconf.listener.nodes['controller._'] = _controller(
        OUR_CONTROLLER, 'controller._', '169.254.0.1', online=True)
    nodeconf.listener.nodes['ac2b6e046d5c'] = _controller(
        FOREIGN_2, 'ac2b6e046d5c', '10.16.10.2', online=True)

    nodeconf.refresh_network_map()

    assert _uuids(nodeconf) == {OUR_CONTROLLER}
    assert not re.search(FOREIGN_2, open(nodeconf.map_path).read())
