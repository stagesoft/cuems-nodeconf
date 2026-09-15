"""
Tests for the daemon's refresh path — how discovery reaches the persisted map.

The merge rules themselves (match by uuid, mark the undiscovered offline, keep
the controller adopted) belong to cuemsutils and are pinned by the vendored
yardstick in specs/planning/yardstick/. What these tests pin is the daemon's
side of that seam: that refresh_network_map carries discovery into the
in-memory index, and that the map on disk is written only when something
changed — and written again after a write that failed.
"""
import os
from unittest.mock import patch

from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener
from cuemsutils.config.network_map import CuemsNetworkMapType
from cuemsutils.tools.NodeList import NodeIndex, NodeRole, node as Node


def _nodeconf(map_path=None):
    nodeconf = CuemsNodeConf()
    nodeconf.network_map = NodeIndex()
    nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
    if map_path is not None:
        nodeconf.map_path = map_path
    return nodeconf


class TestRefreshCarriesDiscoveryIntoTheMap:
    """Discovery reaches self.network_map through refresh_network_map."""

    def test_a_newly_discovered_node_joins_unadopted_and_online(self):
        nodeconf = _nodeconf()
        nodeconf.listener.nodes['newmac123456'] = Node(
            uuid='new-uuid',
            mac='newmac123456',
            name='new_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
            online=True,
        )

        with patch.object(CuemsNetworkMapType, 'save'):
            nodeconf.refresh_network_map()

        assert 'newmac123456' in nodeconf.network_map
        assert nodeconf.network_map['newmac123456']['adopted'] is False
        assert nodeconf.network_map['newmac123456']['online'] is True

    def test_a_rediscovered_node_keeps_its_adoption_and_takes_fresh_discovery_fields(self):
        nodeconf = _nodeconf()
        nodeconf.network_map['existingmac12'] = Node(
            uuid='existing-uuid',
            mac='existingmac12',
            name='existing_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
            adopted=True,
            online=False,
        )
        nodeconf.listener.nodes['existingmac12'] = Node(
            uuid='existing-uuid',
            mac='existingmac12',
            name='existing_node',
            node_role=NodeRole.node,
            ip='192.168.1.11',  # IP changed
            online=True,
        )

        with patch.object(CuemsNetworkMapType, 'save'):
            nodeconf.refresh_network_map()

        assert nodeconf.network_map['existingmac12']['adopted'] is True
        assert nodeconf.network_map['existingmac12']['online'] is True
        assert nodeconf.network_map['existingmac12']['ip'] == '192.168.1.11'

    def test_an_undiscovered_node_is_marked_offline(self):
        nodeconf = _nodeconf()
        nodeconf.network_map['offlinemac123'] = Node(
            uuid='offline-uuid',
            mac='offlinemac123',
            name='offline_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
            online=True,
        )

        with patch.object(CuemsNetworkMapType, 'save'):
            nodeconf.refresh_network_map()

        assert nodeconf.network_map['offlinemac123']['online'] is False

    def test_the_controller_stays_adopted_and_nothing_else_is_adopted_for_it(self):
        nodeconf = _nodeconf()
        for mac, uuid, role, ip in (
            ('mastermac123', 'controller-uuid', NodeRole.controller, '192.168.1.1'),
            ('slavemac1234', 'node-uuid', NodeRole.node, '192.168.1.2'),
        ):
            nodeconf.network_map[mac] = Node(
                uuid=uuid, mac=mac, name=mac, node_role=role, ip=ip, adopted=False,
            )
            nodeconf.listener.nodes[mac] = Node(
                uuid=uuid, mac=mac, name=mac, node_role=role, ip=ip, online=True,
            )

        with patch.object(CuemsNetworkMapType, 'save'):
            nodeconf.refresh_network_map()

        assert nodeconf.network_map['mastermac123']['adopted'] is True
        assert nodeconf.network_map['slavemac1234']['adopted'] is False


class TestRefreshWritesOnlyWhatItMust:
    """When the map is written — the part the yardstick does not pin."""

    def test_an_unchanged_map_is_not_rewritten(self, tmp_path):
        """Constitution II: write only on change (T022).

        The write decision moves inside CuemsNetworkMapType.refresh during
        feature 001, which is exactly when it could be lost without anything
        failing.
        """
        map_path = str(tmp_path / 'network_map.xml')
        nodeconf = _nodeconf(map_path)
        nodeconf.listener.nodes['aabbccddeeff'] = Node(
            uuid='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
            mac='aabbccddeeff',
            name='aabbccddeeff._cuems_nodeconf._tcp.local.',
            node_role=NodeRole.node,
            ip='169.254.1.9',
            online=True,
        )

        nodeconf.refresh_network_map()
        assert os.path.exists(map_path)
        written_at = os.stat(map_path).st_mtime_ns

        real_save = CuemsNetworkMapType.save
        with patch.object(CuemsNetworkMapType, 'save', autospec=True, side_effect=real_save) as save:
            nodeconf.refresh_network_map()

        assert not save.called
        assert os.stat(map_path).st_mtime_ns == written_at

    def test_a_failed_write_is_retried_on_the_next_refresh(self):
        """A write that failed is owed, not forgotten.

        Nothing about the discovery changes between the two passes, so a
        write-only-on-change rule alone would never retry — leaving the map on
        disk stale until some unrelated node event. The daemon retries on every
        pass until the write lands.
        """
        nodeconf = _nodeconf()
        nodeconf.listener.nodes['aabbccddeeff'] = Node(
            uuid='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
            mac='aabbccddeeff',
            name='aabbccddeeff._cuems_nodeconf._tcp.local.',
            node_role=NodeRole.node,
            ip='169.254.1.9',
            online=True,
        )

        with patch.object(
            CuemsNetworkMapType, 'save', side_effect=[PermissionError('read-only /etc'), None]
        ) as save:
            nodeconf.refresh_network_map()
            nodeconf.refresh_network_map()

        assert save.call_count == 2


class TestReadNetworkMap:
    """Loading a provisioned map at boot (FR-005)."""

    def test_reads_a_provisioned_map_into_the_index(self, cuems_conf_dir):
        nodeconf = CuemsNodeConf()
        nodeconf.map_path = str(cuems_conf_dir / 'network_map.xml')

        nodeconf.read_network_map()

        assert set(nodeconf.network_map) == {'2cf05d21cca3', '0800276db133'}
        controller = nodeconf.network_map['2cf05d21cca3']
        assert controller['node_role'] is NodeRole.controller
        assert controller['adopted'] is True
        absent = nodeconf.network_map['0800276db133']
        assert absent['node_role'] is NodeRole.node
        assert absent['adopted'] is False
        assert absent['online'] is False
