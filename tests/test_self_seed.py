"""The daemon's own map row comes from the library, not a private insert (feature 003, US3).

After discovery, the entry found at this node's IP is seeded into the index
through NodeIndex.ensure (cuems-utils 73daab6), by reference, keyed by the
MAC from settings.xml — the listener's MAC is the first twelve characters of
the service NAME (the hostname, `controller._` for a controller), a label and
not identity (constitution III). merge never clobbers that key afterwards
(spec FR-015; research R6; contracts/startup-order.md steps 9–10).
"""
from unittest.mock import patch

import pytest

from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener
from cuemsutils.tools.NodeList import NodeIndex, NodeRole, node as Node

SETTINGS_UUID = '0367f391-ebf4-48b2-9f26-000000000001'
SETTINGS_MAC = '2cf05d21cca3'
OWN_IP = '169.254.1.1'


def _discovered_self(role=NodeRole.firstrun):
    """What the listener holds for us: keyed and filled with the name-derived MAC."""
    return Node(uuid=SETTINGS_UUID, mac='controller._', name='controller._cuems_nodeconf._tcp.local.',
                node_role=role, ip=OWN_IP, adopted=False, online=True)


def _nodeconf(conf_dir):
    nodeconf = CuemsNodeConf()
    nodeconf.map_path = str(conf_dir / 'network_map.xml')
    nodeconf.ip = OWN_IP
    nodeconf.settings_uuid = SETTINGS_UUID
    nodeconf.settings_mac = SETTINGS_MAC
    nodeconf.listener = CuemsAvahiListener(ip=OWN_IP)
    nodeconf.read_network_map()
    return nodeconf


class TestSeedingTheOwnRow:
    def test_the_row_is_the_daemons_own_record_keyed_by_the_settings_mac(self, cuems_conf_dir_empty):
        nodeconf = _nodeconf(cuems_conf_dir_empty)
        nodeconf.node = _discovered_self()
        nodeconf.listener.nodes['controller._'] = nodeconf.node

        nodeconf._seed_own_row()

        assert list(nodeconf.network_map) == [SETTINGS_MAC]
        assert nodeconf.network_map[SETTINGS_MAC] is nodeconf.node      # by reference
        assert nodeconf.node['mac'] == SETTINGS_MAC                       # the label is replaced
        assert nodeconf.node['uuid'] == SETTINGS_UUID

    def test_a_later_role_change_is_visible_through_the_row(self, cuems_conf_dir_empty):
        """The aliasing contract: the daemon's record IS the map's row."""
        nodeconf = _nodeconf(cuems_conf_dir_empty)
        nodeconf.node = _discovered_self()
        nodeconf._seed_own_row()

        nodeconf.node['node_role'] = NodeRole.controller

        assert nodeconf.network_map[SETTINGS_MAC]['node_role'] == NodeRole.controller


class TestNoDuplicateAfterTheFirstMerge:
    def test_the_first_merge_refreshes_the_seeded_row_in_place(self, cuems_conf_dir_empty):
        nodeconf = _nodeconf(cuems_conf_dir_empty)
        nodeconf.node = _discovered_self()
        nodeconf.listener.nodes['controller._'] = nodeconf.node
        nodeconf._seed_own_row()

        nodeconf.network_map.merge(nodeconf.listener.nodes)

        rows = [n for n in nodeconf.network_map.values() if n['uuid'] == SETTINGS_UUID]
        assert len(rows) == 1
        assert list(nodeconf.network_map) == [SETTINGS_MAC]
        assert rows[0]['online'] is True


class TestSeedingIsANoOpWhenListed:
    def test_a_map_that_lists_this_node_is_left_alone(self, cuems_conf_dir):
        """The populated fixture already lists SETTINGS_UUID (adopted controller)."""
        nodeconf = _nodeconf(cuems_conf_dir)
        existing = nodeconf.network_map[SETTINGS_MAC]
        pending_before = nodeconf._map_write_pending
        nodeconf.node = _discovered_self(NodeRole.controller)

        inserted = nodeconf._seed_own_row()

        assert inserted is False
        assert nodeconf.network_map[SETTINGS_MAC] is existing
        assert existing['adopted'] is True
        assert nodeconf._map_write_pending is pending_before


class TestRunSeedsAfterTheSelfLookup:
    """contracts/startup-order.md: the row exists when the role decision is reached (10 before 11)."""

    class _Stop(Exception):
        pass

    def test_run_seeds_the_own_row_after_self_lookup(self, cuems_conf_dir_empty):
        nodeconf = CuemsNodeConf()
        nodeconf.map_path = str(cuems_conf_dir_empty / 'network_map.xml')
        nodeconf.settings_uuid = SETTINGS_UUID
        nodeconf.settings_mac = SETTINGS_MAC
        own = _discovered_self()
        seen = {}

        def _set_ip():
            nodeconf.ip = OWN_IP

        def _stop_at_role_decision():
            seen['rows'] = list(nodeconf.network_map)
            seen['row_is_node'] = nodeconf.network_map.get(SETTINGS_MAC) is nodeconf.node
            raise self._Stop

        with patch.object(nodeconf, 'get_ips', side_effect=_set_ip), \
             patch('cuemsnodeconf.CuemsNodeConf.Zeroconf'), \
             patch.object(nodeconf, 'start_avahi_listener'), \
             patch.object(nodeconf, 'wait_for_local_service_registration'), \
             patch.object(nodeconf, 'retreive_local_node', return_value=own), \
             patch.object(nodeconf, '_render_service_record', return_value=False), \
             patch.object(nodeconf, '_should_resume_master', side_effect=_stop_at_role_decision):
            with pytest.raises(self._Stop):
                nodeconf.run()

        assert seen['rows'] == [SETTINGS_MAC]
        assert seen['row_is_node'] is True
