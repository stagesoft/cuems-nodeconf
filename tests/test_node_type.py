"""
Tests for node type determination (master/slave/firstrun).
"""
import pytest
from unittest.mock import patch
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsNode import CuemsNode, CuemsNodeDict
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener


class TestNodeTypeDetermination:
    """Test node type determination (master/slave/firstrun)."""
    
    def test_set_node_type_becomes_master_when_no_master(self, tmp_path, monkeypatch):
        """Test that node becomes master when no master exists."""
        nodeconf = CuemsNodeConf()
        nodeconf.ip = '169.254.1.1'
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes = CuemsNodeDict()  # No masters
        
        # Create a mock node
        nodeconf.node = CuemsNode({
            'uuid': 'test-uuid',
            'mac': 'aabbccddeeff',
            'name': 'test_node',
            'node_type': CuemsNode.NodeType.firstrun,
            'ip': '169.254.1.1',
        })
        
        # Mock file operations
        with patch('shutil.copy2'), \
             patch.object(nodeconf, 'change_network_to_master', return_value=True), \
             patch.object(nodeconf, 'get_ips'):
            
            nodeconf.set_node_type()
            
            assert nodeconf.node.node_type == CuemsNode.NodeType.master
    
    def test_set_node_type_stays_slave_when_master_exists(self, tmp_path, monkeypatch):
        """Test that node stays slave when master exists."""
        nodeconf = CuemsNodeConf()
        nodeconf.ip = '169.254.1.1'
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        
        # Add a master node to listener
        master_node = CuemsNode({
            'uuid': 'master-uuid',
            'mac': 'mastermac123',
            'name': 'master_node',
            'node_type': CuemsNode.NodeType.master,
            'ip': '192.168.1.1',
        })
        nodeconf.listener.nodes['mastermac123'] = master_node
        
        # Create a firstrun node
        nodeconf.node = CuemsNode({
            'uuid': 'test-uuid',
            'mac': 'aabbccddeeff',
            'name': 'test_node',
            'node_type': CuemsNode.NodeType.firstrun,
            'ip': '169.254.1.1',
        })
        
        # Slave template copy now uses shutil.copy2 (was os.system 'sudo cp').
        with patch('shutil.copy2'):
            nodeconf.set_node_type()

            assert nodeconf.node.node_type == CuemsNode.NodeType.slave

