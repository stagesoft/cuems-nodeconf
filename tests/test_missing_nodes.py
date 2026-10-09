"""
Tests for checking missing adopted nodes.
"""
import pytest
from unittest.mock import patch
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsNode import CuemsNode, CuemsNodeDict
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener


class TestMissingNodes:
    """Test checking for missing adopted nodes."""
    
    def test_check_missing_adopted_nodes_all_present(self):
        """Test when all adopted nodes are present."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        
        # Add adopted node to network_map
        adopted_node = CuemsNode({
            'uuid': 'adopted-uuid',
            'mac': 'adoptedmac12',
            'name': 'adopted_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'adopted': True
        })
        nodeconf.network_map['adoptedmac12'] = adopted_node
        
        # Add same node to discovered nodes
        discovered_node = CuemsNode({
            'uuid': 'adopted-uuid',
            'mac': 'adoptedmac12',
            'name': 'adopted_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
        })
        nodeconf.listener.nodes['adoptedmac12'] = discovered_node
        
        # Should not raise or log warning
        nodeconf.check_missing_adopted_nodes()
    
    def test_check_missing_adopted_nodes_some_missing(self):
        """Test when some adopted nodes are missing."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        
        # Add adopted node to network_map
        missing_node = CuemsNode({
            'uuid': 'missing-uuid',
            'mac': 'missingmac123',
            'name': 'missing_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'adopted': True
        })
        nodeconf.network_map['missingmac123'] = missing_node
        
        # Don't add to discovered nodes (node is missing)
        
        # Should log warning but not raise
        with patch('cuemsutils.log.Logger.warning') as mock_warning:
            nodeconf.check_missing_adopted_nodes()
            mock_warning.assert_called_once()

