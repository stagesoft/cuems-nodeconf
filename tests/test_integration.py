"""
Integration tests for CuemsNodeConf covering end-to-end scenarios.
"""
import pytest
from unittest.mock import MagicMock, patch, Mock
import sys

from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsutils.tools.NodeList import NodeIndex, NodeRole, node as Node
from cuemsutils.config.network_map import CuemsNetworkMapType
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener


class TestIntegrationScenarios:
    """Integration tests for complete workflows."""

    def test_first_run_becomes_controller_scenario(self, tmp_path, monkeypatch):
        """Test complete first-run scenario where node becomes controller."""
        nodeconf = CuemsNodeConf()
        nodeconf.ip = '169.254.1.1'
        nodeconf.map_path = str(tmp_path / 'network_map.xml')  # First run - no file

        # Setup listener with no controllers
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes = NodeIndex()

        # Create local firstrun node
        local_node = Node(
            uuid='local-uuid',
            mac='localmac1234',
            name='local_node',
            node_role=NodeRole.firstrun,
            ip='169.254.1.1',
        )
        nodeconf.listener.nodes['localmac1234'] = local_node
        nodeconf.node = local_node

        # Mock all external operations
        with patch('shutil.copy2'), \
             patch.object(nodeconf, 'change_network_to_master', return_value=True), \
             patch.object(nodeconf, 'get_ips'), \
             patch.object(nodeconf, 'update_master_lock_file'), \
             patch.object(nodeconf, 'notify_systemd'):

            # Simulate set_node_role
            nodeconf.set_node_role()

            assert nodeconf.node['node_role'] == NodeRole.controller

    def test_node_discovers_controller_scenario(self):
        """Test scenario where a plain node discovers the controller."""
        nodeconf = CuemsNodeConf()
        nodeconf.ip = '169.254.1.1'
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')

        # Add controller node to discovered nodes
        controller_node = Node(
            uuid='controller-uuid',
            mac='mastermac123',
            name='controller_node',
            node_role=NodeRole.controller,
            ip='192.168.1.1',
        )
        nodeconf.listener.nodes['mastermac123'] = controller_node

        # Add local node
        local_node = Node(
            uuid='local-uuid',
            mac='localmac1234',
            name='local_node',
            node_role=NodeRole.node,
            ip='169.254.1.1',
        )
        nodeconf.listener.nodes['localmac1234'] = local_node

        # Check nodes
        nodeconf.check_nodes()

        # Verify controller is detected
        assert len(nodeconf.listener.nodes.controllers) == 1
        assert nodeconf.listener.nodes.controllers[0]['uuid'] == 'controller-uuid'

    def test_node_adoption_workflow(self, tmp_path):
        """Test complete node adoption workflow."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')

        # Add discovered node
        discovered_node = Node(
            uuid='discovered-uuid',
            mac='discoveredmac',
            name='discovered_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
            adopted=False,
        )
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes['discoveredmac'] = discovered_node

        # Merge discovered nodes
        with patch.object(CuemsNetworkMapType, 'save'):
            nodeconf.refresh_network_map()

        # Adopt the node
        with patch.object(CuemsNetworkMapType, 'save'):
            result = nodeconf.adopt_node('discovered-uuid')

            assert result['OK'] is True
            assert nodeconf.network_map['discoveredmac']['adopted'] is True

    def test_controller_node_network_merge(self):
        """Test merging network map with controller and node."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')

        # Add controller and node to discovered nodes
        controller = Node(
            uuid='controller-uuid',
            mac='mastermac123',
            name='controller',
            node_role=NodeRole.controller,
            ip='192.168.1.1',
        )
        plain_node = Node(
            uuid='node-uuid',
            mac='slavemac1234',
            name='node',
            node_role=NodeRole.node,
            ip='192.168.1.2',
        )
        nodeconf.listener.nodes['mastermac123'] = controller
        nodeconf.listener.nodes['slavemac1234'] = plain_node

        # Merge and set controller as adopted
        with patch.object(CuemsNetworkMapType, 'save'):
            nodeconf.refresh_network_map()

        # Verify controller is adopted, node is not
        assert nodeconf.network_map['mastermac123']['adopted'] is True
        assert nodeconf.network_map['slavemac1234']['adopted'] is False
        assert nodeconf.network_map['mastermac123']['online'] is True
        assert nodeconf.network_map['slavemac1234']['online'] is True

    def test_large_network_with_multiple_nodes(self):
        """Test network with controller and multiple plain nodes."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()  # Ensure fresh network map
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes = NodeIndex()  # Ensure fresh listener nodes

        # Add controller node
        controller = Node(
            uuid='controller-uuid',
            mac='mastermac123',
            name='controller',
            node_role=NodeRole.controller,
            ip='192.168.1.1',
        )

        # Add multiple plain nodes
        node1 = Node(
            uuid='node1-uuid',
            mac='slave1mac123',
            name='node1',
            node_role=NodeRole.node,
            ip='192.168.1.2',
        )
        node2 = Node(
            uuid='node2-uuid',
            mac='slave2mac456',
            name='node2',
            node_role=NodeRole.node,
            ip='192.168.1.3',
        )
        node3 = Node(
            uuid='node3-uuid',
            mac='slave3mac789',
            name='node3',
            node_role=NodeRole.node,
            ip='192.168.1.4',
        )

        nodeconf.listener.nodes['mastermac123'] = controller
        nodeconf.listener.nodes['slave1mac123'] = node1
        nodeconf.listener.nodes['slave2mac456'] = node2
        nodeconf.listener.nodes['slave3mac789'] = node3

        # Merge and set controller as adopted
        with patch.object(CuemsNetworkMapType, 'save'):
            nodeconf.refresh_network_map()

        # Verify all nodes are in network map
        assert len(nodeconf.network_map) == 4
        assert 'mastermac123' in nodeconf.network_map
        assert 'slave1mac123' in nodeconf.network_map
        assert 'slave2mac456' in nodeconf.network_map
        assert 'slave3mac789' in nodeconf.network_map

        # Verify controller is adopted, nodes are not
        assert nodeconf.network_map['mastermac123']['adopted'] is True
        assert nodeconf.network_map['slave1mac123']['adopted'] is False
        assert nodeconf.network_map['slave2mac456']['adopted'] is False
        assert nodeconf.network_map['slave3mac789']['adopted'] is False

        # Verify all nodes are online
        assert nodeconf.network_map['mastermac123']['online'] is True
        assert nodeconf.network_map['slave1mac123']['online'] is True
        assert nodeconf.network_map['slave2mac456']['online'] is True
        assert nodeconf.network_map['slave3mac789']['online'] is True

        # Verify node role selections
        assert len(nodeconf.listener.nodes.controllers) == 1
        assert len(nodeconf.listener.nodes.by_role(NodeRole.node)) == 3

    def test_network_with_mixed_node_roles(self):
        """Test network with controller, nodes, and a firstrun node."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()  # Ensure fresh network map
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes = NodeIndex()  # Ensure fresh listener nodes

        # Add controller
        controller = Node(
            uuid='controller-uuid',
            mac='mastermac123',
            name='controller',
            node_role=NodeRole.controller,
            ip='192.168.1.1',
        )

        # Add adopted nodes
        node1 = Node(
            uuid='node1-uuid',
            mac='slave1mac123',
            name='node1',
            node_role=NodeRole.node,
            ip='192.168.1.2',
            adopted=True,
        )
        node2 = Node(
            uuid='node2-uuid',
            mac='slave2mac456',
            name='node2',
            node_role=NodeRole.node,
            ip='192.168.1.3',
            adopted=True,
        )

        # Add firstrun node (new node joining network)
        firstrun = Node(
            uuid='firstrun-uuid',
            mac='firstrunmac789',
            name='firstrun',
            node_role=NodeRole.firstrun,
            ip='192.168.1.4',
        )

        # Pre-populate network_map with adopted nodes (simulating existing network)
        nodeconf.network_map['slave1mac123'] = node1
        nodeconf.network_map['slave2mac456'] = node2

        # Now add all nodes to listener (rediscovery)
        nodeconf.listener.nodes['mastermac123'] = controller
        nodeconf.listener.nodes['slave1mac123'] = node1
        nodeconf.listener.nodes['slave2mac456'] = node2
        nodeconf.listener.nodes['firstrunmac789'] = firstrun

        # Merge nodes (should preserve adopted status for existing nodes)
        with patch.object(CuemsNetworkMapType, 'save'):
            nodeconf.refresh_network_map()

        # Verify all nodes are present
        assert len(nodeconf.network_map) == 4

        # Verify node role selections
        assert len(nodeconf.listener.nodes.controllers) == 1
        assert len(nodeconf.listener.nodes.by_role(NodeRole.node)) == 2
        assert len(nodeconf.listener.nodes.by_role(NodeRole.firstrun)) == 1

        # Verify adoption status
        assert nodeconf.network_map['mastermac123']['adopted'] is True
        assert nodeconf.network_map['slave1mac123']['adopted'] is True  # Was already adopted, preserved
        assert nodeconf.network_map['slave2mac456']['adopted'] is True  # Was already adopted, preserved
        assert nodeconf.network_map['firstrunmac789']['adopted'] is False  # Firstrun not adopted

    def test_network_with_nodes_going_offline(self):
        """Test network where some nodes go offline."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()  # Ensure fresh network map
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes = NodeIndex()  # Ensure fresh listener nodes

        # Initially all nodes are online
        controller = Node(
            uuid='controller-uuid',
            mac='mastermac123',
            name='controller',
            node_role=NodeRole.controller,
            ip='192.168.1.1',
            online=True,
        )
        node1 = Node(
            uuid='node1-uuid',
            mac='slave1mac123',
            name='node1',
            node_role=NodeRole.node,
            ip='192.168.1.2',
            online=True,
        )
        node2 = Node(
            uuid='node2-uuid',
            mac='slave2mac456',
            name='node2',
            node_role=NodeRole.node,
            ip='192.168.1.3',
            online=True,
        )

        # Add all to network map
        nodeconf.network_map['mastermac123'] = controller
        nodeconf.network_map['slave1mac123'] = node1
        nodeconf.network_map['slave2mac456'] = node2

        # First merge - all online
        nodeconf.listener.nodes['mastermac123'] = controller
        nodeconf.listener.nodes['slave1mac123'] = node1
        nodeconf.listener.nodes['slave2mac456'] = node2
        with patch.object(CuemsNetworkMapType, 'save'):
            nodeconf.refresh_network_map()

        assert nodeconf.network_map['mastermac123']['online'] is True
        assert nodeconf.network_map['slave1mac123']['online'] is True
        assert nodeconf.network_map['slave2mac456']['online'] is True

        # Second merge - node2 goes offline (not in discovered nodes)
        nodeconf.listener.nodes = NodeIndex()
        nodeconf.listener.nodes['mastermac123'] = controller
        nodeconf.listener.nodes['slave1mac123'] = node1
        # node2 is missing - not in discovered nodes
        with patch.object(CuemsNetworkMapType, 'save'):
            nodeconf.refresh_network_map()

        # node2 should be marked offline
        assert nodeconf.network_map['mastermac123']['online'] is True
        assert nodeconf.network_map['slave1mac123']['online'] is True
        assert nodeconf.network_map['slave2mac456']['online'] is False

    def test_adopting_multiple_nodes_in_sequence(self, tmp_path):
        """Test adopting multiple nodes one after another."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()  # Ensure fresh network map
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes = NodeIndex()  # Ensure fresh listener nodes

        # Add multiple discovered nodes
        node1 = Node(
            uuid='node1-uuid',
            mac='slave1mac123',
            name='node1',
            node_role=NodeRole.node,
            ip='192.168.1.2',
            adopted=False,
        )
        node2 = Node(
            uuid='node2-uuid',
            mac='slave2mac456',
            name='node2',
            node_role=NodeRole.node,
            ip='192.168.1.3',
            adopted=False,
        )
        node3 = Node(
            uuid='node3-uuid',
            mac='slave3mac789',
            name='node3',
            node_role=NodeRole.node,
            ip='192.168.1.4',
            adopted=False,
        )

        nodeconf.listener.nodes['slave1mac123'] = node1
        nodeconf.listener.nodes['slave2mac456'] = node2
        nodeconf.listener.nodes['slave3mac789'] = node3

        # Merge discovered nodes
        with patch.object(CuemsNetworkMapType, 'save'):
            nodeconf.refresh_network_map()

        # Adopt nodes one by one
        with patch.object(CuemsNetworkMapType, 'save'):
            result1 = nodeconf.adopt_node('node1-uuid')
            assert result1['OK'] is True
            assert nodeconf.network_map['slave1mac123']['adopted'] is True

            result2 = nodeconf.adopt_node('node2-uuid')
            assert result2['OK'] is True
            assert nodeconf.network_map['slave2mac456']['adopted'] is True

            result3 = nodeconf.adopt_node('node3-uuid')
            assert result3['OK'] is True
            assert nodeconf.network_map['slave3mac789']['adopted'] is True

        # Verify all are adopted
        assert nodeconf.network_map['slave1mac123']['adopted'] is True
        assert nodeconf.network_map['slave2mac456']['adopted'] is True
        assert nodeconf.network_map['slave3mac789']['adopted'] is True
