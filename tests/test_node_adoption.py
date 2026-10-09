"""
Tests for node adoption and unadoption functionality.
"""
import pytest
from unittest.mock import patch
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsNode import CuemsNode, CuemsNodeDict


class TestNodeAdoption:
    """Test node adoption and unadoption functionality."""
    
    def test_adopt_node_success(self, tmp_path, monkeypatch):
        """Test successfully adopting a node."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        
        # Add a node to network_map (must be online to be adoptable)
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
        
        with patch.object(nodeconf, 'write_network_map'):
            result = nodeconf.adopt_node('test-uuid-123')
            
            assert result['OK'] is True
            assert nodeconf.network_map['testmac123456'].adopted is True
    
    def test_adopt_node_not_found(self):
        """Test adopting a node that doesn't exist."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        
        result = nodeconf.adopt_node('nonexistent-uuid')
        
        assert result['OK'] is False
        assert 'error' in result
        assert 'not found' in result['error']
    
    def test_adopt_node_already_adopted(self, tmp_path):
        """Test adopting a node that is already adopted."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        
        # Add an already adopted node
        node = CuemsNode({
            'uuid': 'test-uuid-123',
            'mac': 'testmac123456',
            'name': 'test_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'adopted': True,
            'online': True
        })
        nodeconf.network_map['testmac123456'] = node
        
        # Try to adopt again - should return success but not write network map
        with patch.object(nodeconf, 'write_network_map') as mock_write:
            result = nodeconf.adopt_node('test-uuid-123')
            
            assert result['OK'] is True
            assert 'message' in result
            assert 'already adopted' in result['message']
            # Should not write network map since nothing changed
            assert not mock_write.called
            # Node should still be adopted
            assert nodeconf.network_map['testmac123456'].adopted is True
    
    def test_adopt_node_offline(self, tmp_path):
        """Test adopting an offline node should fail."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        
        # Add an offline node
        node = CuemsNode({
            'uuid': 'test-uuid-123',
            'mac': 'testmac123456',
            'name': 'test_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'adopted': False,
            'online': False
        })
        nodeconf.network_map['testmac123456'] = node
        
        # Try to adopt - should fail
        with patch.object(nodeconf, 'write_network_map') as mock_write:
            result = nodeconf.adopt_node('test-uuid-123')
            
            assert result['OK'] is False
            assert 'error' in result
            assert 'offline' in result['error']
            # Should not write network map since adoption failed
            assert not mock_write.called
            # Node should still not be adopted
            assert nodeconf.network_map['testmac123456'].adopted is False
    
    def test_unadopt_node_success(self, tmp_path, monkeypatch):
        """Test successfully unadopting a node."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        
        # Add an adopted slave node (must be online)
        node = CuemsNode({
            'uuid': 'test-uuid-123',
            'mac': 'testmac123456',
            'name': 'test_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'adopted': True,
            'online': True
        })
        nodeconf.network_map['testmac123456'] = node
        
        with patch.object(nodeconf, 'write_network_map'):
            result = nodeconf.unadopt_node('test-uuid-123')
            
            assert result['OK'] is True
            assert nodeconf.network_map['testmac123456'].adopted is False
    
    def test_unadopt_node_already_unadopted(self, tmp_path):
        """Test unadopting a node that is already unadopted."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        
        # Add an already unadopted node
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
        
        # Try to unadopt again - should return success but not write network map
        with patch.object(nodeconf, 'write_network_map') as mock_write:
            result = nodeconf.unadopt_node('test-uuid-123')
            
            assert result['OK'] is True
            assert 'message' in result
            assert 'already unadopted' in result['message']
            # Should not write network map since nothing changed
            assert not mock_write.called
            # Node should still be unadopted
            assert nodeconf.network_map['testmac123456'].adopted is False
    
    def test_unadopt_node_offline(self, tmp_path):
        """Test unadopting an offline node (should succeed with warning)."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        
        # Add an adopted but offline node
        node = CuemsNode({
            'uuid': 'test-uuid-123',
            'mac': 'testmac123456',
            'name': 'test_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'adopted': True,
            'online': False
        })
        nodeconf.network_map['testmac123456'] = node
        
        # Try to unadopt - should succeed (offline nodes can be unadopted)
        with patch.object(nodeconf, 'write_network_map') as mock_write:
            result = nodeconf.unadopt_node('test-uuid-123')
            
            assert result['OK'] is True
            # Should write network map since node was unadopted
            assert mock_write.called
            # Node should now be unadopted
            assert nodeconf.network_map['testmac123456'].adopted is False
    
    def test_unadopt_master_node_fails(self):
        """Test that unadopting a master node fails."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        
        # Add an adopted master node
        master_node = CuemsNode({
            'uuid': 'master-uuid',
            'mac': 'mastermac123',
            'name': 'master_node',
            'node_type': CuemsNode.NodeType.master,
            'ip': '192.168.1.1',
            'adopted': True
        })
        nodeconf.network_map['mastermac123'] = master_node
        
        result = nodeconf.unadopt_node('master-uuid')
        
        assert result['OK'] is False
        assert 'error' in result
        assert 'Cannot unadopt master node' in result['error']
        # Master should still be adopted
        assert nodeconf.network_map['mastermac123'].adopted is True
    
    def test_unadopt_node_not_found(self):
        """Test unadopting a node that doesn't exist."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        
        result = nodeconf.unadopt_node('nonexistent-uuid')
        
        assert result['OK'] is False
        assert 'error' in result
        assert 'not found' in result['error']

