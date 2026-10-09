"""
Comprehensive tests for the node adoption flow.
Tests the complete operation from engine callback to network map persistence.
"""
import pytest
from unittest.mock import MagicMock, patch, call
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsNode import CuemsNode, CuemsNodeDict
import tempfile
import os


class TestAdoptionFlow:
    """Test the complete node adoption flow."""
    
    def test_complete_adoption_flow(self, tmp_path):
        """Test the complete adoption flow from engine callback to network map write."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        
        # Add a discovered but not adopted node
        new_node = CuemsNode({
            'uuid': 'new-node-uuid-123',
            'mac': 'newmac123456',
            'name': 'new_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.100',
            'adopted': False,
            'online': True
        })
        nodeconf.network_map['newmac123456'] = new_node
        
        # Verify initial state
        assert new_node.adopted is False
        assert 'new-node-uuid-123' in [n.uuid for n in nodeconf.network_map.values()]
        
        # Create mock communications thread
        nodeconf.communications_thread = MagicMock()
        nodeconf.communications_thread.event_loop = MagicMock()
        nodeconf.communications_thread.respond_to_engine = MagicMock()
        
        # Create mock context
        mock_context = MagicMock()
        
        # Create adoption message
        message = {
            'action': 'nodelist_modify',
            'value': 'new-node-uuid-123',
            'modify_action': 'ADD'
        }
        
        # Test adoption through engine_callback
        with patch('asyncio.run_coroutine_threadsafe') as mock_run:
            nodeconf.engine_callback(message, mock_context)
            
            # Verify node was adopted
            assert new_node.adopted is True
            
            # Verify write_network_map was called (through adopt_node)
            # We can't directly verify this since it's called inside adopt_node,
            # but we can verify the node state changed
            
            # Verify response was sent
            assert mock_run.called
            # The coroutine should send a success response
            call_args = mock_run.call_args
            assert call_args is not None
    
    def test_adoption_flow_node_not_found(self, tmp_path):
        """Test adoption flow when node is not found."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        
        # Create mock communications thread
        nodeconf.communications_thread = MagicMock()
        nodeconf.communications_thread.event_loop = MagicMock()
        nodeconf.communications_thread.respond_to_engine = MagicMock()
        
        # Create mock context
        mock_context = MagicMock()
        
        # Create adoption message for non-existent node
        message = {
            'action': 'nodelist_modify',
            'value': 'nonexistent-uuid',
            'modify_action': 'ADD'
        }
        
        # Test adoption through engine_callback
        with patch('asyncio.run_coroutine_threadsafe') as mock_run:
            nodeconf.engine_callback(message, mock_context)
            
            # Verify response was sent with error
            assert mock_run.called
            # The coroutine should send an error response
    
    def test_adoption_preserves_other_node_data(self, tmp_path):
        """Test that adoption only changes the adopted flag, preserving other data."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        
        # Add a node with specific data
        original_ip = '192.168.1.100'
        original_name = 'test_node'
        original_node_type = CuemsNode.NodeType.slave
        
        node = CuemsNode({
            'uuid': 'test-uuid-123',
            'mac': 'testmac123456',
            'name': original_name,
            'node_type': original_node_type,
            'ip': original_ip,
            'adopted': False,
            'online': True
        })
        nodeconf.network_map['testmac123456'] = node
        
        # Adopt the node
        with patch.object(nodeconf, 'write_network_map'):
            result = nodeconf.adopt_node('test-uuid-123')
            
            assert result['OK'] is True
            assert node.adopted is True
            
            # Verify other data is preserved
            assert node.ip == original_ip
            assert node.name == original_name
            assert node.node_type == original_node_type
            assert node.uuid == 'test-uuid-123'
            assert node.mac == 'testmac123456'
            assert node.online is True
    
    def test_adoption_writes_network_map(self, tmp_path):
        """Test that adoption triggers network map write."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        
        # Add a node (must be online to be adoptable)
        node = CuemsNode({
            'uuid': 'test-uuid-123',
            'mac': 'testmac123456',
            'name': 'test_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'adopted': False,
            'online': True
        })
        nodeconf.network_map['testmac123456'] = node
        
        # Adopt the node and verify write_network_map is called
        with patch.object(nodeconf, 'write_network_map') as mock_write:
            result = nodeconf.adopt_node('test-uuid-123')
            
            assert result['OK'] is True
            assert mock_write.called
            # Verify it was called with the network_map
            mock_write.assert_called_once_with(nodeconf.network_map)
    
    def test_adoption_multiple_nodes_only_adopts_target(self, tmp_path):
        """Test that adopting one node doesn't affect others."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        
        # Add multiple nodes (must be online to be adoptable)
        node1 = CuemsNode({
            'uuid': 'node1-uuid',
            'mac': 'node1mac123',
            'name': 'node1',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'adopted': False,
            'online': True
        })
        node2 = CuemsNode({
            'uuid': 'node2-uuid',
            'mac': 'node2mac123',
            'name': 'node2',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.11',
            'adopted': False,
            'online': True
        })
        nodeconf.network_map['node1mac123'] = node1
        nodeconf.network_map['node2mac123'] = node2
        
        # Adopt only node1
        with patch.object(nodeconf, 'write_network_map'):
            result = nodeconf.adopt_node('node1-uuid')
            
            assert result['OK'] is True
            assert node1.adopted is True
            assert node2.adopted is False  # Should remain unadopted
    
    def test_adoption_after_merge_discovered_nodes(self, tmp_path):
        """Test adoption after merging discovered nodes."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        nodeconf.listener = MagicMock()
        nodeconf.listener.nodes = CuemsNodeDict()
        
        # Add a discovered node
        discovered_node = CuemsNode({
            'uuid': 'discovered-uuid',
            'mac': 'discoveredmac',
            'name': 'discovered_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'adopted': False,
            'online': True
        })
        nodeconf.listener.nodes['discoveredmac'] = discovered_node
        
        # Merge discovered nodes
        nodeconf.merge_discovered_nodes()
        
        # Verify node is in network_map but not adopted
        assert 'discoveredmac' in nodeconf.network_map
        assert nodeconf.network_map['discoveredmac'].adopted is False
        
        # Now adopt the node
        with patch.object(nodeconf, 'write_network_map'):
            result = nodeconf.adopt_node('discovered-uuid')
            
            assert result['OK'] is True
            assert nodeconf.network_map['discoveredmac'].adopted is True

