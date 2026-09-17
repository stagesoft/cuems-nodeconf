"""
Tests for node role determination (controller/node/firstrun).

feature 007: the local ``CuemsNode.NodeType`` enum is gone. The one
definition is ``cuemsutils.tools.NodeList.NodeRole`` (contract C1); this
module imports it rather than defining its own vocabulary.
"""
import pytest
from unittest.mock import patch

from cuemsutils.tools.NodeList import NodeIndex, NodeRole, node as Node
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsNodeConf import NodeRole as ConfNodeRole
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener


class TestNoLocalNodeRoleEnum:
    """T067: no node-role enum is defined locally; every usage resolves to
    the ``cuemsutils`` definition."""

    def test_cuemsnodeconf_defines_no_own_node_role_module(self):
        with pytest.raises(ModuleNotFoundError):
            import cuemsnodeconf.CuemsNode  # noqa: F401

    def test_cuemsnodeconf_node_role_is_the_cuemsutils_definition(self):
        assert ConfNodeRole is NodeRole


class TestNodeRoleDetermination:
    """Test node role determination (controller/node/firstrun)."""

    def test_set_node_role_becomes_controller_when_no_controller(self, tmp_path, monkeypatch):
        """Test that node becomes controller when no controller exists."""
        nodeconf = CuemsNodeConf()
        nodeconf.ip = '169.254.1.1'
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes = NodeIndex()  # No controllers

        nodeconf.node = Node(
            uuid='test-uuid',
            mac='aabbccddeeff',
            name='test_node',
            node_role=NodeRole.firstrun,
            ip='169.254.1.1',
        )

        with patch('shutil.copy2'), \
             patch.object(nodeconf, 'change_network_to_master', return_value=True), \
             patch.object(nodeconf, 'get_ips'):

            nodeconf.set_node_role()

            assert nodeconf.node['node_role'] == NodeRole.controller

    def test_set_node_role_stays_node_when_controller_exists(self, tmp_path, monkeypatch):
        """Test that node stays a plain node when a controller exists."""
        nodeconf = CuemsNodeConf()
        nodeconf.ip = '169.254.1.1'
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')

        controller_node = Node(
            uuid='controller-uuid',
            mac='mastermac123',
            name='controller_node',
            node_role=NodeRole.controller,
            ip='192.168.1.1',
        )
        nodeconf.listener.nodes['mastermac123'] = controller_node

        nodeconf.node = Node(
            uuid='test-uuid',
            mac='aabbccddeeff',
            name='test_node',
            node_role=NodeRole.firstrun,
            ip='169.254.1.1',
        )

        # Node service template copy now uses shutil.copy2 (was os.system 'sudo cp').
        with patch('shutil.copy2'):
            nodeconf.set_node_role()

            assert nodeconf.node['node_role'] == NodeRole.node
