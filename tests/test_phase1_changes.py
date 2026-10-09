# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""Regression tests for the Phase-1 nodeconf re-enable changes.

Covers the invariants that were either broken or newly introduced:
  - write_network_map must NOT mutate the live node_type enum (copy-on-serialize)
  - a round-trip must preserve operator fields role_id / alias / hostname
  - CuemsAvahiListener.remove_service must drop the node from the table
  - AliasPublisher.ensure must scope the A record to the given interface index
    and be idempotent
"""
import os
import pytest
from unittest.mock import patch

import cuemsutils
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsNode import CuemsNode, CuemsNodeDict
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener
import cuemsnodeconf.NodeXmlBuilders  # noqa: F401  (registers XML builders)

# Validate against the canonical cuems-utils schema (which has role_id/alias/
# hostname). The dev box's /etc/cuems/network_map.xsd may be an older copy.
CANON_XSD = os.path.join(
    os.path.dirname(cuemsutils.__file__), 'xml', 'schemas', 'network_map.xsd'
)


def _master_nodeconf(tmp_path):
    nc = CuemsNodeConf()
    nc.map_path = str(tmp_path / 'network_map.xml')
    nc.xsd_path = CANON_XSD
    nc.network_map = CuemsNodeDict()
    nc.network_map['aabbccddeeff'] = CuemsNode({
        'uuid': 'u-master',
        'mac': 'aabbccddeeff',
        'name': 'controller._cuems_nodeconf._tcp.local.',
        'node_type': CuemsNode.NodeType.master,
        'ip': '169.254.0.1',
        'adopted': True,
        'online': True,
        'role_id': 'controller',
        'alias': 'Controller',
        'hostname': 'controller',
    })
    return nc


def test_write_does_not_mutate_live_node_type_enum(tmp_path):
    nc = _master_nodeconf(tmp_path)
    nc.write_network_map(nc.network_map)
    # The live node must still hold the enum, not the serialized string.
    assert nc.network_map['aabbccddeeff'].node_type is CuemsNode.NodeType.master


def test_master_guard_survives_a_write(tmp_path):
    # The enum-mutation bug made this fail on the SECOND attempt: after a write
    # the node_type became a str, so the master guard stopped matching.
    nc = _master_nodeconf(tmp_path)
    nc.write_network_map(nc.network_map)
    result = nc.unadopt_node('u-master')
    assert result['OK'] is False
    assert 'master' in result['error'].lower()


def test_roundtrip_preserves_role_id_alias_hostname(tmp_path):
    nc = _master_nodeconf(tmp_path)
    nc.write_network_map(nc.network_map)

    nc2 = CuemsNodeConf()
    nc2.map_path = nc.map_path
    nc2.xsd_path = CANON_XSD
    nc2.read_network_map()

    node = nc2.network_map['aabbccddeeff']
    assert node.get('role_id') == 'controller'
    assert node.get('alias') == 'Controller'
    assert node.get('hostname') == 'controller'
    assert node.node_type is CuemsNode.NodeType.master  # parsed back to enum


def test_remove_service_drops_node_from_table():
    listener = CuemsAvahiListener(ip='169.254.1.1')
    listener.nodes['aabbccddeeff'] = CuemsNode({
        'uuid': 'u', 'mac': 'aabbccddeeff', 'name': 'n',
        'node_type': CuemsNode.NodeType.slave, 'ip': '169.254.1.9',
    })
    listener.remove_service(None, '_cuems_nodeconf._tcp.local.',
                            'aabbccddeeff._cuems_nodeconf._tcp.local.')
    assert 'aabbccddeeff' not in listener.nodes


def test_alias_publisher_scopes_to_interface_and_is_idempotent(monkeypatch):
    import cuemsnodeconf.AliasPublisher as ap

    calls = {'add': 0, 'last': None}

    class FakeGroup:
        def AddAddress(self, idx, proto, flags, name, ip):
            calls['add'] += 1
            calls['last'] = (idx, proto, name, ip)
        def Commit(self):
            pass
        def GetState(self):
            return ap.ENTRY_GROUP_ESTABLISHED
        def Reset(self):
            pass
        def Free(self):
            pass

    class FakeServer:
        def GetNetworkInterfaceIndexByName(self, ifname):
            return 7 if ifname == 'ethernet1' else 3
        def EntryGroupNew(self):
            return '/grp'

    fake_group = FakeGroup()
    pub = ap.AliasPublisher()
    pub._connect = lambda: True
    pub._server = FakeServer()
    pub._bus = type('B', (), {'get_object': lambda *a, **k: None})()
    monkeypatch.setattr(ap.dbus, 'Interface', lambda obj, iface: fake_group)

    assert pub.ensure('controller.local', '169.254.0.1', 'ethernet1') is True
    assert calls['add'] == 1
    assert calls['last'][0] == 7           # scoped to ethernet1's index
    assert calls['last'][3] == '169.254.0.1'

    # Same args again -> no re-publish (already ESTABLISHED).
    assert pub.ensure('controller.local', '169.254.0.1', 'ethernet1') is True
    assert calls['add'] == 1

    # Changed IP -> re-publish.
    assert pub.ensure('controller.local', '169.254.9.9', 'ethernet1') is True
    assert calls['add'] == 2
    assert calls['last'][3] == '169.254.9.9'


def test_merge_discovered_controller_does_not_duplicate(tmp_path):
    # The controller's avahi service is named 'controller', so the listener's
    # get_mac() derives a garbage key ('controller._'). merge_discovered_nodes
    # must match the existing master entry by UUID and update it in place — NOT
    # create a duplicate node nor flip the real (mac-keyed) node offline. This
    # pins the corruption a live smoke test surfaced on the controller.
    nc = _master_nodeconf(tmp_path)  # map: mac=aabbccddeeff, uuid=u-master

    listener = CuemsAvahiListener(ip='169.254.0.1')
    listener.nodes['controller._'] = CuemsNode({
        'uuid': 'u-master',                       # same uuid as the map entry
        'mac': 'controller._',                    # garbage key from the name
        'name': 'controller._cuems_nodeconf._tcp.local.',
        'node_type': CuemsNode.NodeType.master,
        'ip': '169.254.99.99',                    # renegotiated IPv4LL
        'adopted': False,
        'online': True,
    })
    nc.listener = listener

    nc.merge_discovered_nodes()

    # Exactly one node, still keyed by the REAL mac.
    assert list(nc.network_map.keys()) == ['aabbccddeeff']
    node = nc.network_map['aabbccddeeff']
    # Operator fields preserved.
    assert node.get('role_id') == 'controller'
    assert node.get('alias') == 'Controller'
    assert node.get('hostname') == 'controller'
    # Discovery refreshed the ip and kept it online/adopted; enum intact.
    assert node.get('ip') == '169.254.99.99'
    assert node.online is True
    assert node.adopted is True
    assert node.node_type is CuemsNode.NodeType.master


# --- Foreign controllers on a shared LAN -----------------------------------
#
# Several clusters share the taller LAN (test2, test, test3). Every controller
# advertises node_type=master over mDNS. A host's map must only ever hold ITS
# cluster's controller: the 2026-10-01 incident had test2's nodeconf merge
# test3 into its map and set_master_always_adopted() mark it ADOPTED.

def _foreign_master(uuid='u-foreign', ip='10.16.10.4', name='controller-2'):
    return CuemsNode({
        'uuid': uuid,
        'mac': name + '._',                       # garbage key from the name
        'name': f'{name}._cuems_nodeconf._tcp.local.',
        'node_type': CuemsNode.NodeType.master,
        'ip': ip,
        'adopted': False,
        'online': True,
    })


def _slave(uuid='u-slave', mac='112233445566', ip='169.254.0.2'):
    return CuemsNode({
        'uuid': uuid,
        'mac': mac,
        'name': f'{mac}._cuems_nodeconf._tcp.local.',
        'node_type': CuemsNode.NodeType.slave,
        'ip': ip,
        'adopted': False,
        'online': True,
    })


def test_controller_ignores_foreign_controllers_on_shared_lan(tmp_path):
    nc = _master_nodeconf(tmp_path)
    nc.node = nc.network_map['aabbccddeeff']     # I am this cluster's master

    listener = CuemsAvahiListener(ip='169.254.0.1')
    listener.nodes['controller._'] = CuemsNode({
        'uuid': 'u-master', 'mac': 'controller._',
        'name': 'controller._cuems_nodeconf._tcp.local.',
        'node_type': CuemsNode.NodeType.master, 'ip': '169.254.0.1',
        'adopted': False, 'online': True,
    })
    listener.nodes['112233445566'] = _slave()
    listener.nodes['controller-2._'] = _foreign_master()
    listener.nodes['ac2b6e046d5c'] = _foreign_master(
        uuid='u-foreign-2', ip='10.16.10.2', name='ac2b6e046d5c')
    nc.listener = listener

    nc.merge_discovered_nodes()
    nc.set_master_always_adopted()

    uuids = {n.uuid for n in nc.network_map.values()}
    assert uuids == {'u-master', 'u-slave'}
    # Only OUR master is adopted; the new slave waits for operator adoption.
    assert nc.network_map['aabbccddeeff'].adopted is True
    assert nc.network_map['112233445566'].adopted is False


def test_controller_purges_foreign_controller_already_persisted(tmp_path):
    # A map written by an unfiltered nodeconf already carries a peer
    # controller as adopted=True (test2's real map on 2026-10-06). It must be
    # dropped, not merely flipped offline.
    nc = _master_nodeconf(tmp_path)
    nc.node = nc.network_map['aabbccddeeff']
    stale = _foreign_master(uuid='u-foreign-2', ip='10.16.10.2',
                            name='ac2b6e046d5c')
    stale.adopted = True
    stale.online = False
    nc.network_map['ac2b6e046d5c'] = stale

    listener = CuemsAvahiListener(ip='169.254.0.1')
    listener.nodes['ac2b6e046d5c'] = _foreign_master(
        uuid='u-foreign-2', ip='10.16.10.2', name='ac2b6e046d5c')
    nc.listener = listener

    nc.merge_discovered_nodes()
    nc.set_master_always_adopted()

    assert list(nc.network_map.keys()) == ['aabbccddeeff']
    assert nc.network_map['aabbccddeeff'].adopted is True


def test_node_keeps_its_recorded_controller_and_ignores_others(tmp_path):
    # A node (slave) belongs to the master its map already records.
    nc = _master_nodeconf(tmp_path)                  # map: our master u-master
    nc.node = _slave()                                # I am a node
    nc.network_map['112233445566'] = nc.node
    nc.node.adopted = True

    listener = CuemsAvahiListener(ip='169.254.0.2')
    listener.nodes['controller._'] = CuemsNode({
        'uuid': 'u-master', 'mac': 'controller._',
        'name': 'controller._cuems_nodeconf._tcp.local.',
        'node_type': CuemsNode.NodeType.master, 'ip': '169.254.0.1',
        'adopted': False, 'online': True,
    })
    listener.nodes['112233445566'] = _slave()
    listener.nodes['controller-2._'] = _foreign_master()
    nc.listener = listener

    nc.merge_discovered_nodes()

    assert {n.uuid for n in nc.network_map.values()} == {'u-master', 'u-slave'}
    assert nc.network_map['aabbccddeeff'].online is True


def test_fresh_node_with_no_recorded_controller_accepts_the_first_one(tmp_path):
    # Legacy / first-join behaviour is unchanged: with no master in the map
    # there is nothing to compare against, so the discovered master is taken.
    nc = CuemsNodeConf()
    nc.map_path = str(tmp_path / 'network_map.xml')
    nc.xsd_path = CANON_XSD
    nc.network_map = CuemsNodeDict()
    nc.node = _slave()

    listener = CuemsAvahiListener(ip='169.254.0.2')
    listener.nodes['controller._'] = CuemsNode({
        'uuid': 'u-master', 'mac': 'controller._',
        'name': 'controller._cuems_nodeconf._tcp.local.',
        'node_type': CuemsNode.NodeType.master, 'ip': '169.254.0.1',
        'adopted': False, 'online': True,
    })
    listener.nodes['112233445566'] = _slave()
    nc.listener = listener

    nc.merge_discovered_nodes()
    nc.set_master_always_adopted()

    assert {n.uuid for n in nc.network_map.values()} == {'u-master', 'u-slave'}
    master = next(n for n in nc.network_map.values() if n.uuid == 'u-master')
    assert master.adopted is True
