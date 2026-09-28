"""
Tests for service discovery and local node retrieval.
"""
import pytest
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsutils.tools.NodeList import NodeIndex, NodeRole, node as Node
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener


class TestServiceDiscovery:
    """Test service discovery and local node retrieval."""

    def test_wait_for_local_service_registration(self):
        """Test waiting for local service registration."""
        nodeconf = CuemsNodeConf()
        nodeconf.ip = '169.254.1.1'
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')

        # Add local node to listener
        local_node = Node(
            uuid='local-uuid',
            mac='localmac1234',
            name='local_node',
            node_role=NodeRole.node,
            ip='169.254.1.1',
        )
        nodeconf.listener.nodes['localmac1234'] = local_node

        # Should return immediately since node is already present
        nodeconf.wait_for_local_service_registration()

    def test_retreive_local_node(self):
        """Test retrieving local node from discovered nodes."""
        nodeconf = CuemsNodeConf()
        nodeconf.ip = '169.254.1.1'
        nodeconf.settings_uuid = 'local-uuid'  # feature 003: the lookup also matches the provisioned uuid
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes = NodeIndex()  # Reset nodes

        # Add local node to listener
        local_node = Node(
            uuid='local-uuid',
            mac='localmac1234',
            name='local_node',
            node_role=NodeRole.node,
            ip='169.254.1.1',
        )
        nodeconf.listener.nodes['localmac1234'] = local_node

        # Add another node with different IP
        other_node = Node(
            uuid='other-uuid',
            mac='othermac1234',
            name='other_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
        )
        nodeconf.listener.nodes['othermac1234'] = other_node

        retrieved = nodeconf.retreive_local_node()

        assert retrieved['ip'] == '169.254.1.1'
        assert retrieved['uuid'] == 'local-uuid'
