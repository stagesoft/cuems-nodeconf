"""
Tests for the missing-adopted-nodes warning.

The warning is not part of CuemsNetworkMapType.refresh's orchestration — the
library leaves reporting to its caller — so it survives feature 001 only because
refresh_network_map asks for it explicitly (FR-007). These tests pin that it
still fires, and only when it should.
"""
from unittest.mock import patch

from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener
from cuemsutils.config.network_map import CuemsNetworkMapType
from cuemsutils.tools.NodeList import NodeIndex, NodeRole, node as Node


def _nodeconf_with_adopted(uuid, mac, name):
    nodeconf = CuemsNodeConf()
    nodeconf._document = CuemsNetworkMapType()  # feature 002: start-up loads this document; these tests skip start-up
    nodeconf.network_map = NodeIndex()
    nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
    nodeconf.network_map[mac] = Node(
        uuid=uuid,
        mac=mac,
        name=name,
        node_role=NodeRole.node,
        ip='192.168.1.10',
        adopted=True,
    )
    return nodeconf


class TestMissingNodes:
    """The warning naming adopted nodes that discovery did not see."""

    def test_no_warning_when_every_adopted_node_is_present(self):
        nodeconf = _nodeconf_with_adopted('adopted-uuid', 'adoptedmac12', 'adopted_node')
        nodeconf.listener.nodes['adoptedmac12'] = Node(
            uuid='adopted-uuid',
            mac='adoptedmac12',
            name='adopted_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
        )

        with patch.object(CuemsNetworkMapType, 'save'), \
             patch('cuemsutils.log.Logger.warning') as mock_warning:
            nodeconf.refresh_network_map()

        mock_warning.assert_not_called()

    def test_warns_once_naming_an_adopted_node_that_was_not_discovered(self):
        nodeconf = _nodeconf_with_adopted('missing-uuid', 'missingmac123', 'missing_node')
        # Not discovered: the listener saw nothing.

        with patch.object(CuemsNetworkMapType, 'save'), \
             patch('cuemsutils.log.Logger.warning') as mock_warning:
            nodeconf.refresh_network_map()

        mock_warning.assert_called_once()
        assert 'missing_node' in mock_warning.call_args[0][0]
